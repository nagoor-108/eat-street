from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from models import db, CartItem, MenuItem, Shop, Order, OrderItem, KitchenOrder
import uuid
from collections import defaultdict

orders_bp = Blueprint('orders', __name__)
ORDER_TYPES = {'DELIVERY', 'TAKEAWAY'}
PAYMENT_METHODS = {'cash', 'upi', 'card'}
MAX_ITEM_QUANTITY = 20

def get_session_id():
    if '_id' not in session:
        session['_id'] = str(uuid.uuid4())
    return session['_id']


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _positive_quantity(value):
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        return None
    return quantity if 1 <= quantity <= MAX_ITEM_QUANTITY else None


def _get_cart_total_qty(sid):
    total = db.session.query(
        db.func.coalesce(db.func.sum(CartItem.quantity), 0)
    ).filter(CartItem.session_id == sid).scalar()
    return int(total or 0)


def _can_view_order(order, sid):
    placed_nums = session.get('placed_order_numbers', [])
    return (
        order.session_id == sid or
        order.order_number in placed_nums or
        (current_user.is_authenticated and (order.user_id == current_user.id or current_user.role in ('admin', 'vendor')))
    )


def _cart_payload(sid, message=None):
    items = CartItem.query.filter_by(session_id=sid).all()
    total = sum(i.menu_item.price * i.quantity for i in items)
    total_qty = sum(i.quantity for i in items)
    payload = {
        'success': True,
        'cart_count': total_qty,
        'total': total,
        'items': [
            {
                'id': i.id,
                'menu_item_id': i.menu_item_id,
                'name': i.menu_item.name,
                'price': float(i.menu_item.price),
                'quantity': i.quantity,
                'subtotal': float(i.menu_item.price * i.quantity),
                'shop_id': i.shop_id,
                'shop_name': i.shop.name,
                'image': i.menu_item.image,
                'order_type': i.order_type
            }
            for i in items
        ]
    }
    if message:
        payload['message'] = message
    return payload


# ─── CART: DATA API ───────────────────────────────────────────────────────────
@orders_bp.route('/cart/data', methods=['GET'])
def cart_data():
    sid = get_session_id()
    return jsonify(_cart_payload(sid))


# ─── CART: ADD ITEM ───────────────────────────────────────────────────────────
@orders_bp.route('/cart/add', methods=['POST'])
def add_to_cart():
    data = _json_object()
    if not data:
        return jsonify({'success': False, 'message': 'A JSON request body is required.'}), 400

    item_id = data.get('item_id')
    qty = _positive_quantity(data.get('quantity', 1))
    order_type = data.get('order_type', 'TAKEAWAY')

    if qty is None or order_type not in ORDER_TYPES:
        return jsonify({'success': False, 'message': 'Invalid quantity or order type.'}), 400

    sid = get_session_id()
    item = MenuItem.query.get_or_404(item_id)

    if not item.is_available:
        return jsonify({'success': False, 'message': 'This item is currently unavailable.'}), 400

    existing = CartItem.query.filter_by(
        session_id=sid, menu_item_id=item_id, order_type=order_type
    ).first()

    if existing:
        if existing.quantity + qty > MAX_ITEM_QUANTITY:
            return jsonify({'success': False, 'message': f'You can order at most {MAX_ITEM_QUANTITY} of one item.'}), 400
        existing.quantity += qty
    else:
        cart_item = CartItem(
            session_id=sid,
            user_id=current_user.id if current_user.is_authenticated else None,
            shop_id=item.shop_id,
            menu_item_id=item_id,
            quantity=qty,
            order_type=order_type
        )
        db.session.add(cart_item)

    db.session.commit()
    return jsonify(_cart_payload(sid, message=f'{item.name} added to cart!'))


# ─── CART: REMOVE ITEM ────────────────────────────────────────────────────────
@orders_bp.route('/cart/remove/<int:cart_id>', methods=['POST'])
def remove_from_cart(cart_id):
    sid = get_session_id()
    item = CartItem.query.filter_by(id=cart_id, session_id=sid).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return jsonify(_cart_payload(sid, message='Item removed from cart.'))


# ─── CART: CLEAR ALL ITEMS ───────────────────────────────────────────────────
@orders_bp.route('/cart/clear', methods=['POST'])
def clear_cart():
    sid = get_session_id()
    CartItem.query.filter_by(session_id=sid).delete()
    if current_user.is_authenticated:
        CartItem.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify(_cart_payload(sid, message='Cart has been cleared for your new order.'))


# ─── CART: UPDATE QUANTITY ───────────────────────────────────────────────────
@orders_bp.route('/cart/update', methods=['POST'])
def update_cart():
    data = _json_object()
    if not data:
        return jsonify({'success': False, 'message': 'Invalid cart update.'}), 400

    sid = get_session_id()
    cart_item = None
    if 'cart_id' in data:
        cart_item = CartItem.query.filter_by(id=data['cart_id'], session_id=sid).first()
    elif 'item_id' in data:
        cart_item = CartItem.query.filter_by(menu_item_id=data['item_id'], session_id=sid).first()

    try:
        qty = int(data.get('quantity', 1))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Quantity must be a number.'}), 400

    if not cart_item and qty > 0 and 'item_id' in data:
        # If item was not in cart and qty > 0, add it
        item = MenuItem.query.get(data['item_id'])
        if item and item.is_available:
            order_type = data.get('order_type', 'TAKEAWAY')
            if order_type not in ORDER_TYPES:
                order_type = 'TAKEAWAY'
            cart_item = CartItem(
                session_id=sid,
                user_id=current_user.id if current_user.is_authenticated else None,
                shop_id=item.shop_id,
                menu_item_id=item.id,
                quantity=min(qty, MAX_ITEM_QUANTITY),
                order_type=order_type
            )
            db.session.add(cart_item)
    elif cart_item:
        if qty <= 0:
            db.session.delete(cart_item)
        elif qty > MAX_ITEM_QUANTITY:
            return jsonify({'success': False, 'message': f'You can order at most {MAX_ITEM_QUANTITY} of one item.'}), 400
        else:
            cart_item.quantity = qty

    db.session.commit()
    return jsonify(_cart_payload(sid))


# ─── CART PAGE ────────────────────────────────────────────────────────────────
@orders_bp.route('/cart')
def cart():
    sid = get_session_id()
    items = CartItem.query.filter_by(session_id=sid).all()
    
    # Group items by shop
    grouped_by_shop = defaultdict(list)
    total = 0
    total_qty = 0
    for i in items:
        subtotal = i.menu_item.price * i.quantity
        total += subtotal
        total_qty += i.quantity
        grouped_by_shop[i.shop].append(i)

    return render_template(
        'order/cart.html',
        cart_items=items,
        grouped_by_shop=dict(grouped_by_shop),
        total=total,
        total_qty=total_qty
    )


# ─── CHECKOUT ─────────────────────────────────────────────────────────────────
@orders_bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    is_ajax = (
        request.is_json or
        'application/json' in request.headers.get('Accept', '') or
        request.headers.get('X-Requested-With', '').lower() == 'xmlhttprequest'
    )

    if not current_user.is_authenticated:
        if is_ajax:
            return jsonify({
                'success': False,
                'requires_auth': True,
                'login_url': url_for('auth.login', next=url_for('orders.checkout')),
                'message': 'Please login or create an account to place your order.'
            }), 401
        flash('Please login or register to place your order. 🍴', 'info')
        return redirect(url_for('auth.login', next=url_for('orders.checkout')))

    sid = get_session_id()
    cart_items = CartItem.query.filter(
        (CartItem.session_id == sid) | (CartItem.user_id == current_user.id)
    ).all()
    if not cart_items:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('home.index'))

    # Group items by shop
    grouped_by_shop = defaultdict(list)
    total = 0
    for ci in cart_items:
        grouped_by_shop[ci.shop].append(ci)
        total += ci.menu_item.price * ci.quantity

    if request.method == 'POST':
        order_type     = request.form.get('order_type', 'TAKEAWAY')
        address        = request.form.get('address', '').strip()
        pickup_time    = request.form.get('pickup_time', '').strip()
        payment_method = request.form.get('payment_method', 'cash')
        special_note   = request.form.get('special_note', '').strip()

        if order_type not in ORDER_TYPES or payment_method not in PAYMENT_METHODS:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Invalid order details.'}), 400
            flash('Invalid order details.', 'danger')
            return redirect(url_for('orders.checkout'))

        if order_type == 'DELIVERY' and not address:
            if is_ajax:
                return jsonify({'success': False, 'message': 'A delivery address is required.'}), 400
            flash('A delivery address is required.', 'warning')
            return redirect(url_for('orders.checkout'))

        # Validate all items are available and quantities are valid
        for item in cart_items:
            if not item.menu_item.is_available:
                msg = f'"{item.menu_item.name}" is currently unavailable. Please remove it from your cart.'
                if is_ajax:
                    return jsonify({'success': False, 'message': msg}), 400
                flash(msg, 'danger')
                return redirect(url_for('orders.cart'))
            if not (1 <= item.quantity <= MAX_ITEM_QUANTITY):
                if is_ajax:
                    return jsonify({'success': False, 'message': 'One or more items have invalid quantities.'}), 400
                flash('One or more items have invalid quantities.', 'danger')
                return redirect(url_for('orders.cart'))

        # Create separate orders per shop (multi-shop split checkout)
        created_orders = []
        user_id = current_user.id if current_user.is_authenticated else None

        for shop, items in grouped_by_shop.items():
            shop_total = sum(i.menu_item.price * i.quantity for i in items)
            order = Order(
                shop_id=shop.id,
                order_type=order_type,
                total_amount=shop_total,
                delivery_address=address,
                pickup_time=pickup_time,
                payment_method=payment_method,
                special_note=special_note,
                session_id=sid,
                user_id=user_id,
                status='PENDING'
            )
            order.generate_order_number()
            db.session.add(order)
            db.session.flush()

            for ci in items:
                oi = OrderItem(
                    order_id=order.id,
                    menu_item_id=ci.menu_item_id,
                    quantity=ci.quantity,
                    unit_price=ci.menu_item.price,
                    total_price=ci.menu_item.price * ci.quantity
                )
                db.session.add(oi)

            ko = KitchenOrder(order_id=order.id, shop_id=shop.id)
            db.session.add(ko)
            created_orders.append(order)

        # Track placed orders in session
        placed_nums = list(session.get('placed_order_numbers', []))
        for o in created_orders:
            if o.order_number not in placed_nums:
                placed_nums.append(o.order_number)
        session['placed_order_numbers'] = placed_nums

        # Clear cart completely for every new order and assign fresh cart session
        CartItem.query.filter_by(session_id=sid).delete()
        if current_user.is_authenticated:
            CartItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        # Reset cart session ID so next order always starts in a fresh new cart
        session['_id'] = str(uuid.uuid4())

        if is_ajax:
            return jsonify({
                'success': True,
                'order_numbers': [o.order_number for o in created_orders],
                'primary_order_number': created_orders[0].order_number if created_orders else '',
                'total_amount': sum(o.total_amount for o in created_orders),
                'count': len(created_orders),
                'shops': [o.shop.name for o in created_orders],
                'redirect_url': url_for('orders.my_orders')
            })

        if len(created_orders) == 1:
            flash(f'Order #{created_orders[0].order_number} placed successfully with {created_orders[0].shop.name}! 🎉', 'success')
        else:
            order_nums = ', '.join(f'#{o.order_number}' for o in created_orders)
            flash(f'{len(created_orders)} separate orders ({order_nums}) placed successfully across stalls! 🎉', 'success')

        return redirect(url_for('orders.my_orders'))

    return render_template(
        'order/checkout.html',
        cart_items=cart_items,
        grouped_by_shop=dict(grouped_by_shop),
        total=total
    )


# ─── MY ORDERS PAGE ───────────────────────────────────────────────────────────
@orders_bp.route('/my-orders')
def my_orders():
    sid = get_session_id()
    placed_nums = session.get('placed_order_numbers', [])
    if current_user.is_authenticated:
        orders = Order.query.filter(
            (Order.user_id == current_user.id) | (Order.session_id == sid) | (Order.order_number.in_(placed_nums))
        ).order_by(Order.created_at.desc()).all()
    else:
        orders = Order.query.filter(
            (Order.session_id == sid) | (Order.order_number.in_(placed_nums))
        ).order_by(Order.created_at.desc()).all()

    return render_template('order/my_orders.html', orders=orders)


# ─── ORDER TRACKING ───────────────────────────────────────────────────────────
@orders_bp.route('/track/<order_number>')
def track(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    if not _can_view_order(order, get_session_id()):
        abort(403)
    return render_template('order/track.html', order=order)


# ─── ORDER STATUS API ─────────────────────────────────────────────────────────
@orders_bp.route('/status/<order_number>')
def order_status(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    if not _can_view_order(order, get_session_id()):
        abort(403)
    return jsonify({
        'order_number': order.order_number,
        'status': order.status,
        'shop_name': order.shop.name,
        'kitchen_status': order.kitchen_order.status if order.kitchen_order else 'PENDING'
    })
