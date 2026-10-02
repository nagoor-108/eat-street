from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash, abort
from flask_login import current_user
from models import db, Table, TableReservation, Shop, Order, OrderItem, KitchenOrder, WaiterRequest, MenuItem, CartItem
import uuid
from datetime import date as date_type, time as time_type, datetime

dine_in_bp = Blueprint('dine_in', __name__)
MAX_ITEM_QUANTITY = 20
ALLOWED_WAITER_REQUESTS = {'WAITER', 'WATER', 'BILL', 'MENU', 'CLEANING'}
VALID_PREFERENCES = {'Any', 'Window', 'Near entrance', 'Family area', 'Quiet area'}

def get_session_id():
    if '_id' not in session:
        session['_id'] = str(uuid.uuid4())
    return session['_id']


# ─── AVAILABLE TABLES API ─────────────────────────────────────────────────────
@dine_in_bp.route('/available-tables/<int:shop_id>')
def available_tables(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    date_str = request.args.get('date', '').strip()
    time_str = request.args.get('time', '').strip()
    pref = request.args.get('preference', 'Any').strip()
    
    try:
        people_count = int(request.args.get('people_count', 2))
    except (TypeError, ValueError):
        people_count = 2

    if not date_str:
        date_str = date_type.today().isoformat()
    if not time_str:
        time_str = shop.opening_time or '12:00'

    # Check date validity
    try:
        parsed_date = date_type.fromisoformat(date_str)
        if parsed_date < date_type.today():
            return jsonify({'success': False, 'message': 'Date cannot be in the past.', 'tables': []}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid date format.', 'tables': []}), 400

    # Get active tables with enough capacity
    suitable_tables = Table.query.filter(
        Table.shop_id == shop_id,
        Table.is_active == True,
        Table.capacity >= people_count
    ).order_by(Table.capacity.asc(), Table.table_number.asc()).all()

    # Get tables already reserved for (date, time)
    reserved_table_ids = set(
        r.table_id for r in TableReservation.query.filter(
            TableReservation.shop_id == shop_id,
            TableReservation.date == date_str,
            TableReservation.time == time_str,
            TableReservation.status.in_(['PENDING', 'CONFIRMED'])
        ).all()
    )

    # Filter out reserved tables
    available = [t for t in suitable_tables if t.id not in reserved_table_ids]

    if not available:
        return jsonify({
            'success': True,
            'preference_matched': False,
            'tables': [],
            'message': f'No tables available for {people_count} people on {date_str} at {time_str}. Please try a different time or party size.'
        })

    # Check preference matching
    if pref and pref != 'Any':
        pref_lower = pref.lower()
        matched = [t for t in available if (t.location_desc or '').lower() == pref_lower]
        if matched:
            return jsonify({
                'success': True,
                'preference_matched': True,
                'tables': [{'id': t.id, 'number': t.table_number, 'capacity': t.capacity, 'location': t.location_desc or 'Main hall'} for t in matched],
                'message': f'Found {len(matched)} table(s) matching your preference "{pref}".'
            })
        else:
            return jsonify({
                'success': True,
                'preference_matched': False,
                'tables': [{'id': t.id, 'number': t.table_number, 'capacity': t.capacity, 'location': t.location_desc or 'Main hall'} for t in available],
                'message': f'No tables available matching your preference "{pref}". Showing {len(available)} other suitable table(s) with enough capacity:'
            })

    # 'Any' preference
    return jsonify({
        'success': True,
        'preference_matched': True,
        'tables': [{'id': t.id, 'number': t.table_number, 'capacity': t.capacity, 'location': t.location_desc or 'Main hall'} for t in available],
        'message': f'{len(available)} table(s) available for {people_count} people.'
    })


# ─── RESERVE TABLE PAGE & HANDLER ─────────────────────────────────────────────
@dine_in_bp.route('/reserve/<int:shop_id>', methods=['GET', 'POST'])
def reserve(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    tables = Table.query.filter_by(shop_id=shop_id, is_active=True).all()

    if request.method == 'POST':
        is_json = request.is_json
        data = request.get_json(silent=True) if is_json else request.form

        date = (data.get('date') or '').strip()
        time = (data.get('time') or '').strip()
        pref = (data.get('seating_preference') or data.get('preference') or 'Any').strip()
        if pref not in VALID_PREFERENCES:
            pref = 'Any'

        try:
            people_count = int(data.get('people_count', 2))
            reservation_date = date_type.fromisoformat(date)
            reservation_time = time_type.fromisoformat(time)
        except (TypeError, ValueError):
            msg = 'Enter a valid date (YYYY-MM-DD), time (HH:MM), and party size (1-20).'
            return jsonify({'success': False, 'message': msg}), 400

        table_id = data.get('table_id')
        guest_name = (data.get('guest_name') or '').strip()
        guest_phone = (data.get('guest_phone') or '').strip()
        note = (data.get('note') or '').strip()

        if reservation_date < date_type.today() or not 1 <= people_count <= 20:
            return jsonify({'success': False, 'message': 'Enter a valid future date and party size (1-20).'}), 400

        if not table_id:
            return jsonify({'success': False, 'message': 'Please select an available table.'}), 400

        try:
            table_id = int(table_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Invalid table selected.'}), 400

        table = Table.query.filter_by(id=table_id, shop_id=shop_id, is_active=True).first()
        if not table:
            return jsonify({'success': False, 'message': 'Selected table does not exist or does not belong to this shop.'}), 400

        if people_count > table.capacity:
            return jsonify({'success': False, 'message': f'Selected table {table.table_number} has capacity for {table.capacity} people, but you requested {people_count}.'}), 400

        if not guest_name:
            return jsonify({'success': False, 'message': 'Guest name is required.'}), 400

        if not (shop.opening_time <= time <= shop.closing_time):
            return jsonify({'success': False, 'message': f'Please select a time during opening hours ({shop.opening_time} - {shop.closing_time}).'}), 400

        # Prevent double-booking on same table, date, and time
        existing = TableReservation.query.filter(
            TableReservation.table_id == table.id,
            TableReservation.date == date,
            TableReservation.time == time,
            TableReservation.status.in_(['PENDING', 'CONFIRMED'])
        ).first()

        if existing:
            return jsonify({'success': False, 'message': f'Table {table.table_number} is already reserved for {date} at {time}. Please choose another table or time slot.'}), 409

        sid = get_session_id()
        reservation = TableReservation(
            shop_id=shop_id,
            table_id=table.id,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=sid,
            guest_name=guest_name,
            guest_phone=guest_phone,
            date=date,
            time=time,
            people_count=people_count,
            seating_preference=pref,
            note=note,
            status='CONFIRMED'
        )
        db.session.add(reservation)
        db.session.commit()

        return jsonify({
            'success': True,
            'reservation_id': reservation.id,
            'shop_name': shop.name,
            'table_number': table.table_number,
            'capacity': table.capacity,
            'date': date,
            'time': time,
            'people_count': people_count,
            'seating_preference': pref,
            'message': f'Table {table.table_number} reserved successfully for {people_count} people on {date} at {time}!'
        })

    return render_template('dine_in/reserve.html', shop=shop, tables=tables)


# ─── MY RESERVATIONS PAGE ─────────────────────────────────────────────────────
@dine_in_bp.route('/my-reservations')
def my_reservations():
    sid = get_session_id()
    if current_user.is_authenticated:
        reservations = TableReservation.query.filter(
            (TableReservation.user_id == current_user.id) | (TableReservation.session_id == sid)
        ).order_by(TableReservation.created_at.desc()).all()
    else:
        reservations = TableReservation.query.filter_by(session_id=sid).order_by(TableReservation.created_at.desc()).all()

    return render_template('dine_in/my_reservations.html', reservations=reservations)


# ─── QR CODE SCAN ─────────────────────────────────────────────────────────────
@dine_in_bp.route('/qr/<qr_code>')
def qr_menu(qr_code):
    table = Table.query.filter_by(qr_code=qr_code, is_active=True).first_or_404()
    shop  = table.shop
    from models import MenuCategory
    categories = MenuCategory.query.filter_by(shop_id=shop.id).order_by(MenuCategory.sort_order).all()

    session['dine_in_table'] = qr_code
    session['dine_in_shop']  = shop.id

    return render_template('dine_in/table_menu.html', shop=shop, table=table, categories=categories)


# ─── DINE-IN ORDER ────────────────────────────────────────────────────────────
@dine_in_bp.route('/order', methods=['POST'])
def place_dine_in_order():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON request body is required.'}), 400
    session_qr = session.get('dine_in_table')
    qr_code = data.get('qr_code') or session_qr
    items = data.get('items', [])
    note = data.get('note', '')
    sid = get_session_id()

    if not session_qr or qr_code != session_qr:
        return jsonify({'success': False, 'message': 'Scan the table QR code before placing an order.'}), 403

    table = Table.query.filter_by(qr_code=qr_code, is_active=True).first()
    if not table:
        return jsonify({'success': False, 'message': 'Invalid table'}), 400

    shop = table.shop
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'message': 'Add at least one item to your order.'}), 400

    validated_items = []
    seen_item_ids = set()
    for item_data in items:
        if not isinstance(item_data, dict):
            return jsonify({'success': False, 'message': 'Invalid order item.'}), 400
        menu_item = MenuItem.query.filter_by(id=item_data.get('item_id'), shop_id=shop.id, is_available=True).first()
        try:
            quantity = int(item_data.get('quantity'))
        except (TypeError, ValueError):
            quantity = 0
        if not menu_item or not 1 <= quantity <= MAX_ITEM_QUANTITY or menu_item.id in seen_item_ids:
            return jsonify({'success': False, 'message': 'One or more order items are invalid or unavailable.'}), 400
        seen_item_ids.add(menu_item.id)
        validated_items.append((menu_item, quantity))

    total = 0
    order = Order(
        shop_id=shop.id,
        order_type='DINE_IN',
        table_id=table.id,
        user_id=current_user.id if current_user.is_authenticated else None,
        session_id=sid,
        special_note=note,
        payment_method='cash'
    )
    order.generate_order_number()
    db.session.add(order)
    db.session.flush()

    for menu_item, qty in validated_items:
        oi = OrderItem(order_id=order.id, menu_item_id=menu_item.id,
                       quantity=qty, unit_price=menu_item.price,
                       total_price=menu_item.price * qty)
        db.session.add(oi)
        total += menu_item.price * qty

    order.total_amount = total
    table.status = 'OCCUPIED'
    ko = KitchenOrder(order_id=order.id, shop_id=shop.id)
    db.session.add(ko)
    CartItem.query.filter_by(session_id=sid).delete()
    if current_user.is_authenticated:
        CartItem.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    session['_id'] = str(uuid.uuid4())

    return jsonify({'success': True, 'order_number': order.order_number,
                    'total': total, 'message': 'Order placed! Kitchen is notified.'})


# ─── WAITER REQUEST ───────────────────────────────────────────────────────────
@dine_in_bp.route('/waiter/request', methods=['POST'])
def waiter_request():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON request body is required.'}), 400
    session_qr = session.get('dine_in_table')
    qr_code = data.get('qr_code') or session_qr
    request_type = data.get('request_type', 'WAITER')

    if not session_qr or qr_code != session_qr:
        return jsonify({'success': False, 'message': 'Scan the table QR code before requesting service.'}), 403
    if request_type not in ALLOWED_WAITER_REQUESTS:
        return jsonify({'success': False, 'message': 'Invalid service request.'}), 400

    table = Table.query.filter_by(qr_code=qr_code, is_active=True).first()
    if not table:
        return jsonify({'success': False, 'message': 'Invalid table'}), 400

    wr = WaiterRequest(table_id=table.id, shop_id=table.shop_id,
                       request_type=request_type, status='PENDING')
    db.session.add(wr)
    db.session.commit()

    labels = {'WAITER': '🔔 Waiter called!', 'WATER': '💧 Water requested!',
              'BILL': '🧾 Bill requested!', 'MENU': '📋 Menu requested!',
              'CLEANING': '🧹 Cleaning requested!'}
    return jsonify({'success': True, 'message': labels.get(request_type, 'Request sent!')})


# ─── TABLE STATUS API ─────────────────────────────────────────────────────────
@dine_in_bp.route('/table-status/<int:shop_id>')
def table_status(shop_id):
    tables = Table.query.filter_by(shop_id=shop_id, is_active=True).all()
    return jsonify([{'id': t.id, 'number': t.table_number,
                     'status': t.status, 'capacity': t.capacity,
                     'location': t.location_desc or 'Main hall'} for t in tables])
