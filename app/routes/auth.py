from flask import abort, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, limiter
from app.models import User, Shop, ExpenseCategory, Notification, TransactionLog, BuyerProfile, Supplier
from app.forms import LoginForm, RegistrationForm, ShopSetupForm, ChangePasswordForm
from app.decorators import logout_required
from app.routes import auth_bp as bp
from app.utils import send_sms, create_notification, log_transaction
from datetime import datetime
import secrets

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("1000 per hour")
@logout_required
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(phone=form.phone.data).first()
        if user and user.check_password(form.password.data) and user.is_active:
            login_user(user, remember=form.remember.data)
            log_transaction(user.id, 'login', f'User logged in from IP {request.remote_addr}', request.remote_addr)

            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif user.shop:
                return redirect(url_for('vendor.dashboard'))
            elif user.role == 'supplier':
                return redirect(url_for('supplier.dashboard'))
            else:
                return redirect(url_for('buyer.dashboard'))
        else:
            flash('Namba ya simu au nenosiri si sahihi.', 'danger')
    return render_template('auth/login.html', form=form)

@bp.route('/logout')
@login_required
def logout():
    log_transaction(current_user.id, 'logout', 'User logged out', request.remote_addr)
    logout_user()
    flash('Umetoka kwenye akaunti yako.', 'success')
    return redirect(url_for('main.index'))

@bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per hour")
@logout_required
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            phone=form.phone.data,
            full_name=form.full_name.data,
            role=form.role.data
        )
        user.set_password(form.password.data)
        user.api_token = secrets.token_urlsafe(32)
        db.session.add(user)
        db.session.flush()

        if form.role.data == 'supplier':
            supplier = Supplier(user_id=user.id, business_name='', verified=False)
            db.session.add(supplier)
        elif form.role.data == 'buyer':
            buyer_profile = BuyerProfile(user_id=user.id, loyalty_points=0)
            db.session.add(buyer_profile)

        db.session.commit()

        try:
            send_sms(user.phone, f"Karibu Soko Safi! Akaunti yako imeundwa. Karibu tena.")
        except Exception as e:
            current_app.logger.error(f"SMS failed: {e}")

        log_transaction(user.id, 'register', f'New {user.role} registered', request.remote_addr)
        flash('Umefanikiwa kujisajili! Tafadhali ingia.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)

@bp.route('/setup-wizard', methods=['GET', 'POST'])
@login_required
def setup_wizard():
    if current_user.shop:
        return redirect(url_for('vendor.dashboard'))

    form = ShopSetupForm()
    if form.validate_on_submit():
        shop = Shop(
            vendor_id=current_user.id,
            name=form.name.data,
            location=form.location.data,
            category=form.category.data,
            verified=False
        )
        db.session.add(shop)
        db.session.flush()

        default_cats = ['Kodi', 'Usafiri', 'Wafanyakazi', 'Ununuzi', 'Matangazo', 'Huduma']
        for cat_name in default_cats:
            cat = ExpenseCategory(shop_id=shop.id, name=cat_name)
            db.session.add(cat)

        db.session.commit()

        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            create_notification(admin.id, 'new_shop', f'Duka jipya: {shop.name} linahitaji kuthibitishwa.')

        log_transaction(current_user.id, 'setup_shop', f'Shop {shop.name} created', request.remote_addr)
        flash('Duka lako limeanzishwa! Sasa unaweza kuanza kuongeza bidhaa.', 'success')
        return redirect(url_for('vendor.dashboard'))

    return render_template('auth/setup_wizard.html', form=form)

@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if current_user.check_password(form.old_password.data):
            current_user.set_password(form.new_password.data)
            db.session.commit()
            log_transaction(current_user.id, 'change_password', 'Password changed', request.remote_addr)
            flash('Nenosiri limebadilishwa kwa fanikiwa.', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('Nenosiri la zamani si sahihi.', 'danger')
    return render_template('auth/change_password.html', form=form)

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        new_name = request.form.get('full_name')
        if new_name:
            current_user.full_name = new_name
            db.session.commit()
            flash('Taarifa zimesasishwa.', 'success')
        return redirect(url_for('auth.profile'))
    return render_template('auth/profile.html', user=current_user)