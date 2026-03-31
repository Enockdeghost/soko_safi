from flask import render_template, redirect, url_for, flash, request, abort, Response
from flask_login import login_required, current_user
from app.extensions import db
from app.models import (
    User, Supplier, SupplierProduct, OrderRequest, Notification,
    TransactionLog, Product, Order, OrderItem, Review
)
from app.forms import SupplierProfileForm, SupplierProductForm
from app.decorators import supplier_required
from app.routes import supplier_bp as bp
from app.utils import send_sms, create_notification, log_transaction
from datetime import datetime, date, timedelta
from sqlalchemy import func

def get_supplier_or_abort():
    supplier = current_user.supplier_profile
    if not supplier:
        flash('Tafadhali kamilisha wasifu wako.', 'warning')
        return redirect(url_for('supplier.profile'))
    return supplier

@bp.route('/dashboard')
@login_required
@supplier_required
def dashboard():
    supplier = get_supplier_or_abort()
    if isinstance(supplier, Response):
        return supplier

    pending_orders = OrderRequest.query.filter_by(supplier_id=supplier.id, status='pending').count()
    accepted_orders = OrderRequest.query.filter_by(supplier_id=supplier.id, status='accepted').count()
    fulfilled_orders = OrderRequest.query.filter_by(supplier_id=supplier.id, status='fulfilled').count()
    total_orders = OrderRequest.query.filter_by(supplier_id=supplier.id).count()

    recent_orders = OrderRequest.query.filter_by(supplier_id=supplier.id)\
                        .order_by(OrderRequest.created_at.desc()).limit(5).all()

    top_products = db.session.query(
        OrderRequest.product_name,
        func.sum(OrderRequest.quantity).label('total_qty')
    ).filter(OrderRequest.supplier_id == supplier.id)\
     .group_by(OrderRequest.product_name)\
     .order_by(func.sum(OrderRequest.quantity).desc())\
     .limit(5).all()

    total_quantity = db.session.query(func.sum(OrderRequest.quantity))\
                     .filter(OrderRequest.supplier_id == supplier.id,
                             OrderRequest.status == 'fulfilled').scalar() or 0

    recent_activities = OrderRequest.query.filter_by(supplier_id=supplier.id)\
                         .order_by(OrderRequest.updated_at.desc()).limit(5).all()

    return render_template('supplier/dashboard.html',
                           supplier=supplier,
                           pending_orders=pending_orders,
                           accepted_orders=accepted_orders,
                           fulfilled_orders=fulfilled_orders,
                           total_orders=total_orders,
                           recent_orders=recent_orders,
                           top_products=top_products,
                           total_quantity=total_quantity,
                           recent_activities=recent_activities)

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
@supplier_required
def profile():
    supplier = current_user.supplier_profile
    if not supplier:
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
    supplier = get_supplier_or_abort()
    if isinstance(supplier, Response):
        return supplier
    products = SupplierProduct.query.filter_by(supplier_id=supplier.id).all()
    return render_template('supplier/products.html', products=products)

@bp.route('/products/add', methods=['GET', 'POST'])
@login_required
@supplier_required
def add_product():
    supplier = get_supplier_or_abort()
    if isinstance(supplier, Response):
        return supplier
    form = SupplierProductForm()
    if form.validate_on_submit():
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
    supplier = get_supplier_or_abort()
    if isinstance(supplier, Response):
        return supplier
    orders = OrderRequest.query.filter_by(supplier_id=supplier.id)\
                .order_by(OrderRequest.created_at.desc()).all()
    return render_template('supplier/orders.html', orders=orders)

@bp.route('/order/<int:id>/accept')
@login_required
@supplier_required
def accept_order(id):
    order = OrderRequest.query.get_or_404(id)
    if order.supplier_id != current_user.supplier_profile.id:
        abort(403)
    if order.status != 'pending':
        flash('Ombi hili tayari limechukuliwa.', 'info')
        return redirect(url_for('supplier.orders'))
    order.status = 'accepted'
    order.updated_at = datetime.utcnow()
    db.session.commit()
    create_notification(order.vendor_id, 'order_accepted',
                        f'Ombi lako la {order.product_name} limekubaliwa.')
    vendor = User.query.get(order.vendor_id)
    if vendor:
        send_sms(vendor.phone, f'Ombi lako la {order.product_name} limekubaliwa.')
    log_transaction(current_user.id, 'accept_order', f'Accepted order {order.id}', request.remote_addr)
    flash('Ombi limekubaliwa.', 'success')
    return redirect(url_for('supplier.orders'))

@bp.route('/order/<int:id>/reject')
@login_required
@supplier_required
def reject_order(id):
    order = OrderRequest.query.get_or_404(id)
    if order.supplier_id != current_user.supplier_profile.id:
        abort(403)
    if order.status != 'pending':
        flash('Ombi hili tayari limechukuliwa.', 'info')
        return redirect(url_for('supplier.orders'))
    order.status = 'rejected'
    order.updated_at = datetime.utcnow()
    db.session.commit()
    create_notification(order.vendor_id, 'order_rejected',
                        f'Ombi lako la {order.product_name} limekataliwa.')
    vendor = User.query.get(order.vendor_id)
    if vendor:
        send_sms(vendor.phone, f'Ombi lako la {order.product_name} limekataliwa.')
    log_transaction(current_user.id, 'reject_order', f'Rejected order {order.id}', request.remote_addr)
    flash('Ombi limekataliwa.', 'info')
    return redirect(url_for('supplier.orders'))

@bp.route('/order/<int:id>/fulfill')
@login_required
@supplier_required
def fulfill_order(id):
    order = OrderRequest.query.get_or_404(id)
    if order.supplier_id != current_user.supplier_profile.id:
        abort(403)
    if order.status != 'accepted':
        flash('Unaweza kutimiza maagizo yaliyokubaliwa tu.', 'danger')
        return redirect(url_for('supplier.orders'))
    order.status = 'fulfilled'
    order.updated_at = datetime.utcnow()
    db.session.commit()
    create_notification(order.vendor_id, 'order_fulfilled',
                        f'Ombi lako la {order.product_name} limetimizwa.')
    vendor = User.query.get(order.vendor_id)
    if vendor:
        send_sms(vendor.phone, f'Ombi lako la {order.product_name} limetimizwa.')
    log_transaction(current_user.id, 'fulfill_order', f'Fulfilled order {order.id}', request.remote_addr)
    flash('Ombi limetimizwa.', 'success')
    return redirect(url_for('supplier.orders'))

@bp.route('/analytics')
@login_required
@supplier_required
def analytics():
    supplier = get_supplier_or_abort()
    if isinstance(supplier, Response):
        return supplier

    top_requests = db.session.query(
        OrderRequest.product_name,
        func.sum(OrderRequest.quantity).label('total_qty')
    ).filter(OrderRequest.supplier_id == supplier.id)\
     .group_by(OrderRequest.product_name)\
     .order_by(func.sum(OrderRequest.quantity).desc())\
     .limit(10).all()

    top_vendors = db.session.query(
        User.full_name, User.phone,
        func.count(OrderRequest.id).label('order_count')
    ).join(OrderRequest, OrderRequest.vendor_id == User.id)\
     .filter(OrderRequest.supplier_id == supplier.id)\
     .group_by(User.id)\
     .order_by(func.count(OrderRequest.id).desc())\
     .limit(5).all()

    months = []
    monthly_counts = []
    for i in range(11, -1, -1):
        month_start = date.today().replace(day=1) - timedelta(days=30*i)
        month_end = (month_start + timedelta(days=31)).replace(day=1)
        count = OrderRequest.query.filter(
            OrderRequest.supplier_id == supplier.id,
            OrderRequest.created_at >= month_start,
            OrderRequest.created_at < month_end
        ).count()
        months.append(month_start.strftime('%b %y'))
        monthly_counts.append(count)

    return render_template('supplier/analytics.html',
                           top_requests=top_requests,
                           top_vendors=top_vendors,
                           months=months,
                           monthly_counts=monthly_counts)