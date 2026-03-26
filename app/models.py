from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db, login

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    full_name = db.Column(db.String(100))
    role = db.Column(db.String(20), default='vendor')  # admin, vendor, supplier, buyer, beneficiary
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    api_token = db.Column(db.String(64), unique=True, index=True)

    shop = db.relationship('Shop', backref='vendor', uselist=False, lazy=True)
    supplier_profile = db.relationship('Supplier', backref='user', uselist=False, lazy=True)
    buyer_profile = db.relationship('BuyerProfile', foreign_keys='BuyerProfile.user_id', backref='user', uselist=False, lazy=True)
    sales = db.relationship('Sale', backref='user', lazy='dynamic')
    expenses = db.relationship('Expense', backref='user', lazy='dynamic')
    payments = db.relationship('Payment', backref='user', lazy='dynamic')
    transactions = db.relationship('TransactionLog', backref='user', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')
    vouchers_created = db.relationship('Voucher', foreign_keys='Voucher.created_by', backref='creator', lazy='dynamic')
    vouchers_redeemed = db.relationship('Voucher', foreign_keys='Voucher.redeemed_by_vendor', backref='redeemer', lazy='dynamic')
    training_applications = db.relationship('TrainingApplication', foreign_keys='TrainingApplication.vendor_id', backref='vendor', lazy='dynamic')
    grant_applications = db.relationship('GrantApplication', foreign_keys='GrantApplication.vendor_id', backref='vendor', lazy='dynamic')
    order_requests = db.relationship('OrderRequest', foreign_keys='OrderRequest.vendor_id', backref='vendor', lazy='dynamic')
    received_reviews = db.relationship('Review', foreign_keys='Review.vendor_id', backref='vendor', lazy='dynamic')
    given_reviews = db.relationship('Review', foreign_keys='Review.buyer_id', backref='buyer', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_api_token(self):
        import secrets
        self.api_token = secrets.token_urlsafe(32)

    def average_rating(self):
        ratings = [r.rating for r in self.received_reviews]
        return sum(ratings)/len(ratings) if ratings else 0

@login.user_loader
def load_user(id):
    return User.query.get(int(id))

class Shop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200))
    category = db.Column(db.String(50))
    verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    daily_target = db.Column(db.Float, default=100000)

    products = db.relationship('Product', backref='shop', lazy='dynamic', cascade='all, delete-orphan')
    expense_categories = db.relationship('ExpenseCategory', backref='shop', lazy='dynamic', cascade='all, delete-orphan')
    vouchers_redeemed = db.relationship('Voucher', foreign_keys='Voucher.redeemed_at_shop', backref='shop', lazy='dynamic')
    voucher_redemptions = db.relationship('VoucherRedemption', backref='shop', lazy='dynamic')

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    products = db.relationship('Product', backref='category', lazy='dynamic')

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Float, default=0)
    unit = db.Column(db.String(20), default='pcs')
    expiry_date = db.Column(db.Date, nullable=True)
    low_stock_threshold = db.Column(db.Float, default=5)
    image_url = db.Column(db.String(200), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    barcode = db.Column(db.String(50), unique=True, index=True, nullable=True)

    sales = db.relationship('Sale', backref='product', lazy='dynamic')
    cart_items = db.relationship('Cart', backref='product', lazy='dynamic')
    order_items = db.relationship('OrderItem', backref='product', lazy='dynamic')
    wishlists = db.relationship('Wishlist', backref='product', lazy='dynamic')
    promotions = db.relationship('Promotion', backref='product', lazy='dynamic')

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), default='cash')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    synced = db.Column(db.Boolean, default=True)

class ExpenseCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)

    expenses = db.relationship('Expense', backref='category', lazy='dynamic')

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_category.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    date = db.Column(db.Date, default=datetime.utcnow)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    synced = db.Column(db.Boolean, default=True)

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    business_name = db.Column(db.String(100), nullable=False)
    contact_phone = db.Column(db.String(20))
    location = db.Column(db.String(200))
    verified = db.Column(db.Boolean, default=False)

    products = db.relationship('SupplierProduct', backref='supplier', lazy='dynamic')
    order_requests = db.relationship('OrderRequest', backref='supplier', lazy='dynamic')

class SupplierProduct(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float)
    unit = db.Column(db.String(20))

class OrderRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

class Voucher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    beneficiary_name = db.Column(db.String(100))
    beneficiary_phone = db.Column(db.String(20))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(20), default='active')
    expiry_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    redeemed_at = db.Column(db.DateTime)
    redeemed_by_vendor = db.Column(db.Integer, db.ForeignKey('user.id'))
    redeemed_at_shop = db.Column(db.Integer, db.ForeignKey('shop.id'))

    redemptions = db.relationship('VoucherRedemption', backref='voucher', lazy='dynamic')

class VoucherRedemption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voucher_id = db.Column(db.Integer, db.ForeignKey('voucher.id'))
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'))
    amount = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class TrainingProgram(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    capacity = db.Column(db.Integer)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    applications = db.relationship('TrainingApplication', backref='program', lazy='dynamic')

class TrainingApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    program_id = db.Column(db.Integer, db.ForeignKey('training_program.id'))
    status = db.Column(db.String(20), default='pending')
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)

class GrantApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount_requested = db.Column(db.Float)
    purpose = db.Column(db.Text)
    business_plan = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    reviewed_at = db.Column(db.DateTime)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    reference = db.Column(db.String(100), unique=True)
    status = db.Column(db.String(20), default='pending')
    method = db.Column(db.String(20))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(50))
    message = db.Column(db.String(200))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TransactionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class BuyerProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)
    default_address = db.Column(db.String(200))
    phone_verified = db.Column(db.Boolean, default=False)
    loyalty_points = db.Column(db.Integer, default=0)
    referral_code = db.Column(db.String(20), unique=True)
    referred_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    referrer = db.relationship('User', foreign_keys=[referred_by])

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Float, nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    total_amount = db.Column(db.Float, nullable=False)
    points_earned = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending')
    payment_method = db.Column(db.String(20))
    payment_status = db.Column(db.String(20), default='pending')
    delivery_address = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    buyer = db.relationship('User', foreign_keys=[buyer_id])
    vendor = db.relationship('User', foreign_keys=[vendor_id])
    items = db.relationship('OrderItem', backref='order', lazy='dynamic')
    review = db.relationship('Review', backref='order', uselist=False, lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Float)
    price_at_time = db.Column(db.Float)
    subtotal = db.Column(db.Float)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), unique=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    rating = db.Column(db.Integer)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

class Promotion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    discount_percent = db.Column(db.Integer)
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

    vendor = db.relationship('User', foreign_keys=[vendor_id])