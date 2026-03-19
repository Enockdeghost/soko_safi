from flask import jsonify, request, abort, current_app
from flask_login import login_required, current_user
from app import db
from app.models import User, Product, Sale, Expense, ExpenseCategory, Notification, Voucher, Payment
from app.routes import api_bp as bp
from datetime import datetime, date
from sqlalchemy import func
import secrets
import hmac

# ----------------------------------------------------------------------
# Authentication for offline sync (token-based)
# ----------------------------------------------------------------------
def authenticate_token():
    """Extract and validate API token from header."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    token = auth_header.split(' ')[1]
    # In production, use a database of tokens or JWT.
    # For simplicity, we treat token as user_id (insecure – replace with proper method)
    # A better approach: store hashed tokens in User model.
    user = User.query.filter_by(api_token=token).first()
    return user

# Add an api_token column to User model (run migration)
# class User(db.Model):
#     api_token = db.Column(db.String(64), unique=True, index=True)
#     def generate_api_token(self):
#         self.api_token = secrets.token_urlsafe(32)

# ----------------------------------------------------------------------
# Helper: resolve conflicts using timestamps
# ----------------------------------------------------------------------
def resolve_sale_conflict(local_sale, server_sale):
    """Return True if local_sale is newer and should replace server_sale."""
    if not server_sale:
        return True
    # Compare timestamps (assume local_sale['timestamp'] is ISO string)
    local_time = datetime.fromisoformat(local_sale['timestamp'])
    return local_time > server_sale.timestamp

# ----------------------------------------------------------------------
# SYNC ENDPOINT (with conflict resolution)
# ----------------------------------------------------------------------
@bp.route('/sync', methods=['POST'])
def sync():
    """
    Synchronise offline data.
    Expects JSON:
    {
        "sales": [...],
        "expenses": [...],
        "products": [...],
        "vendor_id": 123   (if using simple token)
    }
    Returns summary of synced items and conflicts.
    """
    # Authenticate
    user = authenticate_token()
    if not user:
        # Fallback: allow vendor_id in body (insecure, for demo only)
        vendor_id = request.get_json().get('vendor_id')
        user = User.query.get(vendor_id) if vendor_id else None
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    response = {
        'synced_sales': 0,
        'synced_expenses': 0,
        'synced_products': 0,
        'conflicts': []
    }

    # --------------------------------------------------------------
    # Process sales
    # --------------------------------------------------------------
    for sale_data in data.get('sales', []):
        try:
            # Basic validation
            required = ['product_id', 'quantity', 'total_price', 'timestamp']
            if not all(k in sale_data for k in required):
                response['conflicts'].append({'type': 'sale', 'data': sale_data, 'reason': 'Missing fields'})
                continue

            # Check product ownership
            product = Product.query.get(sale_data['product_id'])
            if not product or product.shop.vendor_id != user.id:
                response['conflicts'].append({'type': 'sale', 'data': sale_data, 'reason': 'Invalid product'})
                continue

            # Look for existing sale (if client sent an id)
            existing = None
            if 'id' in sale_data:
                existing = Sale.query.get(sale_data['id'])
                if existing and existing.user_id != user.id:
                    response['conflicts'].append({'type': 'sale', 'data': sale_data, 'reason': 'Sale belongs to another user'})
                    continue

            # Conflict resolution
            if existing and not resolve_sale_conflict(sale_data, existing):
                # Server version is newer, skip
                continue

            # Prepare sale object
            if existing:
                sale = existing
            else:
                sale = Sale(user_id=user.id)

            sale.product_id = sale_data['product_id']
            sale.quantity = sale_data['quantity']
            sale.total_price = sale_data['total_price']
            sale.payment_method = sale_data.get('payment_method', 'cash')
            sale.timestamp = datetime.fromisoformat(sale_data['timestamp'])
            sale.synced = True

            # Update product stock (decrement)
            if not existing:  # only decrement once
                product.quantity -= sale.quantity

            db.session.add(sale)
            response['synced_sales'] += 1
        except Exception as e:
            response['conflicts'].append({'type': 'sale', 'data': sale_data, 'reason': str(e)})

    # --------------------------------------------------------------
    # Process expenses
    # --------------------------------------------------------------
    for exp_data in data.get('expenses', []):
        try:
            required = ['category_id', 'amount', 'date']
            if not all(k in exp_data for k in required):
                response['conflicts'].append({'type': 'expense', 'data': exp_data, 'reason': 'Missing fields'})
                continue

            # Verify category belongs to user's shop
            category = ExpenseCategory.query.get(exp_data['category_id'])
            if not category or category.shop.vendor_id != user.id:
                response['conflicts'].append({'type': 'expense', 'data': exp_data, 'reason': 'Invalid category'})
                continue

            existing = None
            if 'id' in exp_data:
                existing = Expense.query.get(exp_data['id'])
                if existing and existing.user_id != user.id:
                    response['conflicts'].append({'type': 'expense', 'data': exp_data, 'reason': 'Expense belongs to another user'})
                    continue

            # Simple conflict: use client timestamp (if provided) or ignore
            # We'll just overwrite if client timestamp is newer
            if existing:
                # Use 'timestamp' field from client if present
                client_time = datetime.fromisoformat(exp_data.get('timestamp', '2000-01-01'))
                if client_time <= existing.timestamp:
                    continue
                expense = existing
            else:
                expense = Expense(user_id=user.id)

            expense.category_id = exp_data['category_id']
            expense.amount = exp_data['amount']
            expense.description = exp_data.get('description', '')
            expense.date = datetime.strptime(exp_data['date'], '%Y-%m-%d').date()
            if 'timestamp' in exp_data:
                expense.timestamp = datetime.fromisoformat(exp_data['timestamp'])
            expense.synced = True

            db.session.add(expense)
            response['synced_expenses'] += 1
        except Exception as e:
            response['conflicts'].append({'type': 'expense', 'data': exp_data, 'reason': str(e)})

    # --------------------------------------------------------------
    # Process product updates (e.g., price changes, stock adjustments)
    # --------------------------------------------------------------
    for prod_data in data.get('products', []):
        try:
            required = ['id', 'name', 'price', 'quantity']
            if not all(k in prod_data for k in required):
                response['conflicts'].append({'type': 'product', 'data': prod_data, 'reason': 'Missing fields'})
                continue

            product = Product.query.get(prod_data['id'])
            if not product or product.shop.vendor_id != user.id:
                response['conflicts'].append({'type': 'product', 'data': prod_data, 'reason': 'Invalid product'})
                continue

            # Use client's updated_at if newer
            client_updated = datetime.fromisoformat(prod_data.get('updated_at', '2000-01-01'))
            if client_updated <= product.updated_at:
                continue

            product.name = prod_data['name']
            product.price = prod_data['price']
            product.quantity = prod_data['quantity']
            product.unit = prod_data.get('unit', product.unit)
            product.low_stock_threshold = prod_data.get('low_stock_threshold', product.low_stock_threshold)
            product.updated_at = datetime.utcnow()

            db.session.add(product)
            response['synced_products'] += 1
        except Exception as e:
            response['conflicts'].append({'type': 'product', 'data': prod_data, 'reason': str(e)})

    db.session.commit()
    return jsonify(response)

# ----------------------------------------------------------------------
# GET PRODUCTS for offline catalog (by shop_id)
# ----------------------------------------------------------------------
@bp.route('/products/<int:shop_id>', methods=['GET'])
def get_products(shop_id):
    """Return all products of a given shop (public)."""
    products = Product.query.filter_by(shop_id=shop_id).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'quantity': p.quantity,
        'unit': p.unit,
        'expiry_date': p.expiry_date.isoformat() if p.expiry_date else None,
        'updated_at': p.updated_at.isoformat()
    } for p in products])

# ----------------------------------------------------------------------
# GET expense categories for a vendor
# ----------------------------------------------------------------------
@bp.route('/expense-categories', methods=['GET'])
@login_required
def get_expense_categories():
    """Return expense categories for current vendor's shop."""
    if current_user.role != 'vendor':
        return jsonify({'error': 'Forbidden'}), 403
    shop = current_user.shop
    if not shop:
        return jsonify({'error': 'No shop'}), 404
    cats = ExpenseCategory.query.filter_by(shop_id=shop.id).all()
    return jsonify([{'id': c.id, 'name': c.name} for c in cats])

# ----------------------------------------------------------------------
# MOBILE MONEY STUB (charge)
# ----------------------------------------------------------------------
@bp.route('/mobile-money/charge', methods=['POST'])
def mobile_money_charge():
    """
    Simulate mobile money payment.
    Expected JSON: { "phone": "2557...", "amount": 5000, "reference": "order123" }
    """
    data = request.get_json()
    if not data or 'phone' not in data or 'amount' not in data:
        return jsonify({'error': 'Missing phone or amount'}), 400

    # Simulate processing
    success = True  # In reality call API
    if success:
        transaction_id = f"TXN{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{secrets.randbelow(1000)}"
        # Optionally record payment
        if 'user_id' in data:
            payment = Payment(
                user_id=data['user_id'],
                amount=data['amount'],
                reference=data.get('reference', ''),
                status='completed',
                method='mpesa'
            )
            db.session.add(payment)
            db.session.commit()
        return jsonify({'success': True, 'transaction_id': transaction_id})
    else:
        return jsonify({'success': False, 'message': 'Payment failed'}), 500

# ----------------------------------------------------------------------
# VOUCHER REDEMPTION via API (for POS)
# ----------------------------------------------------------------------
@bp.route('/vouchers/redeem', methods=['POST'])
@login_required
def redeem_voucher_api():
    """Redeem a voucher using JSON."""
    if current_user.role != 'vendor':
        return jsonify({'error': 'Only vendors can redeem'}), 403
    data = request.get_json()
    if not data or 'code' not in data:
        return jsonify({'error': 'Missing voucher code'}), 400

    voucher = Voucher.query.filter_by(code=data['code'].upper(), status='active').first()
    if not voucher or (voucher.expiry_date and voucher.expiry_date < date.today()):
        return jsonify({'error': 'Invalid or expired voucher'}), 400

    # Redeem
    voucher.status = 'redeemed'
    voucher.redeemed_at = datetime.utcnow()
    voucher.redeemed_by_vendor = current_user.id
    voucher.redeemed_at_shop = current_user.shop.id
    db.session.add(voucher)
    db.session.commit()

    return jsonify({
        'success': True,
        'amount': voucher.amount,
        'beneficiary': voucher.beneficiary_name
    })

# ----------------------------------------------------------------------
# DASHBOARD DATA for vendors
# ----------------------------------------------------------------------
@bp.route('/dashboard/vendor')
@login_required
def vendor_dashboard_data():
    """JSON data for vendor dashboard charts (last 7 days)."""
    if current_user.role != 'vendor':
        return jsonify({'error': 'Forbidden'}), 403

    # Daily sales
    sales_data = db.session.query(
        func.date(Sale.timestamp).label('date'),
        func.sum(Sale.total_price).label('total')
    ).filter(Sale.user_id == current_user.id)\
     .group_by(func.date(Sale.timestamp))\
     .order_by(func.date(Sale.timestamp).desc())\
     .limit(7).all()

    # Low stock alerts
    low_stock_count = Product.query.filter(
        Product.shop_id == current_user.shop.id,
        Product.quantity <= Product.low_stock_threshold
    ).count()

    # Top 5 products
    top_products = db.session.query(
        Product.name,
        func.sum(Sale.quantity).label('qty')
    ).join(Sale).filter(Sale.user_id == current_user.id)\
     .group_by(Product.id)\
     .order_by(func.sum(Sale.quantity).desc())\
     .limit(5).all()

    return jsonify({
        'sales': [{'date': str(s.date), 'total': s.total} for s in sales_data],
        'low_stock': low_stock_count,
        'top_products': [{'name': p.name, 'quantity': p.qty} for p in top_products]
    })

# ----------------------------------------------------------------------
# DASHBOARD DATA for suppliers
# ----------------------------------------------------------------------
@bp.route('/dashboard/supplier')
@login_required
def supplier_dashboard_data():
    """JSON data for supplier analytics."""
    if current_user.role != 'supplier':
        return jsonify({'error': 'Forbidden'}), 403
    supplier = current_user.supplier_profile
    if not supplier:
        return jsonify({'error': 'Supplier profile not found'}), 404

    # Most requested products
    top_requests = db.session.query(
        OrderRequest.product_name,
        func.sum(OrderRequest.quantity).label('total_qty')
    ).filter(OrderRequest.supplier_id == supplier.id)\
     .group_by(OrderRequest.product_name)\
     .order_by(func.sum(OrderRequest.quantity).desc())\
     .limit(10).all()

    # Orders by status
    status_counts = db.session.query(
        OrderRequest.status, func.count(OrderRequest.id)
    ).filter(OrderRequest.supplier_id == supplier.id)\
     .group_by(OrderRequest.status).all()

    return jsonify({
        'top_requests': [{'product': r[0], 'quantity': r[1]} for r in top_requests],
        'status_counts': {s: c for s, c in status_counts}
    })

# ----------------------------------------------------------------------
# GET NOTIFICATIONS for current user
# ----------------------------------------------------------------------
@bp.route('/notifications')
@login_required
def get_notifications():
    """Return unread notifications for the logged-in user."""
    notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False)\
                               .order_by(Notification.created_at.desc()).all()
    return jsonify([{
        'id': n.id,
        'type': n.type,
        'message': n.message,
        'created_at': n.created_at.isoformat()
    } for n in notifs])

@bp.route('/notifications/<int:id>/read', methods=['POST'])
@login_required
def mark_notification_read(id):
    notif = Notification.query.get_or_404(id)
    if notif.user_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True})