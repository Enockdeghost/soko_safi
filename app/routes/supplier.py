from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import Supplier, SupplierProduct, OrderRequest, User, Notification
from app.forms import SupplierProfileForm, SupplierProductForm, OrderRequestForm
from app.decorators import supplier_required
from app.routes import supplier_bp as bp
from app.utils import send_sms, create_notification, log_transaction
from datetime import datetime
from sqlalchemy import func

@bp.route('/dashboard')
@login_required
@supplier_required
def dashboard():
    supplier = current_user.supplier_profile
    if not supplier:
        # Create empty profile if missing
        supplier = Supplier(user_id=current_user.id, business_name='', verified=False)
        db.session.add(supplier)
        db.session.commit()
        flash('Tafadhali kamilisha wasifu wako.', 'info')
        return redirect(url_for('supplier.profile'))
    
    if not supplier.verified:
        flash('Akaunti yako inasubiri kuthibitishwa na msimamizi.', 'warning')
    
    pending_orders = OrderRequest.query.filter_by(supplier_id=supplier.id, status='pending').count()
    total_orders = OrderRequest.query.filter_by(supplier_id=supplier.id).count()
    total_products = SupplierProduct.query.filter_by(supplier_id=supplier.id).count()
    recent_orders = OrderRequest.query.filter_by(supplier_id=supplier.id).order_by(OrderRequest.created_at.desc()).limit(5).all()
    
    return render_template('supplier/dashboard.html',
                           supplier=supplier,
                           pending_orders=pending_orders,
                           total_orders=total_orders,
                           total_products=total_products,
                           recent_orders=recent_orders)

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
@supplier_required
def profile():
    """View and edit supplier profile (business name, contact, location)."""
    supplier = current_user.supplier_profile
    if not supplier:
        # Create if missing (should exist from registration)
        supplier = Supplier(user_id=current_user.id, business_name='', verified=False)
        db.session.add(supplier)
        db.session.commit()

    form = SupplierProfileForm(obj=supplier)
    if form.validate_on_submit():
        supplier.business_name = form.business_name.data
        supplier.contact_phone = form.contact_phone.data
        supplier.location = form.location.data
        db.session.commit()
        log_transaction(current_user.id, 'update_supplier_profile', 'Profile updated', request.remote_addr)
        flash('Taarifa zimesasishwa.', 'success')
        return redirect(url_for('supplier.profile'))

    return render_template('supplier/profile.html', form=form, supplier=supplier)

@bp.route('/products')
@login_required
@supplier_required
def products():
    """List supplier's products (items they can supply)."""
    supplier = current_user.supplier_profile
    products = SupplierProduct.query.filter_by(supplier_id=supplier.id).all()
    return render_template('supplier/products.html', products=products)

@bp.route('/products/add', methods=['GET', 'POST'])
@login_required
@supplier_required
def add_product():
    """Add a new product to supplier's catalog."""
    form = SupplierProductForm()
    if form.validate_on_submit():
        supplier = current_user.supplier_profile
        product = SupplierProduct(
            supplier_id=supplier.id,
            name=form.name.data,
            price=form.price.data,
            unit=form.unit.data
        )
        db.session.add(product)
        db.session.commit()
        log_transaction(current_user.id, 'add_supplier_product', f'Added {product.name}', request.remote_addr)
        flash('Bidhaa imeongezwa.', 'success')
        return redirect(url_for('supplier.products'))
    return render_template('supplier/add_product.html', form=form)

@bp.route('/products/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@supplier_required
def edit_product(id):
    """Edit supplier product."""
    product = SupplierProduct.query.get_or_404(id)
    if product.supplier_id != current_user.supplier_profile.id:
        abort(403)
    form = SupplierProductForm(obj=product)
    if form.validate_on_submit():
        product.name = form.name.data
        product.price = form.price.data
        product.unit = form.unit.data
        db.session.commit()
        log_transaction(current_user.id, 'edit_supplier_product', f'Edited {product.name}', request.remote_addr)
        flash('Bidhaa imesasishwa.', 'success')
        return redirect(url_for('supplier.products'))
    return render_template('supplier/edit_product.html', form=form, product=product)

@bp.route('/products/delete/<int:id>')
@login_required
@supplier_required
def delete_product(id):
    """Delete supplier product."""
    product = SupplierProduct.query.get_or_404(id)
    if product.supplier_id != current_user.supplier_profile.id:
        abort(403)
    db.session.delete(product)
    db.session.commit()
    log_transaction(current_user.id, 'delete_supplier_product', f'Deleted product ID {id}', request.remote_addr)
    flash('Bidhaa imefutwa.', 'success')
    return redirect(url_for('supplier.products'))

@bp.route('/orders')
@login_required
@supplier_required
def orders():
    """List all order requests from vendors."""
    supplier = current_user.supplier_profile
    orders = OrderRequest.query.filter_by(supplier_id=supplier.id)\
        .order_by(OrderRequest.created_at.desc()).all()
    return render_template('supplier/orders.html', orders=orders)

@bp.route('/order/<int:id>/accept')
@login_required
@supplier_required
def accept_order(id):
    """Accept a vendor's order request."""
    order = OrderRequest.query.get_or_404(id)
    if order.supplier_id != current_user.supplier_profile.id:
        abort(403)
    order.status = 'accepted'
    order.updated_at = datetime.utcnow()
    db.session.commit()

    # Notify vendor
    create_notification(order.vendor_id, 'order_accepted',
                        f'Ombi lako kwa {order.product_name} limekubaliwa na msambazaji.')
    # Optionally send SMS
    vendor = User.query.get(order.vendor_id)
    if vendor:
        send_sms(vendor.phone, f'Ombi lako la {order.product_name} limekubaliwa.')

    log_transaction(current_user.id, 'accept_order', f'Order {order.id} accepted', request.remote_addr)
    flash('Ombi limekubaliwa.', 'success')
    return redirect(url_for('supplier.orders'))

@bp.route('/order/<int:id>/reject')
@login_required
@supplier_required
def reject_order(id):
    """Reject a vendor's order request."""
    order = OrderRequest.query.get_or_404(id)
    if order.supplier_id != current_user.supplier_profile.id:
        abort(403)
    order.status = 'rejected'
    order.updated_at = datetime.utcnow()
    db.session.commit()

    # Notify vendor
    create_notification(order.vendor_id, 'order_rejected',
                        f'Ombi lako kwa {order.product_name} limekataliwa. Tafadhali wasiliana na msambazaji.')

    log_transaction(current_user.id, 'reject_order', f'Order {order.id} rejected', request.remote_addr)
    flash('Ombi limekataliwa.', 'info')
    return redirect(url_for('supplier.orders'))

@bp.route('/order/<int:id>/fulfill')
@login_required
@supplier_required
def fulfill_order(id):
    """Mark order as fulfilled (supplier has delivered)."""
    order = OrderRequest.query.get_or_404(id)
    if order.supplier_id != current_user.supplier_profile.id:
        abort(403)
    order.status = 'fulfilled'
    order.updated_at = datetime.utcnow()
    db.session.commit()

    create_notification(order.vendor_id, 'order_fulfilled',
                        f'Ombi lako la {order.product_name} limetimizwa.')

    log_transaction(current_user.id, 'fulfill_order', f'Order {order.id} fulfilled', request.remote_addr)
    flash('Ombi limetimizwa.', 'success')
    return redirect(url_for('supplier.orders'))

@bp.route('/analytics')
@login_required
@supplier_required
def analytics():
    """Supplier analytics: most requested products, top vendors, etc."""
    supplier = current_user.supplier_profile
    if not supplier.verified:
        flash('Akaunti yako haijathibitishwa.', 'warning')
        return redirect(url_for('supplier.dashboard'))

    # Most requested products
    top_requests = db.session.query(
        OrderRequest.product_name,
        func.sum(OrderRequest.quantity).label('total_qty')
    ).filter(OrderRequest.supplier_id == supplier.id)\
     .group_by(OrderRequest.product_name)\
     .order_by(func.sum(OrderRequest.quantity).desc())\
     .limit(10).all()

    # Vendors who order most
    top_vendors = db.session.query(
        User.full_name,
        func.count(OrderRequest.id).label('order_count')
    ).join(OrderRequest, OrderRequest.vendor_id == User.id)\
     .filter(OrderRequest.supplier_id == supplier.id)\
     .group_by(User.id)\
     .order_by(func.count(OrderRequest.id).desc())\
     .limit(5).all()

    # Orders by month (for chart)
    monthly_orders = db.session.query(
        func.strftime('%Y-%m', OrderRequest.created_at).label('month'),
        func.count(OrderRequest.id).label('count')
    ).filter(OrderRequest.supplier_id == supplier.id)\
     .group_by(func.strftime('%Y-%m', OrderRequest.created_at))\
     .order_by(func.strftime('%Y-%m', OrderRequest.created_at).desc())\
     .limit(12).all()

    return render_template('supplier/analytics.html',
                           top_requests=top_requests,
                           top_vendors=top_vendors,
                           monthly_orders=monthly_orders)