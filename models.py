from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from flask_bcrypt import Bcrypt

db = SQLAlchemy()
bcrypt = Bcrypt()


# ─── USER ────────────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(120), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    phone         = db.Column(db.String(20))
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), default='customer')   # customer | vendor | admin
    address       = db.Column(db.Text)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    is_active     = db.Column(db.Boolean, default=True)

    orders        = db.relationship('Order', backref='customer', lazy=True)
    reservations  = db.relationship('TableReservation', backref='customer', lazy=True)
    shop          = db.relationship('Shop', backref='vendor', uselist=False, lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'


# ─── SHOP ─────────────────────────────────────────────────────────────────────
class Shop(db.Model):
    __tablename__ = 'shops'
    id            = db.Column(db.Integer, primary_key=True)
    shop_code     = db.Column(db.String(10), unique=True)          # ES001, ES002 …
    name          = db.Column(db.String(120), nullable=False)
    telugu_name   = db.Column(db.String(120))
    description   = db.Column(db.Text)
    category      = db.Column(db.String(80))                       # BBQ | Fast Food | Snacks …
    image         = db.Column(db.String(256), default='default_shop.jpg')
    banner        = db.Column(db.String(256))
    rating        = db.Column(db.Float, default=4.0)
    total_reviews = db.Column(db.Integer, default=0)
    location      = db.Column(db.String(256), default='Eat Street, Rama Rao Peta, Kakinada')
    contact       = db.Column(db.String(20))
    opening_time  = db.Column(db.String(10), default='11:00')
    closing_time  = db.Column(db.String(10), default='23:00')
    dine_in       = db.Column(db.Boolean, default=True)
    takeaway      = db.Column(db.Boolean, default=True)
    delivery      = db.Column(db.Boolean, default=False)
    table_booking = db.Column(db.Boolean, default=True)
    qr_ordering   = db.Column(db.Boolean, default=True)
    is_active     = db.Column(db.Boolean, default=True)
    vendor_id     = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    categories    = db.relationship('MenuCategory', backref='shop', lazy=True, cascade='all,delete')
    menu_items    = db.relationship('MenuItem', backref='shop', lazy=True, cascade='all,delete')
    tables        = db.relationship('Table', backref='shop', lazy=True, cascade='all,delete')
    orders        = db.relationship('Order', backref='shop', lazy=True)

    def avg_price(self):
        prices = [i.price for i in self.menu_items if i.is_available]
        return round(sum(prices) / len(prices), 0) if prices else 0

    def __repr__(self):
        return f'<Shop {self.name}>'


# ─── MENU CATEGORY ────────────────────────────────────────────────────────────
class MenuCategory(db.Model):
    __tablename__ = 'menu_categories'
    id          = db.Column(db.Integer, primary_key=True)
    shop_id     = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    name        = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(256))
    sort_order  = db.Column(db.Integer, default=0)

    items       = db.relationship('MenuItem', backref='category', lazy=True, cascade='all,delete')


# ─── MENU ITEM ────────────────────────────────────────────────────────────────
class MenuItem(db.Model):
    __tablename__ = 'menu_items'
    id               = db.Column(db.Integer, primary_key=True)
    shop_id          = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    category_id      = db.Column(db.Integer, db.ForeignKey('menu_categories.id'))
    name             = db.Column(db.String(120), nullable=False)
    telugu_name      = db.Column(db.String(120))
    description      = db.Column(db.Text)
    price            = db.Column(db.Float, nullable=False)
    quantity_desc    = db.Column(db.String(80))                     # "4 pcs", "1 serving"
    veg_nonveg       = db.Column(db.String(10), default='non-veg')  # veg | non-veg | egg
    image            = db.Column(db.String(256), default='default_food.jpg')
    is_available     = db.Column(db.Boolean, default=True)
    is_featured      = db.Column(db.Boolean, default=False)
    preparation_time = db.Column(db.Integer, default=15)            # minutes
    spice_level      = db.Column(db.String(20), default='medium')   # mild | medium | hot
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<MenuItem {self.name} ₹{self.price}>'


# ─── ORDER ────────────────────────────────────────────────────────────────────
class Order(db.Model):
    __tablename__ = 'orders'
    id              = db.Column(db.Integer, primary_key=True)
    order_number    = db.Column(db.String(20), unique=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'))
    shop_id         = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    order_type      = db.Column(db.String(20), nullable=False)      # DELIVERY | TAKEAWAY | DINE_IN
    status          = db.Column(db.String(30), default='PENDING')   # PENDING|ACCEPTED|PREPARING|READY|DELIVERED|CANCELLED
    total_amount    = db.Column(db.Float, default=0.0)
    delivery_address= db.Column(db.Text)
    pickup_time     = db.Column(db.String(20))
    table_id        = db.Column(db.Integer, db.ForeignKey('tables.id'))
    special_note    = db.Column(db.Text)
    payment_method  = db.Column(db.String(30), default='cash')      # cash | upi | card
    payment_status  = db.Column(db.String(20), default='pending')   # pending | paid
    session_id      = db.Column(db.String(128))                     # for guest orders
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items           = db.relationship('OrderItem', backref='order', lazy=True, cascade='all,delete')
    kitchen_order   = db.relationship('KitchenOrder', backref='order', uselist=False)

    def generate_order_number(self):
        import secrets
        # 64 bits of randomness makes a duplicate overwhelmingly unlikely while
        # remaining well within the database column's 20-character limit.
        self.order_number = 'ES' + secrets.token_hex(8).upper()


# ─── ORDER ITEM ───────────────────────────────────────────────────────────────
class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id                   = db.Column(db.Integer, primary_key=True)
    order_id             = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    menu_item_id         = db.Column(db.Integer, db.ForeignKey('menu_items.id'), nullable=False)
    quantity             = db.Column(db.Integer, default=1)
    unit_price           = db.Column(db.Float, nullable=False)
    total_price          = db.Column(db.Float, nullable=False)
    special_instructions = db.Column(db.String(256))

    menu_item            = db.relationship('MenuItem', lazy=True)


# ─── TABLE ────────────────────────────────────────────────────────────────────
class Table(db.Model):
    __tablename__ = 'tables'
    id           = db.Column(db.Integer, primary_key=True)
    shop_id      = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    table_number = db.Column(db.String(10), nullable=False)
    capacity     = db.Column(db.Integer, default=4)
    status       = db.Column(db.String(20), default='AVAILABLE')   # AVAILABLE | OCCUPIED | RESERVED
    qr_code      = db.Column(db.String(128), unique=True)
    location_desc= db.Column(db.String(80))                        # "Near entrance", "Window"
    is_active    = db.Column(db.Boolean, default=True)

    orders       = db.relationship('Order', backref='table', lazy=True)
    reservations = db.relationship('TableReservation', backref='table', lazy=True)
    requests     = db.relationship('WaiterRequest', backref='table', lazy=True)

    def __repr__(self):
        return f'<Table {self.table_number} ({self.status})>'


# ─── TABLE RESERVATION ────────────────────────────────────────────────────────
class TableReservation(db.Model):
    __tablename__ = 'table_reservations'
    id           = db.Column(db.Integer, primary_key=True)
    shop_id      = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    table_id     = db.Column(db.Integer, db.ForeignKey('tables.id'))
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'))
    session_id   = db.Column(db.String(128))                     # for guest reservations
    guest_name   = db.Column(db.String(120))
    guest_phone  = db.Column(db.String(20))
    date         = db.Column(db.String(20), nullable=False)
    time         = db.Column(db.String(10), nullable=False)
    people_count = db.Column(db.Integer, default=2)
    seating_preference = db.Column(db.String(50), default='Any') # Any | Window | Near entrance | Family area | Quiet area
    status       = db.Column(db.String(20), default='PENDING')     # PENDING | CONFIRMED | CANCELLED
    note         = db.Column(db.Text)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    shop         = db.relationship('Shop', lazy=True)


# ─── KITCHEN ORDER ────────────────────────────────────────────────────────────
class KitchenOrder(db.Model):
    __tablename__ = 'kitchen_orders'
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    shop_id    = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    status     = db.Column(db.String(30), default='PENDING')       # PENDING|ACCEPTED|PREPARING|READY|SERVED
    priority   = db.Column(db.Integer, default=1)
    note       = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shop       = db.relationship('Shop', lazy=True)


# ─── WAITER REQUEST ───────────────────────────────────────────────────────────
class WaiterRequest(db.Model):
    __tablename__ = 'waiter_requests'
    id           = db.Column(db.Integer, primary_key=True)
    table_id     = db.Column(db.Integer, db.ForeignKey('tables.id'), nullable=False)
    shop_id      = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    request_type = db.Column(db.String(30))                        # WAITER|WATER|BILL|MENU|CLEANING
    status       = db.Column(db.String(20), default='PENDING')     # PENDING | DONE
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    shop         = db.relationship('Shop', lazy=True)


# ─── CART ─────────────────────────────────────────────────────────────────────
class CartItem(db.Model):
    __tablename__ = 'cart_items'
    id           = db.Column(db.Integer, primary_key=True)
    session_id   = db.Column(db.String(128), nullable=False)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'))
    shop_id      = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_items.id'), nullable=False)
    quantity     = db.Column(db.Integer, default=1)
    order_type   = db.Column(db.String(20), default='TAKEAWAY')
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    menu_item    = db.relationship('MenuItem', lazy=True)
    shop         = db.relationship('Shop', lazy=True)
