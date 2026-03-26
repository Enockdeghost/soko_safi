from flask import render_template, redirect, url_for, flash, request, abort, send_file, Response
from flask_login import login_required, current_user
from app import db
from app.models import (
    User, Shop, Product, Sale, Expense, ExpenseCategory,
    OrderRequest, Supplier, Voucher, VoucherRedemption,
    TrainingProgram, TrainingApplication, GrantApplication,
    Notification, TransactionLog, Order, Promotion, Cart, Category
)
from app.forms import (
    ProductForm, SaleForm, ExpenseForm, ExpenseCategoryForm,
    OrderRequestForm, DateRangeForm, GrantApplicationForm
)
from app.decorators import vendor_required
from app.routes import vendor_bp as bp
from app.utils import (
    send_sms, create_notification, log_transaction,
    generate_pdf_report, mobile_money_charge
)
from datetime import datetime, date, timedelta
from sqlalchemy import func
import io
import csv

def get_shop_or_abort():
    shop = current_user.shop
    if not shop:
        flash('Tafadhali kwanza anzisha duka lako.', 'warning')
        return redirect(url_for('auth.setup_wizard'))
    return shop

# ----------------------------------------------------------------------
# DASHBOARD (with all advanced metrics)
# ----------------------------------------------------------------------
@bp.route('/dashboard')
@login_required
@vendor_required
def dashboard():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop

    today = date.today()
    yesterday = today - timedelta(days=1)
    thirty_days_ago = today - timedelta(days=30)

    # Today's totals
    today_sales = db.session.query(func.sum(Sale.total_price)).filter(
        Sale.user_id == current_user.id,
        func.date(Sale.timestamp) == today
    ).scalar() or 0

    today_expenses = db.session.query(func.sum(Expense.amount)).filter(
        Expense.user_id == current_user.id,
        Expense.date == today
    ).scalar() or 0

    today_profit = today_sales - today_expenses

    # Yesterday's totals
    yesterday_sales = db.session.query(func.sum(Sale.total_price)).filter(
        Sale.user_id == current_user.id,
        func.date(Sale.timestamp) == yesterday
    ).scalar() or 0

    yesterday_expenses = db.session.query(func.sum(Expense.amount)).filter(
        Expense.user_id == current_user.id,
        Expense.date == yesterday
    ).scalar() or 0

    sales_change = ((today_sales - yesterday_sales) / yesterday_sales * 100) if yesterday_sales else 0
    expense_change = ((today_expenses - yesterday_expenses) / yesterday_expenses * 100) if yesterday_expenses else 0
    profit_margin = (today_profit / today_sales * 100) if today_sales else 0

    # Daily target (stored in shop, default 100000)
    daily_target = getattr(shop, 'daily_target', 100000)
    target_progress = min(100, (today_sales / daily_target * 100)) if daily_target else 0

    # Low stock
    low_stock_count = Product.query.filter(
        Product.shop_id == shop.id,
        Product.quantity <= Product.low_stock_threshold
    ).count()

    low_stock_products = Product.query.filter(
        Product.shop_id == shop.id,
        Product.quantity <= Product.low_stock_threshold
    ).all()

    # Quick action dropdowns
    products = Product.query.filter_by(shop_id=shop.id).order_by(Product.name).all()
    expense_categories = ExpenseCategory.query.filter_by(shop_id=shop.id).all()

    # Top products (last 30 days)
    top_products = db.session.query(
        Product.name,
        func.sum(Sale.quantity).label('quantity'),
        func.sum(Sale.total_price).label('revenue')
    ).join(Sale).filter(
        Sale.user_id == current_user.id,
        Sale.timestamp >= thirty_days_ago,
        Product.shop_id == shop.id
    ).group_by(Product.id).order_by(func.sum(Sale.quantity).desc()).limit(5).all()

    # Product profitability (simplified, assumes cost = 70% of price if not set)
    product_profitability = []
    for p in products[:5]:
        total_sales = db.session.query(func.sum(Sale.total_price)).filter(
            Sale.product_id == p.id,
            Sale.timestamp >= thirty_days_ago
        ).scalar() or 0
        # if you have cost field, use it; else estimate
        cost = getattr(p, 'cost', p.price * 0.7)
        total_qty = db.session.query(func.sum(Sale.quantity)).filter(
            Sale.product_id == p.id,
            Sale.timestamp >= thirty_days_ago
        ).scalar() or 0
        profit = total_sales - (cost * total_qty)
        product_profitability.append({
            'name': p.name,
            'profit': profit,
            'margin': (profit / total_sales * 100) if total_sales else 0
        })

    # Weekly sales (last 4 weeks)
    weekly_labels = []
    weekly_sales = []
    for i in range(3, -1, -1):
        week_start = today - timedelta(weeks=i+1)
        week_end = today - timedelta(weeks=i)
        total = db.session.query(func.sum(Sale.total_price)).filter(
            Sale.user_id == current_user.id,
            Sale.timestamp >= week_start,
            Sale.timestamp < week_end
        ).scalar() or 0
        weekly_labels.append(f'Wiki {4-i}')
        weekly_sales.append(total)

    # Daily sales/expenses for last 7 days
    days = []
    daily_sales = []
    daily_expenses = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        days.append(day.strftime('%a'))
        daily_sales.append(db.session.query(func.sum(Sale.total_price)).filter(
            Sale.user_id == current_user.id,
            func.date(Sale.timestamp) == day
        ).scalar() or 0)
        daily_expenses.append(db.session.query(func.sum(Expense.amount)).filter(
            Expense.user_id == current_user.id,
            Expense.date == day
        ).scalar() or 0)

    # Cash flow forecast (next 7 days)
    avg_daily_sales = db.session.query(func.avg(Sale.total_price)).filter(
        Sale.user_id == current_user.id,
        Sale.timestamp >= thirty_days_ago
    ).scalar() or 0

    avg_daily_expenses = db.session.query(func.avg(Expense.amount)).filter(
        Expense.user_id == current_user.id,
        Expense.date >= thirty_days_ago
    ).scalar() or 0

    projection_dates = [(today + timedelta(days=i)).strftime('%a') for i in range(1, 8)]
    projection = []
    balance = today_profit
    for _ in range(7):
        balance += avg_daily_sales - avg_daily_expenses
        projection.append(max(balance, 0))

    # Automated reorder suggestions
    reorder_suggestions = []
    for p in products:
        avg_daily = db.session.query(func.avg(Sale.quantity)).filter(
            Sale.product_id == p.id,
            Sale.timestamp >= thirty_days_ago
        ).scalar() or 0
        if avg_daily > 0 and p.quantity / avg_daily <= 7:
            reorder_suggestions.append({
                'product': p,
                'days_left': round(p.quantity / avg_daily, 1),
                'suggested_qty': round(avg_daily * 14)
            })

    # Recent activities
    recent_sales = Sale.query.filter_by(user_id=current_user.id).order_by(Sale.timestamp.desc()).limit(5).all()
    recent_expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).limit(5).all()
    recent_activities = []
    for s in recent_sales:
        recent_activities.append({
            'type': 'sale',
            'description': f"Umeuza {s.quantity} {s.product.unit} {s.product.name}",
            'time': s.timestamp.strftime('%H:%M')
        })
    for e in recent_expenses:
        recent_activities.append({
            'type': 'expense',
            'description': f"Gharama {e.category.name} TZS {e.amount:,.0f}",
            'time': e.date.strftime('%d/%m')
        })
    recent_activities = sorted(recent_activities, key=lambda x: x['time'], reverse=True)[:10]

    # Expense breakdown (pie chart)
    expense_breakdown = db.session.query(
        ExpenseCategory.name,
        func.sum(Expense.amount).label('total')
    ).join(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.date >= thirty_days_ago
    ).group_by(ExpenseCategory.id).all()
    expense_labels = [item.name for item in expense_breakdown]
    expense_data = [item.total for item in expense_breakdown]

    # 7-day sales chart
    sales_labels = []
    sales_data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        total = db.session.query(func.sum(Sale.total_price)).filter(
            Sale.user_id == current_user.id,
            func.date(Sale.timestamp) == day
        ).scalar() or 0
        sales_labels.append(day.strftime('%d/%m'))
        sales_data.append(total)

    return render_template(
        'vendor/dashboard.html',
        shop=shop,
        today_sales=today_sales,
        today_expenses=today_expenses,
        today_profit=today_profit,
        sales_change=round(sales_change, 1),
        expense_change=round(expense_change, 1),
        profit_margin=round(profit_margin, 1),
        daily_target=daily_target,
        target_progress=round(target_progress, 1),
        low_stock_count=low_stock_count,
        low_stock_products=low_stock_products,
        products=products,
        expense_categories=expense_categories,
        top_products=top_products,
        product_profitability=product_profitability,
        weekly_labels=weekly_labels,
        weekly_sales=weekly_sales,
        days=days,
        daily_sales=daily_sales,
        daily_expenses=daily_expenses,
        projection_dates=projection_dates,
        projection=projection,
        reorder_suggestions=reorder_suggestions,
        recent_activities=recent_activities,
        expense_labels=expense_labels,
        expense_data=expense_data,
        sales_labels=sales_labels,
        sales_data=sales_data
    )

# ----------------------------------------------------------------------
# QUICK ACTIONS
# ----------------------------------------------------------------------
@bp.route('/quick-sale', methods=['POST'])
@login_required
@vendor_required
def quick_sale():
    product_id = request.form.get('product_id')
    quantity = float(request.form.get('quantity', 0))
    product = Product.query.get_or_404(product_id)
    if product.shop.vendor_id != current_user.id:
        abort(403)
    if product.quantity < quantity:
        flash('Idadi haitoshi!', 'danger')
        return redirect(url_for('vendor.dashboard'))
    total = product.price * quantity
    sale = Sale(
        product_id=product.id,
        user_id=current_user.id,
        quantity=quantity,
        total_price=total,
        payment_method='cash'
    )
    product.quantity -= quantity
    db.session.add(sale)
    db.session.commit()
    log_transaction(current_user.id, 'quick_sale', f'Sold {quantity} {product.name}', request.remote_addr)
    if product.quantity <= product.low_stock_threshold:
        flash(f'Tahadhari: {product.name} inakaribia kuisha!', 'warning')
    flash('Mauzo yamehifadhiwa!', 'success')
    return redirect(url_for('vendor.dashboard'))

@bp.route('/quick-expense', methods=['POST'])
@login_required
@vendor_required
def quick_expense():
    category_id = request.form.get('category_id')
    amount = float(request.form.get('amount', 0))
    cat = ExpenseCategory.query.get_or_404(category_id)
    if cat.shop.vendor_id != current_user.id:
        abort(403)
    expense = Expense(
        user_id=current_user.id,
        category_id=category_id,
        amount=amount,
        date=date.today()
    )
    db.session.add(expense)
    db.session.commit()
    log_transaction(current_user.id, 'quick_expense', f'Added expense TZS {amount}', request.remote_addr)
    flash('Gharama imeongezwa!', 'success')
    return redirect(url_for('vendor.dashboard'))

# ----------------------------------------------------------------------
# INVENTORY MANAGEMENT
# ----------------------------------------------------------------------
@bp.route('/inventory')
@login_required
@vendor_required
def inventory():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop
    products = Product.query.filter_by(shop_id=shop.id).order_by(Product.name).all()
    return render_template('vendor/inventory.html', products=products)


@bp.route('/inventory/export')
@login_required
@vendor_required
def export_inventory():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop
    products = Product.query.filter_by(shop_id=shop.id).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'price', 'quantity', 'unit', 'expiry_date', 'low_stock_threshold', 'description', 'barcode', 'category_id'])
    for p in products:
        writer.writerow([
            p.name, p.price, p.quantity, p.unit,
            p.expiry_date.strftime('%Y-%m-%d') if p.expiry_date else '',
            p.low_stock_threshold, p.description or '',
            p.barcode or '', p.category_id or ''
        ])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        as_attachment=True,
        download_name='inventory.csv',
        mimetype='text/csv'
    )

@bp.route('/inventory/import', methods=['POST'])
@login_required
@vendor_required
def import_inventory():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop
    file = request.files.get('file')
    if not file:
        flash('Tafadhali chagua faili la CSV.', 'danger')
        return redirect(url_for('vendor.inventory'))
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        for row in csv_input:
            product = Product(
                shop_id=shop.id,
                name=row['name'],
                price=float(row['price']),
                quantity=float(row['quantity']),
                unit=row['unit'],
                expiry_date=datetime.strptime(row['expiry_date'], '%Y-%m-%d').date() if row.get('expiry_date') else None,
                low_stock_threshold=float(row['low_stock_threshold']) if row.get('low_stock_threshold') else 5,
                description=row.get('description', ''),
                barcode=row.get('barcode', '') or None,
                category_id=int(row['category_id']) if row.get('category_id') and row['category_id'].strip() else None
            )
            db.session.add(product)
        db.session.commit()
        flash('Bidhaa zimeingizwa kwa mafanikio.', 'success')
    except Exception as e:
        flash(f'Kuna hitilafu katika faili: {str(e)}', 'danger')
    return redirect(url_for('vendor.inventory'))

@bp.route('/product/add', methods=['GET', 'POST'])
@login_required
@vendor_required
def add_product():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop
    form = ProductForm()
    if form.validate_on_submit():
        product = Product(
            shop_id=shop.id,
            name=form.name.data,
            price=form.price.data,
            quantity=form.quantity.data,
            unit=form.unit.data,
            expiry_date=form.expiry_date.data,
            low_stock_threshold=form.low_stock_threshold.data
        )
        db.session.add(product)
        db.session.commit()
        log_transaction(current_user.id, 'add_product', f'Added product: {product.name}', request.remote_addr)
        flash('Bidhaa imeongezwa kwenye stock.', 'success')
        return redirect(url_for('vendor.inventory'))
    return render_template('vendor/add_product.html', form=form)

@bp.route('/product/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@vendor_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    if product.shop.vendor_id != current_user.id:
        abort(403)
    form = ProductForm(obj=product)
    if form.validate_on_submit():
        product.name = form.name.data
        product.price = form.price.data
        product.quantity = form.quantity.data
        product.unit = form.unit.data
        product.expiry_date = form.expiry_date.data
        product.low_stock_threshold = form.low_stock_threshold.data
        product.updated_at = datetime.utcnow()
        db.session.commit()
        log_transaction(current_user.id, 'edit_product', f'Edited product: {product.name}', request.remote_addr)
        flash('Bidhaa imesasishwa.', 'success')
        return redirect(url_for('vendor.inventory'))
    return render_template('vendor/edit_product.html', form=form, product=product)

@bp.route('/product/delete/<int:id>')
@login_required
@vendor_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    if product.shop.vendor_id != current_user.id:
        abort(403)
    db.session.delete(product)
    db.session.commit()
    log_transaction(current_user.id, 'delete_product', f'Deleted product ID {id}', request.remote_addr)
    flash('Bidhaa imefutwa.', 'success')
    return redirect(url_for('vendor.inventory'))

# ----------------------------------------------------------------------
# SALES
# ----------------------------------------------------------------------
@bp.route('/sales', methods=['GET', 'POST'])
@login_required
@vendor_required
def sales():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop

    form = SaleForm()
    products = Product.query.filter_by(shop_id=shop.id).order_by(Product.name).all()
    form.product_id.choices = [(p.id, f"{p.name} - TZS {p.price} ({p.quantity} {p.unit})") for p in products]

    if form.validate_on_submit():
        product = Product.query.get(form.product_id.data)
        if product.quantity < form.quantity.data:
            flash('Idadi haitoshi kwenye stock!', 'danger')
            return redirect(url_for('vendor.sales'))

        total_price = product.price * form.quantity.data
        sale = Sale(
            product_id=product.id,
            user_id=current_user.id,
            quantity=form.quantity.data,
            total_price=total_price,
            payment_method=form.payment_method.data
        )
        product.quantity -= form.quantity.data
        db.session.add(sale)
        db.session.commit()

        log_transaction(current_user.id, 'record_sale',
                        f'Sold {sale.quantity} {product.unit} of {product.name} for TZS {total_price}',
                        request.remote_addr)

        if product.quantity <= product.low_stock_threshold:
            msg = f"Tahadhari: {product.name} imekaribia kuisha. Idadi iliyobaki: {product.quantity}"
            flash(msg, 'warning')
            create_notification(current_user.id, 'low_stock', msg)
            send_sms(current_user.phone, msg)

        flash('Mauzo yamehifadhiwa.', 'success')
        return redirect(url_for('vendor.sales'))

    sales_list = Sale.query.filter_by(user_id=current_user.id).order_by(Sale.timestamp.desc()).all()
    return render_template('vendor/sales.html', form=form, sales=sales_list, products=products)

@bp.route('/sales/delete/<int:id>')
@login_required
@vendor_required
def delete_sale(id):
    sale = Sale.query.get_or_404(id)
    if sale.user_id != current_user.id:
        abort(403)
    db.session.delete(sale)
    db.session.commit()
    log_transaction(current_user.id, 'delete_sale', f'Deleted sale ID {id}', request.remote_addr)
    flash('Rekodi ya mauzo imefutwa.', 'success')
    return redirect(url_for('vendor.sales'))

# ----------------------------------------------------------------------
# EXPENSES
# ----------------------------------------------------------------------
@bp.route('/expenses', methods=['GET', 'POST'])
@login_required
@vendor_required
def expenses():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop
    form = ExpenseForm()
    form.category_id.choices = [(c.id, c.name) for c in ExpenseCategory.query.filter_by(shop_id=shop.id).all()]

    if form.validate_on_submit():
        expense = Expense(
            user_id=current_user.id,
            category_id=form.category_id.data,
            amount=form.amount.data,
            description=form.description.data,
            date=form.date.data
        )
        db.session.add(expense)
        db.session.commit()
        log_transaction(current_user.id, 'add_expense',
                        f'Expense TZS {expense.amount} for {expense.category.name}',
                        request.remote_addr)
        flash('Gharama imeongezwa.', 'success')
        return redirect(url_for('vendor.expenses'))

    expenses_list = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
    return render_template('vendor/expenses.html', form=form, expenses=expenses_list)

@bp.route('/expense/delete/<int:id>')
@login_required
@vendor_required
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    if expense.user_id != current_user.id:
        abort(403)
    db.session.delete(expense)
    db.session.commit()
    flash('Gharama imefutwa.', 'success')
    return redirect(url_for('vendor.expenses'))

# ----------------------------------------------------------------------
# EXPENSE CATEGORIES
# ----------------------------------------------------------------------
@bp.route('/expense-categories', methods=['GET', 'POST'])
@login_required
@vendor_required
def expense_categories():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop
    form = ExpenseCategoryForm()
    if form.validate_on_submit():
        cat = ExpenseCategory(shop_id=shop.id, name=form.name.data)
        db.session.add(cat)
        db.session.commit()
        flash('Aina ya gharama imeongezwa.', 'success')
        return redirect(url_for('vendor.expense_categories'))

    categories = ExpenseCategory.query.filter_by(shop_id=shop.id).all()
    return render_template('vendor/expense_categories.html', form=form, categories=categories)

@bp.route('/expense-category/delete/<int:id>')
@login_required
@vendor_required
def delete_expense_category(id):
    cat = ExpenseCategory.query.get_or_404(id)
    if cat.shop.vendor_id != current_user.id:
        abort(403)
    if Expense.query.filter_by(category_id=id).first():
        flash('Aina hii ina gharama zilizohifadhiwa. Badilisha gharama hizo kwanza.', 'danger')
        return redirect(url_for('vendor.expense_categories'))
    db.session.delete(cat)
    db.session.commit()
    flash('Aina ya gharama imefutwa.', 'success')
    return redirect(url_for('vendor.expense_categories'))

# ----------------------------------------------------------------------
# SUPPLIER ORDERS
# ----------------------------------------------------------------------
@bp.route('/supplier-orders', methods=['GET', 'POST'])
@login_required
@vendor_required
def supplier_orders():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop
    form = OrderRequestForm()
    suppliers = Supplier.query.filter_by(verified=True).all()
    form.supplier_id.choices = [(s.id, s.business_name) for s in suppliers]

    if form.validate_on_submit():
        order = OrderRequest(
            vendor_id=current_user.id,
            supplier_id=form.supplier_id.data,
            product_name=form.product_name.data,
            quantity=form.quantity.data,
            unit=form.unit.data
        )
        db.session.add(order)
        db.session.commit()
        log_transaction(current_user.id, 'order_request',
                        f'Ordered {order.quantity} {order.unit} of {order.product_name} from supplier {order.supplier_id}',
                        request.remote_addr)
        supplier_user = User.query.join(Supplier).filter(Supplier.id == order.supplier_id).first()
        if supplier_user:
            create_notification(supplier_user.id, 'new_order',
                                f'Ombi jipya la {order.product_name} kutoka {shop.name}')
        flash('Ombi limewasilishwa kwa msambazaji.', 'success')
        return redirect(url_for('vendor.supplier_orders'))

    orders = OrderRequest.query.filter_by(vendor_id=current_user.id).order_by(OrderRequest.created_at.desc()).all()
    return render_template('vendor/supplier_orders.html', form=form, orders=orders, suppliers=suppliers)

@bp.route('/supplier-order/cancel/<int:id>')
@login_required
@vendor_required
def cancel_supplier_order(id):
    order = OrderRequest.query.get_or_404(id)
    if order.vendor_id != current_user.id:
        abort(403)
    if order.status not in ['pending', 'accepted']:
        flash('Huwezi kughairi ombi lililokwisha timizwa.', 'danger')
    else:
        order.status = 'cancelled'
        order.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Ombi limeghairiwa.', 'success')
    return redirect(url_for('vendor.supplier_orders'))

# ----------------------------------------------------------------------
# REPORTS
# ----------------------------------------------------------------------
@bp.route('/reports', methods=['GET', 'POST'])
@login_required
@vendor_required
def reports():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop
    form = DateRangeForm()
    if form.validate_on_submit():
        start = form.start_date.data
        end = form.end_date.data
        sales = Sale.query.filter(
            Sale.user_id == current_user.id,
            func.date(Sale.timestamp) >= start,
            func.date(Sale.timestamp) <= end
        ).order_by(Sale.timestamp).all()
        total_sales = sum(s.total_price for s in sales)

        expenses = Expense.query.filter(
            Expense.user_id == current_user.id,
            Expense.date >= start,
            Expense.date <= end
        ).order_by(Expense.date).all()
        total_expenses = sum(e.amount for e in expenses)

        top_products = db.session.query(
            Product.name,
            func.sum(Sale.quantity).label('total_qty'),
            func.sum(Sale.total_price).label('total')
        ).join(Sale).filter(
            Sale.user_id == current_user.id,
            func.date(Sale.timestamp) >= start,
            func.date(Sale.timestamp) <= end
        ).group_by(Product.id).order_by(func.sum(Sale.quantity).desc()).limit(5).all()

        return render_template('vendor/report_results.html',
                               start=start, end=end,
                               sales=sales, total_sales=total_sales,
                               expenses=expenses, total_expenses=total_expenses,
                               top_products=top_products,
                               profit=total_sales - total_expenses)
    return render_template('vendor/reports.html', form=form)

@bp.route('/export/pdf')
@login_required
@vendor_required
def export_pdf():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop
    end = date.today()
    start = end - timedelta(days=30)

    sales = Sale.query.filter(
        Sale.user_id == current_user.id,
        func.date(Sale.timestamp) >= start,
        func.date(Sale.timestamp) <= end
    ).all()

    expenses = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date >= start,
        Expense.date <= end
    ).all()

    lines = [f"Ripoti ya Mauzo na Gharama: {start} hadi {end}"]
    lines.append("")
    lines.append("MAUZO:")
    total_sales = 0
    for s in sales:
        lines.append(f"{s.timestamp.strftime('%Y-%m-%d %H:%M')} - {s.product.name} x{s.quantity} {s.product.unit} = TZS {s.total_price}")
        total_sales += s.total_price
    lines.append(f"Jumla ya Mauzo: TZS {total_sales}")
    lines.append("")
    lines.append("GHARAMA:")
    total_expenses = 0
    for e in expenses:
        lines.append(f"{e.date} - {e.category.name}: TZS {e.amount} ({e.description})")
        total_expenses += e.amount
    lines.append(f"Jumla ya Gharama: TZS {total_expenses}")
    lines.append("")
    lines.append(f"FAIDA: TZS {total_sales - total_expenses}")

    pdf_buffer = generate_pdf_report(lines, f"Ripoti ya {current_user.shop.name}")
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name='report.pdf',
        mimetype='application/pdf'
    )

@bp.route('/export/csv')
@login_required
@vendor_required
def export_csv():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop
    end = date.today()
    start = end - timedelta(days=30)

    sales = Sale.query.filter(
        Sale.user_id == current_user.id,
        func.date(Sale.timestamp) >= start,
        func.date(Sale.timestamp) <= end
    ).all()

    expenses = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date >= start,
        Expense.date <= end
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Aina', 'Tarehe', 'Maelezo', 'Kiasi (TZS)'])

    for s in sales:
        writer.writerow(['Mauzo', s.timestamp.strftime('%Y-%m-%d'), f"{s.product.name} x{s.quantity}", s.total_price])
    for e in expenses:
        writer.writerow(['Gharama', e.date, f"{e.category.name}: {e.description}", e.amount])

    total_sales = sum(s.total_price for s in sales)
    total_expenses = sum(e.amount for e in expenses)
    writer.writerow([])
    writer.writerow(['Jumla ya Mauzo', '', '', total_sales])
    writer.writerow(['Jumla ya Gharama', '', '', total_expenses])
    writer.writerow(['Faida', '', '', total_sales - total_expenses])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        as_attachment=True,
        download_name='report.csv',
        mimetype='text/csv'
    )

# ----------------------------------------------------------------------
# VOUCHER REDEMPTION
# ----------------------------------------------------------------------
@bp.route('/redeem-voucher', methods=['POST'])
@login_required
@vendor_required
def redeem_voucher():
    code = request.form.get('code', '').strip().upper()
    if not code:
        flash('Tafadhali ingiza namba ya vocha.', 'danger')
        return redirect(url_for('vendor.sales'))

    voucher = Voucher.query.filter_by(code=code, status='active').first()
    if not voucher or (voucher.expiry_date and voucher.expiry_date < date.today()):
        flash('Vocha si sahihi au imekwisha.', 'danger')
        return redirect(url_for('vendor.sales'))

    voucher.status = 'redeemed'
    voucher.redeemed_at = datetime.utcnow()
    voucher.redeemed_by_vendor = current_user.id
    voucher.redeemed_at_shop = current_user.shop.id
    redemption = VoucherRedemption(
        voucher_id=voucher.id,
        vendor_id=current_user.id,
        shop_id=current_user.shop.id,
        amount=voucher.amount
    )
    db.session.add(redemption)
    db.session.commit()

    log_transaction(current_user.id, 'redeem_voucher',
                    f'Redeemed voucher {code} worth TZS {voucher.amount}', request.remote_addr)
    flash(f'Vocha imetumika. Thamani: TZS {voucher.amount}', 'success')
    return redirect(url_for('vendor.sales'))

# ----------------------------------------------------------------------
# TRAININGS & GRANTS
# ----------------------------------------------------------------------
@bp.route('/trainings')
@login_required
@vendor_required
def trainings():
    programs = TrainingProgram.query.filter(TrainingProgram.start_date >= date.today()).all()
    my_applications = TrainingApplication.query.filter_by(vendor_id=current_user.id).all()
    return render_template('vendor/trainings.html', programs=programs, applications=my_applications)

@bp.route('/training/apply/<int:program_id>')
@login_required
@vendor_required
def apply_training(program_id):
    program = TrainingProgram.query.get_or_404(program_id)
    existing = TrainingApplication.query.filter_by(vendor_id=current_user.id, program_id=program_id).first()
    if existing:
        flash('Umeshatuma ombi kwa mafunzo haya.', 'info')
    else:
        app = TrainingApplication(vendor_id=current_user.id, program_id=program_id)
        db.session.add(app)
        db.session.commit()
        log_transaction(current_user.id, 'apply_training', f'Applied for training: {program.title}', request.remote_addr)
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            create_notification(admin.id, 'training_application',
                                f'{current_user.full_name} ameomba kujiunga na {program.title}')
        flash('Ombi la mafunzo limetumwa.', 'success')
    return redirect(url_for('vendor.trainings'))

@bp.route('/grants', methods=['GET', 'POST'])
@login_required
@vendor_required
def grants():
    form = GrantApplicationForm()
    if form.validate_on_submit():
        grant = GrantApplication(
            vendor_id=current_user.id,
            amount_requested=form.amount.data,
            purpose=form.purpose.data,
            business_plan=form.business_plan.data
        )
        db.session.add(grant)
        db.session.commit()
        log_transaction(current_user.id, 'apply_grant',
                        f'Applied for grant TZS {grant.amount_requested}', request.remote_addr)
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            create_notification(admin.id, 'grant_application',
                                f'{current_user.full_name} ameomba ruzuku ya TZS {grant.amount_requested}')
        flash('Ombi la ruzuku limetumwa.', 'success')
        return redirect(url_for('vendor.grants'))

    my_grants = GrantApplication.query.filter_by(vendor_id=current_user.id).order_by(GrantApplication.applied_at.desc()).all()
    return render_template('vendor/grants.html', form=form, grants=my_grants)

# ----------------------------------------------------------------------
# NOTIFICATIONS
# ----------------------------------------------------------------------
@bp.route('/notifications')
@login_required
@vendor_required
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    for n in notifs:
        if not n.is_read:
            n.is_read = True
    db.session.commit()
    return render_template('vendor/notifications.html', notifications=notifs)

# ----------------------------------------------------------------------
# SHOP EDIT
# ----------------------------------------------------------------------
@bp.route('/shop/edit', methods=['GET', 'POST'])
@login_required
@vendor_required
def edit_shop():
    shop = get_shop_or_abort()
    if isinstance(shop, Response):
        return shop
    if request.method == 'POST':
        shop.name = request.form.get('name', shop.name)
        shop.location = request.form.get('location', shop.location)
        shop.category = request.form.get('category', shop.category)
        db.session.commit()
        log_transaction(current_user.id, 'edit_shop', 'Updated shop details', request.remote_addr)
        flash('Taarifa za duka zimesasishwa.', 'success')
        return redirect(url_for('vendor.dashboard'))
    return render_template('vendor/edit_shop.html', shop=shop)

# ----------------------------------------------------------------------
# PRINT RECEIPT
# ----------------------------------------------------------------------
@bp.route('/print-receipt/<int:sale_id>')
@login_required
@vendor_required
def print_receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    if sale.user_id != current_user.id:
        abort(403)
    shop = current_user.shop
    return render_template('vendor/receipt.html', sale=sale, shop=shop, datetime=datetime)

# ----------------------------------------------------------------------
# SET DAILY TARGET
# ----------------------------------------------------------------------
@bp.route('/set-target', methods=['POST'])
@login_required
@vendor_required
def set_target():
    target = request.form.get('target', type=int)
    if target and target > 0:
        shop = current_user.shop
        shop.daily_target = target
        db.session.commit()
        flash('Lengo la kila siku limesasishwa!', 'success')
    return redirect(url_for('vendor.dashboard'))

@bp.route('/orders')
@login_required
@vendor_required
def vendor_orders():
    orders = Order.query.filter_by(vendor_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('vendor/orders.html', orders=orders)

@bp.route('/order/<int:id>')
@login_required
@vendor_required
def order_detail(id):
    order = Order.query.get_or_404(id)
    if order.vendor_id != current_user.id:
        abort(403)
    return render_template('vendor/order_detail.html', order=order)

@bp.route('/promotions', methods=['GET', 'POST'])
@login_required
@vendor_required
def promotions():
    if request.method == 'POST':
        # Create promotion
        product_id = request.form.get('product_id') or None
        discount = int(request.form.get('discount'))
        start = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
        end = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
        promo = Promotion(
            vendor_id=current_user.id,
            product_id=product_id,
            discount_percent=discount,
            start_date=start,
            end_date=end
        )
        db.session.add(promo)
        db.session.commit()
        flash('Promotion imeundwa.', 'success')
        return redirect(url_for('vendor.promotions'))
    promos = Promotion.query.filter_by(vendor_id=current_user.id).all()
    products = Product.query.filter_by(shop_id=current_user.shop.id).all()
    return render_template('vendor/promotions.html', promos=promos, products=products)