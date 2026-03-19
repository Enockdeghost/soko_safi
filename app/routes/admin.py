from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import (
    User, Shop, Supplier, Product, Sale, Expense,
    Voucher, VoucherRedemption, TrainingProgram, TrainingApplication,
    GrantApplication, Notification, TransactionLog, OrderRequest
)
from app.forms import (
    VoucherForm, BulkVoucherForm, TrainingProgramForm,
    UserEditForm, DateRangeForm
)
from app.decorators import admin_required
from app.routes import admin_bp as bp
from app.utils import send_sms, create_notification, log_transaction
from datetime import datetime, date, timedelta
from sqlalchemy import func
import secrets

# ----------------------------------------------------------------------
# ADMIN DASHBOARD
# ----------------------------------------------------------------------
@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    # Summary statistics
    total_vendors = User.query.filter_by(role='vendor').count()
    total_suppliers = User.query.filter_by(role='supplier').count()
    total_shops = Shop.query.count()
    pending_shops = Shop.query.filter_by(verified=False).count()
    pending_suppliers = Supplier.query.filter_by(verified=False).count()
    pending_grants = GrantApplication.query.filter_by(status='pending').count()
    active_vouchers = Voucher.query.filter_by(status='active').count()

    # Recent activities (last 10 transaction logs)
    recent_logs = TransactionLog.query.order_by(TransactionLog.timestamp.desc()).limit(10).all()

    # Sales summary (today)
    today_sales = db.session.query(func.sum(Sale.total_price)).filter(
        func.date(Sale.timestamp) == date.today()
    ).scalar() or 0

    # New vendors this month
    month_start = date.today().replace(day=1)
    new_vendors = User.query.filter(
        User.role == 'vendor',
        func.date(User.created_at) >= month_start
    ).count()

    return render_template(
        'admin/dashboard.html',
        total_vendors=total_vendors,
        total_suppliers=total_suppliers,
        total_shops=total_shops,
        pending_shops=pending_shops,
        pending_suppliers=pending_suppliers,
        pending_grants=pending_grants,
        active_vouchers=active_vouchers,
        recent_logs=recent_logs,
        today_sales=today_sales,
        new_vendors=new_vendors
    )

# ----------------------------------------------------------------------
# VENDOR MANAGEMENT
# ----------------------------------------------------------------------
@bp.route('/vendors')
@login_required
@admin_required
def vendors():
    page = request.args.get('page', 1, type=int)
    vendors = User.query.filter_by(role='vendor').order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('admin/vendors.html', vendors=vendors)

@bp.route('/vendor/<int:id>')
@login_required
@admin_required
def vendor_detail(id):
    vendor = User.query.get_or_404(id)
    if vendor.role != 'vendor':
        abort(404)
    shop = vendor.shop
    products = Product.query.filter_by(shop_id=shop.id).count() if shop else 0
    sales_total = db.session.query(func.sum(Sale.total_price)).filter(Sale.user_id == vendor.id).scalar() or 0
    return render_template('admin/vendor_detail.html', vendor=vendor, shop=shop, products=products, sales_total=sales_total)

@bp.route('/vendor/<int:id>/toggle-active')
@login_required
@admin_required
def toggle_vendor_active(id):
    vendor = User.query.get_or_404(id)
    if vendor.role != 'vendor':
        abort(404)
    vendor.is_active = not vendor.is_active
    db.session.commit()
    status = 'activated' if vendor.is_active else 'deactivated'
    log_transaction(current_user.id, f'vendor_{status}', f'Vendor {vendor.phone} {status}', request.remote_addr)
    flash(f'Mfanyabiashara {vendor.full_name} ame{"washwa" if vendor.is_active else "zimwa"}.', 'success')
    return redirect(url_for('admin.vendors'))

# ----------------------------------------------------------------------
# SHOP VERIFICATION
# ----------------------------------------------------------------------
@bp.route('/shops')
@login_required
@admin_required
def shops():
    page = request.args.get('page', 1, type=int)
    shops = Shop.query.order_by(Shop.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/shops.html', shops=shops)

@bp.route('/shop/<int:id>/verify')
@login_required
@admin_required
def verify_shop(id):
    shop = Shop.query.get_or_404(id)
    if shop.verified:
        flash('Duka tayari limethibitishwa.', 'info')
    else:
        shop.verified = True
        db.session.commit()
        # Notify vendor
        create_notification(shop.vendor_id, 'shop_verified', f'Duka lako {shop.name} limethibitishwa.')
        send_sms(shop.vendor.phone, f'Duka lako {shop.name} limethibitishwa. Sasa unaweza kuuza.')
        log_transaction(current_user.id, 'verify_shop', f'Verified shop {shop.id}', request.remote_addr)
        flash('Duka limethibitishwa.', 'success')
    return redirect(url_for('admin.shops'))

# ----------------------------------------------------------------------
# SUPPLIER MANAGEMENT
# ----------------------------------------------------------------------
@bp.route('/suppliers')
@login_required
@admin_required
def suppliers():
    page = request.args.get('page', 1, type=int)
    suppliers = Supplier.query.order_by(Supplier.id).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/suppliers.html', suppliers=suppliers)

@bp.route('/supplier/<int:id>/verify')
@login_required
@admin_required
def verify_supplier(id):
    supplier = Supplier.query.get_or_404(id)
    if supplier.verified:
        flash('Msambazaji tayari amethibitishwa.', 'info')
    else:
        supplier.verified = True
        db.session.commit()
        # Notify supplier
        create_notification(supplier.user_id, 'supplier_verified', 'Akaunti yako ya msambazaji imethibitishwa.')
        send_sms(supplier.user.phone, 'Akaunti yako ya msambazaji imethibitishwa. Sasa unaweza kupokea maagizo.')
        log_transaction(current_user.id, 'verify_supplier', f'Verified supplier {supplier.id}', request.remote_addr)
        flash('Msambazaji amethibitishwa.', 'success')
    return redirect(url_for('admin.suppliers'))

# ----------------------------------------------------------------------
# VOUCHER MANAGEMENT
# ----------------------------------------------------------------------
@bp.route('/vouchers', methods=['GET', 'POST'])
@login_required
@admin_required
def vouchers():
    form = VoucherForm()
    if form.validate_on_submit():
        # Generate unique code
        code = secrets.token_hex(4).upper()
        while Voucher.query.filter_by(code=code).first():
            code = secrets.token_hex(4).upper()
        voucher = Voucher(
            code=code,
            amount=form.amount.data,
            beneficiary_name=form.beneficiary_name.data,
            beneficiary_phone=form.beneficiary_phone.data,
            created_by=current_user.id,
            expiry_date=form.expiry_date.data
        )
        db.session.add(voucher)
        db.session.commit()
        log_transaction(current_user.id, 'create_voucher', f'Created voucher {code}', request.remote_addr)
        flash(f'Vocha {code} imeundwa.', 'success')
        return redirect(url_for('admin.vouchers'))

    page = request.args.get('page', 1, type=int)
    vouchers_list = Voucher.query.order_by(Voucher.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/vouchers.html', form=form, vouchers=vouchers_list)

@bp.route('/vouchers/bulk', methods=['GET', 'POST'])
@login_required
@admin_required
def bulk_vouchers():
    form = BulkVoucherForm()
    if form.validate_on_submit():
        codes = []
        for _ in range(form.count.data):
            code = secrets.token_hex(4).upper()
            while Voucher.query.filter_by(code=code).first():
                code = secrets.token_hex(4).upper()
            voucher = Voucher(
                code=code,
                amount=form.amount.data,
                created_by=current_user.id,
                expiry_date=form.expiry_date.data
            )
            db.session.add(voucher)
            codes.append(code)
        db.session.commit()
        log_transaction(current_user.id, 'bulk_create_voucher', f'Created {len(codes)} vouchers', request.remote_addr)
        flash(f'Vocha {len(codes)} zimeundwa.', 'success')
        return redirect(url_for('admin.vouchers'))
    return render_template('admin/bulk_vouchers.html', form=form)

@bp.route('/voucher/<int:id>/revoke')
@login_required
@admin_required
def revoke_voucher(id):
    voucher = Voucher.query.get_or_404(id)
    if voucher.status != 'active':
        flash('Vocha haiwezi kubatilishwa kwa sababu haiko active.', 'danger')
    else:
        voucher.status = 'revoked'
        db.session.commit()
        log_transaction(current_user.id, 'revoke_voucher', f'Revoked voucher {voucher.code}', request.remote_addr)
        flash('Vocha imebatilishwa.', 'success')
    return redirect(url_for('admin.vouchers'))

# ----------------------------------------------------------------------
# TRAINING PROGRAMS
# ----------------------------------------------------------------------
@bp.route('/trainings', methods=['GET', 'POST'])
@login_required
@admin_required
def trainings():
    form = TrainingProgramForm()
    if form.validate_on_submit():
        program = TrainingProgram(
            title=form.title.data,
            description=form.description.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            capacity=form.capacity.data,
            created_by=current_user.id
        )
        db.session.add(program)
        db.session.commit()
        log_transaction(current_user.id, 'create_training', f'Created training {program.title}', request.remote_addr)
        flash('Mafunzo yameundwa.', 'success')
        return redirect(url_for('admin.trainings'))

    programs = TrainingProgram.query.order_by(TrainingProgram.start_date.desc()).all()
    return render_template('admin/trainings.html', form=form, programs=programs)

@bp.route('/training/<int:id>/applicants')
@login_required
@admin_required
def training_applicants(id):
    program = TrainingProgram.query.get_or_404(id)
    applicants = TrainingApplication.query.filter_by(program_id=id).all()
    return render_template('admin/training_applicants.html', program=program, applicants=applicants)

@bp.route('/training-application/<int:id>/<action>')
@login_required
@admin_required
def handle_training_application(id, action):
    app = TrainingApplication.query.get_or_404(id)
    if action == 'approve':
        app.status = 'approved'
        msg = 'approved'
    elif action == 'reject':
        app.status = 'rejected'
        msg = 'rejected'
    else:
        abort(400)
    db.session.commit()
    # Notify vendor
    create_notification(app.vendor_id, 'training_application',
                        f'Ombi lako la mafunzo {app.program.title} lime{msg}.')
    send_sms(app.vendor.user.phone, f'Ombi lako la mafunzo lime{msg}.')
    log_transaction(current_user.id, f'training_application_{msg}',
                    f'Application {app.id} {msg}', request.remote_addr)
    flash(f'Ombi lime{msg}.', 'success')
    return redirect(url_for('admin.training_applicants', id=app.program_id))

# ----------------------------------------------------------------------
# GRANT APPLICATIONS
# ----------------------------------------------------------------------
@bp.route('/grants')
@login_required
@admin_required
def grants():
    page = request.args.get('page', 1, type=int)
    grants = GrantApplication.query.order_by(GrantApplication.applied_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/grants.html', grants=grants)

@bp.route('/grant/<int:id>/<action>')
@login_required
@admin_required
def handle_grant(id, action):
    grant = GrantApplication.query.get_or_404(id)
    if action == 'approve':
        grant.status = 'approved'
        msg = 'approved'
    elif action == 'reject':
        grant.status = 'rejected'
        msg = 'rejected'
    else:
        abort(400)
    grant.reviewed_by = current_user.id
    grant.reviewed_at = datetime.utcnow()
    db.session.commit()
    # Notify vendor
    create_notification(grant.vendor_id, 'grant_application',
                        f'Ombi lako la ruzuku lime{msg}.')
    send_sms(grant.vendor.phone, f'Ombi lako la ruzuku lime{msg}.')
    log_transaction(current_user.id, f'grant_{msg}',
                    f'Grant {grant.id} {msg}', request.remote_addr)
    flash(f'Ruzuku ime{msg}.', 'success')
    return redirect(url_for('admin.grants'))

# ----------------------------------------------------------------------
# USER MANAGEMENT
# ----------------------------------------------------------------------
@bp.route('/users')
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    users = User.query.order_by(User.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/users.html', users=users)

@bp.route('/user/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    form = UserEditForm(obj=user)
    if form.validate_on_submit():
        user.full_name = form.full_name.data
        user.role = form.role.data
        user.is_active = form.is_active.data
        db.session.commit()
        log_transaction(current_user.id, 'edit_user', f'Edited user {user.id}', request.remote_addr)
        flash('Taarifa za mtumiaji zimesasishwa.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/edit_user.html', form=form, user=user)

# ----------------------------------------------------------------------
# SYSTEM LOGS
# ----------------------------------------------------------------------
@bp.route('/logs')
@login_required
@admin_required
def logs():
    page = request.args.get('page', 1, type=int)
    logs = TransactionLog.query.order_by(TransactionLog.timestamp.desc()).paginate(page=page, per_page=50, error_out=False)
    return render_template('admin/logs.html', logs=logs)

# ----------------------------------------------------------------------
# REPORTS (admin-level summary)
# ----------------------------------------------------------------------
@bp.route('/reports', methods=['GET', 'POST'])
@login_required
@admin_required
def reports():
    form = DateRangeForm()
    if form.validate_on_submit():
        start = form.start_date.data
        end = form.end_date.data

        # Total sales
        total_sales = db.session.query(func.sum(Sale.total_price)).filter(
            func.date(Sale.timestamp) >= start,
            func.date(Sale.timestamp) <= end
        ).scalar() or 0

        # Number of sales
        sales_count = Sale.query.filter(
            func.date(Sale.timestamp) >= start,
            func.date(Sale.timestamp) <= end
        ).count()

        # Top vendors by sales
        top_vendors = db.session.query(
            User.full_name, User.phone,
            func.sum(Sale.total_price).label('total')
        ).join(Sale, Sale.user_id == User.id)\
         .filter(func.date(Sale.timestamp) >= start, func.date(Sale.timestamp) <= end)\
         .group_by(User.id)\
         .order_by(func.sum(Sale.total_price).desc())\
         .limit(10).all()

        # Vouchers redeemed
        vouchers_redeemed = VoucherRedemption.query.filter(
            func.date(VoucherRedemption.timestamp) >= start,
            func.date(VoucherRedemption.timestamp) <= end
        ).count()
        voucher_total = db.session.query(func.sum(VoucherRedemption.amount)).filter(
            func.date(VoucherRedemption.timestamp) >= start,
            func.date(VoucherRedemption.timestamp) <= end
        ).scalar() or 0

        # New vendors registered
        new_vendors = User.query.filter(
            User.role == 'vendor',
            func.date(User.created_at) >= start,
            func.date(User.created_at) <= end
        ).count()

        return render_template('admin/report_results.html',
                               start=start, end=end,
                               total_sales=total_sales,
                               sales_count=sales_count,
                               top_vendors=top_vendors,
                               vouchers_redeemed=vouchers_redeemed,
                               voucher_total=voucher_total,
                               new_vendors=new_vendors)
    return render_template('admin/reports.html', form=form)