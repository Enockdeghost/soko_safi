from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Tafadhali ingia kwanza.', 'warning')
            return redirect(url_for('auth.login'))
        if current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def vendor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Tafadhali ingia kwanza.', 'warning')
            return redirect(url_for('auth.login'))
        # Check if user has a shop (any user can be a seller)
        if not current_user.shop:
            flash('Tafadhali kwanza anzisha duka lako.', 'warning')
            return redirect(url_for('auth.setup_wizard'))
        return f(*args, **kwargs)
    return decorated_function

def supplier_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Tafadhali ingia kwanza.', 'warning')
            return redirect(url_for('auth.login'))
        if current_user.role != 'supplier':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def buyer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Tafadhali ingia kwanza.', 'warning')
            return redirect(url_for('auth.login'))
        if current_user.role != 'buyer':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def logout_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated:
            flash('Tayari umeshaingia.', 'info')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function