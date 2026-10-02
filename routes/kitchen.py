from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user
from models import db, Shop, Order, KitchenOrder, WaiterRequest, Table

kitchen_bp = Blueprint('kitchen', __name__)


def require_shop_access(shop):
    if current_user.role == 'admin':
        return
    if current_user.role != 'vendor' or shop.vendor_id != current_user.id:
        abort(403)

@kitchen_bp.route('/<int:shop_id>')
@login_required
def display(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    require_shop_access(shop)

    kitchen_orders = (KitchenOrder.query
                      .filter_by(shop_id=shop_id)
                      .filter(KitchenOrder.status.notin_(['SERVED', 'CANCELLED']))
                      .order_by(KitchenOrder.created_at.asc())
                      .all())
    waiter_requests = (WaiterRequest.query
                       .filter_by(shop_id=shop_id, status='PENDING')
                       .order_by(WaiterRequest.created_at.asc())
                       .all())
    return render_template('dine_in/kitchen.html',
                           shop=shop,
                           kitchen_orders=kitchen_orders,
                           waiter_requests=waiter_requests)

@kitchen_bp.route('/update', methods=['POST'])
@login_required
def update_status():
    data      = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON request body is required.'}), 400
    ko_id     = data.get('kitchen_order_id')
    new_status= data.get('status')

    valid_statuses = ['ACCEPTED', 'PREPARING', 'READY', 'SERVED', 'CANCELLED']
    if new_status not in valid_statuses:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400

    ko = KitchenOrder.query.get_or_404(ko_id)
    require_shop_access(ko.shop)
    ko.status = new_status
    # mirror to main order
    ko.order.status = new_status if new_status != 'SERVED' else 'DELIVERED'
    db.session.commit()
    return jsonify({'success': True, 'status': new_status})

@kitchen_bp.route('/waiter/done/<int:wr_id>', methods=['POST'])
@login_required
def resolve_waiter_request(wr_id):
    wr = WaiterRequest.query.get_or_404(wr_id)
    require_shop_access(wr.shop)
    wr.status = 'DONE'
    db.session.commit()
    return jsonify({'success': True})

@kitchen_bp.route('/orders/<int:shop_id>')
@login_required
def get_kitchen_orders(shop_id):
    """Polling endpoint for real-time kitchen updates."""
    shop = Shop.query.get_or_404(shop_id)
    require_shop_access(shop)
    kitchen_orders = (KitchenOrder.query
                      .filter_by(shop_id=shop_id)
                      .filter(KitchenOrder.status.notin_(['SERVED', 'CANCELLED']))
                      .order_by(KitchenOrder.created_at.asc())
                      .all())
    data = []
    for ko in kitchen_orders:
        order = ko.order
        data.append({
            'ko_id': ko.id,
            'order_number': order.order_number,
            'table': order.table.table_number if order.table else '—',
            'order_type': order.order_type,
            'status': ko.status,
            'items': [{'name': i.menu_item.name, 'qty': i.quantity} for i in order.items],
            'note': order.special_note,
            'created_at': order.created_at.strftime('%H:%M')
        })
    return jsonify(data)
