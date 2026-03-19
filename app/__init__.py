from flask import Flask, render_template, request, g
from app.extensions import db, migrate, login, babel, talisman, limiter, scheduler, mail
from config import Config
import logging
from logging.handlers import RotatingFileHandler
import os

def get_locale():
    if not g.get('lang_code', None):
        languages = ['sw', 'en']
        g.lang_code = request.accept_languages.best_match(languages) or 'sw'
    return g.lang_code

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    login.login_view = 'auth.login'
    login.login_message = 'Tafadhali ingia ili kuendelea.'
    login.login_message_category = 'info'
    babel.init_app(app, locale_selector=get_locale)

    csp = {
        'default-src': '\'self\'',
        'script-src': ['\'self\'', 'https://cdn.jsdelivr.net', 'https://code.jquery.com'],
        'style-src': ['\'self\'', 'https://cdn.jsdelivr.net'],
        'img-src': ['\'self\'', 'data:'],
        'font-src': ['\'self\'', 'https://cdn.jsdelivr.net']
    }
    talisman.init_app(app, content_security_policy=csp, force_https=False)

    limiter.init_app(app)
    mail.init_app(app)
    scheduler.init_app(app)
    scheduler.start()

    from app.routes import main, auth, vendor, supplier, admin, api, buyer
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp, url_prefix='/auth')
    app.register_blueprint(vendor.bp, url_prefix='/vendor')
    app.register_blueprint(supplier.bp, url_prefix='/supplier')
    app.register_blueprint(admin.bp, url_prefix='/admin')
    app.register_blueprint(api.bp, url_prefix='/api')
    app.register_blueprint(buyer.bp, url_prefix='/buyer')

    register_error_handlers(app)
    register_commands(app)

    @app.context_processor
    def inject_global_data():
        from app.models import Category, Cart
        from flask_login import current_user
        categories = Category.query.all()
        cart_count = 0
        if current_user.is_authenticated and current_user.role == 'buyer':
            cart_count = Cart.query.filter_by(buyer_id=current_user.id).count()
        return dict(categories=categories, cart_count=cart_count)

    if not app.debug:
        setup_logging(app)

    @scheduler.task('cron', id='check_low_stock', hour=9, minute=0)
    def check_low_stock_job():
        with app.app_context():
            from app.models import Product
            from app.utils import send_sms, create_notification
            low_products = Product.query.filter(Product.quantity <= Product.low_stock_threshold).all()
            for product in low_products:
                vendor = product.shop.vendor
                msg = f"Tahadhari: {product.name} imekaribia kuisha. Idadi iliyobaki: {product.quantity}"
                create_notification(vendor.id, 'low_stock', msg)
                send_sms(vendor.phone, msg)

    return app

def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403

def register_commands(app):
    import click
    from app.models import User
    from app.extensions import db

    @app.cli.command("create-admin")
    @click.argument('phone')
    @click.argument('password')
    def create_admin(phone, password):
        user = User(phone=phone, full_name='Admin', role='admin')
        user.set_password(password)
        user.generate_api_token()
        db.session.add(user)
        db.session.commit()
        click.echo(f'Admin user {phone} created.')

    @app.cli.command("generate-token")
    @click.argument('user_id')
    def generate_token(user_id):
        user = User.query.get(user_id)
        if user:
            user.generate_api_token()
            db.session.commit()
            click.echo(f'New token for {user.phone}: {user.api_token}')
        else:
            click.echo('User not found.')

    @app.cli.command("list-users")
    def list_users():
        users = User.query.all()
        for u in users:
            click.echo(f'{u.id}: {u.phone} ({u.role})')

def setup_logging(app):
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/soko_safi.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Soko Safi startup')