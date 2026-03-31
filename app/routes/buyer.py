from flask import render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import (
    User, Shop, Product, Cart, Order, OrderItem, Review, Wishlist,
    BuyerProfile, Promotion, Notification, Category
)
from app.decorators import buyer_required
from app.routes import buyer_bp as bp
from app.utils import send_sms, create_notification, log_transaction
from datetime import datetime
from sqlalchemy import func
import secrets

def _get_buyer_profile():
    """Helper to retrieve or create a buyer profile, handling list vs. single object."""
    profile = current_user.buyer_profile
    if isinstance(profile, list):
        if profile:
            profile = profile[0]
        else:
            profile = BuyerProfile(user_id=current_user.id, loyalty_points=0)
            db.session.add(profile)
            db.session.commit()
    elif profile is None:
        profile = BuyerProfile(user_id=current_user.id, loyalty_points=0)
        db.session.add(profile)
        db.session.commit()
    return profile

@bp.route('/dashboard')
@login_required
@buyer_required
def dashboard():
    profile = _get_buyer_profile()
    points = profile.loyalty_points

    # Recent orders (limit 5)
    recent_orders = Order.query.filter_by(buyer_id=current_user.id)\
                        .order_by(Order.created_at.desc()).limit(5).all()

    # Wishlist items
    wishlist = Wishlist.query.filter_by(buyer_id=current_user.id).all()

    # Order counts by status
    order_counts = db.session.query(Order.status, func.count(Order.id))\
                    .filter(Order.buyer_id == current_user.id)\
                    .group_by(Order.status).all()
    order_stats = {status: count for status, count in order_counts}

    # Activity feed: combine last 3 orders and unread notifications
    activities = []
    latest_orders = Order.query.filter_by(buyer_id=current_user.id)\
                        .order_by(Order.created_at.desc()).limit(3).all()
    for o in latest_orders:
        activities.append({
            'type': 'order',
            'message': f"Agizo #{o.order_number} limewekwa",
            'time': o.created_at,
            'status': o.status
        })
    notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False)\
                        .order_by(Notification.created_at.desc()).limit(3).all()
    for n in notifs:
        activities.append({
            'type': 'notification',
            'message': n.message,
            'time': n.created_at
        })
    activities.sort(key=lambda x: x['time'], reverse=True)
    activities = activities[:5]

    # Recommendations based on purchase history
    recommended = []
    last_orders_ids = [o.id for o in latest_orders]
    if last_orders_ids:
        category_ids = db.session.query(Product.category_id)\
                        .join(OrderItem)\
                        .filter(OrderItem.order_id.in_(last_orders_ids))\
                        .filter(Product.category_id != None)\
                        .distinct().all()
        category_ids = [c[0] for c in category_ids]
        if category_ids:
            recommended = Product.query.filter(
                Product.category_id.in_(category_ids),
                Product.is_active == True,
                Product.quantity > 0
            ).order_by(func.random()).limit(6).all()
    if len(recommended) < 6:
        top_products = db.session.query(Product)\
                        .join(OrderItem)\
                        .group_by(Product.id)\
                        .order_by(func.sum(OrderItem.quantity).desc())\
                        .limit(6 - len(recommended)).all()
        for p in top_products:
            if p not in recommended:
                recommended.append(p)

    # Active promotions (for all or specific vendors – here we show all active)
    now = datetime.utcnow()
    promotions = Promotion.query.filter(
        Promotion.start_date <= now,
        Promotion.end_date >= now,
        Promotion.is_active == True
    ).limit(3).all()

    return render_template('buyer/dashboard.html',
                           orders=recent_orders,
                           wishlist=wishlist,
                           points=points,
                           order_stats=order_stats,
                           activities=activities,
                           recommended=recommended,
                           promotions=promotions)

@bp.route('/catalog')
def catalog():
    products = Product.query.filter(Product.quantity > 0).all()
    return render_template('buyer/catalog.html', products=products)

@bp.route('/product/<int:id>')
def product_detail(id):
    product = Product.query.get_or_404(id)
    reviews = Review.query.filter_by(vendor_id=product.shop.vendor_id).all()
    in_wishlist = False
    if current_user.is_authenticated and current_user.role == 'buyer':
        in_wishlist = Wishlist.query.filter_by(buyer_id=current_user.id, product_id=id).first() is not None
    return render_template('buyer/product_detail.html', product=product, reviews=reviews, in_wishlist=in_wishlist)

@bp.route('/add-to-cart', methods=['POST'])
@login_required
@buyer_required
def add_to_cart():
    product_id = request.form.get('product_id')
    quantity = float(request.form.get('quantity', 1))
    product = Product.query.get_or_404(product_id)
    if product.quantity < quantity:
        flash('Samahani, bidhaa imeisha kiasi hicho.', 'danger')
        return redirect(request.referrer or url_for('buyer.catalog'))

    cart_item = Cart.query.filter_by(buyer_id=current_user.id, product_id=product_id).first()
    if cart_item:
        cart_item.quantity += quantity
    else:
        cart_item = Cart(buyer_id=current_user.id, product_id=product_id, quantity=quantity)
        db.session.add(cart_item)
    db.session.commit()
    flash('Bidhaa imeongezwa kwenye rukwama.', 'success')
    return redirect(url_for('buyer.view_cart'))

@bp.route('/cart')
@login_required
@buyer_required
def view_cart():
    cart_items = Cart.query.filter_by(buyer_id=current_user.id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('buyer/cart.html', cart_items=cart_items, total=total)

@bp.route('/cart/update/<int:id>', methods=['POST'])
@login_required
@buyer_required
def update_cart(id):
    item = Cart.query.get_or_404(id)
    if item.buyer_id != current_user.id:
        abort(403)
    quantity = float(request.form.get('quantity', 1))
    if quantity <= 0:
        db.session.delete(item)
    else:
        item.quantity = quantity
    db.session.commit()
    return redirect(url_for('buyer.view_cart'))

@bp.route('/cart/remove/<int:id>')
@login_required
@buyer_required
def remove_from_cart(id):
    item = Cart.query.get_or_404(id)
    if item.buyer_id != current_user.id:
        abort(403)
    db.session.delete(item)
    db.session.commit()
    flash('Bidhaa imetolewa kwenye rukwama.', 'success')
    return redirect(url_for('buyer.view_cart'))

@bp.route('/checkout', methods=['GET', 'POST'])
@login_required
@buyer_required
def checkout():
    cart_items = Cart.query.filter_by(buyer_id=current_user.id).all()
    if not cart_items:
        flash('Rukwama yako haina bidhaa.', 'danger')
        return redirect(url_for('buyer.catalog'))

    if request.method == 'POST':
        address = request.form.get('address')
        payment_method = request.form.get('payment_method')
        vendor_items = {}
        for item in cart_items:
            vid = item.product.shop.vendor_id
            vendor_items.setdefault(vid, []).append(item)

        orders_created = []
        for vendor_id, items in vendor_items.items():
            order_number = secrets.token_hex(4).upper()
            total = sum(it.product.price * it.quantity for it in items)
            order = Order(
                order_number=order_number,
                buyer_id=current_user.id,
                vendor_id=vendor_id,
                total_amount=total,
                payment_method=payment_method,
                delivery_address=address,
                status='pending'
            )
            db.session.add(order)
            db.session.flush()
            for item in items:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    price_at_time=item.product.price,
                    subtotal=item.product.price * item.quantity
                )
                db.session.add(order_item)
                item.product.quantity -= item.quantity
                db.session.delete(item)
            orders_created.append(order)
            vendor = User.query.get(vendor_id)
            if vendor:
                send_sms(vendor.phone, f"Umepokea agizo jipya #{order_number} kutoka kwa mnunuzi.")

        total_spent = sum(o.total_amount for o in orders_created)
        points_earned = int(total_spent * 0.01)
        profile = _get_buyer_profile()
        profile.loyalty_points += points_earned
        db.session.commit()
        flash('Agizo limewekwa! Unapokea SMS hivi karibuni.', 'success')
        return redirect(url_for('buyer.orders'))

    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('buyer/checkout.html', cart_items=cart_items, total=total)

@bp.route('/orders')
@login_required
@buyer_required
def orders():
    orders = Order.query.filter_by(buyer_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('buyer/orders.html', orders=orders)

@bp.route('/order/<int:id>')
@login_required
@buyer_required
def order_detail(id):
    order = Order.query.get_or_404(id)
    if order.buyer_id != current_user.id:
        abort(403)
    return render_template('buyer/order_detail.html', order=order)

@bp.route('/order/<int:id>/review', methods=['GET', 'POST'])
@login_required
@buyer_required
def review_order(id):
    order = Order.query.get_or_404(id)
    if order.buyer_id != current_user.id or order.status != 'delivered':
        abort(403)
    existing = Review.query.filter_by(order_id=id).first()
    if existing:
        flash('Tayari umetoa maoni kwa agizo hili.', 'info')
        return redirect(url_for('buyer.order_detail', id=id))

    if request.method == 'POST':
        rating = int(request.form.get('rating'))
        comment = request.form.get('comment', '')
        review = Review(order_id=id, buyer_id=current_user.id, vendor_id=order.vendor_id, rating=rating, comment=comment)
        db.session.add(review)
        db.session.commit()
        flash('Asante kwa maoni yako!', 'success')
        return redirect(url_for('buyer.order_detail', id=id))

    return render_template('buyer/review.html', order=order)

@bp.route('/wishlist')
@login_required
@buyer_required
def wishlist():
    wishlist_items = Wishlist.query.filter_by(buyer_id=current_user.id).all()
    return render_template('buyer/wishlist.html', wishlist=wishlist_items)

@bp.route('/wishlist/toggle/<int:product_id>')
@login_required
@buyer_required
def toggle_wishlist(product_id):
    wish = Wishlist.query.filter_by(buyer_id=current_user.id, product_id=product_id).first()
    if wish:
        db.session.delete(wish)
        db.session.commit()
        return jsonify({'status': 'removed'})
    else:
        wish = Wishlist(buyer_id=current_user.id, product_id=product_id)
        db.session.add(wish)
        db.session.commit()
        return jsonify({'status': 'added'})

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
@buyer_required
def profile():
    profile = _get_buyer_profile()
    if request.method == 'POST':
        profile.default_address = request.form.get('address')
        db.session.commit()
        flash('Taarifa zimesasishwa.', 'success')
        return redirect(url_for('buyer.profile'))
    return render_template('buyer/profile.html', profile=profile)

@bp.route('/cart-count')
@login_required
@buyer_required
def cart_count():
    count = Cart.query.filter_by(buyer_id=current_user.id).count()
    return jsonify({'count': count})