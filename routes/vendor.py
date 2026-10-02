from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from models import db, Shop, Order, MenuItem, MenuCategory, Table, TableReservation, KitchenOrder

vendor_bp = Blueprint('vendor', __name__)
ORDER_STATUSES = {'PENDING', 'ACCEPTED', 'PREPARING', 'READY', 'DELIVERED', 'CANCELLED'}
TABLE_STATUSES = {'AVAILABLE', 'OCCUPIED', 'RESERVED'}

def get_vendor_shop():
    return Shop.query.filter_by(vendor_id=current_user.id).first()


def require_shop_access(shop):
    """Allow an admin or the vendor assigned to this exact shop."""
    if current_user.role == 'admin':
        return
    if current_user.role != 'vendor' or shop.vendor_id != current_user.id:
        abort(403)

@vendor_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role not in ('vendor', 'admin'):
        flash('Access denied.', 'danger')
        return redirect(url_for('home.index'))
    shop = get_vendor_shop()
    if not shop and current_user.role != 'admin':
        flash('No shop linked to your account.', 'warning')
        return redirect(url_for('home.index'))

    shops = [shop] if shop else Shop.query.all()
    stats = {}
    for s in shops:
        today_orders  = Order.query.filter_by(shop_id=s.id).count()
        pending_count = Order.query.filter_by(shop_id=s.id, status='PENDING').count()
        total_revenue = db.session.query(db.func.sum(Order.total_amount)).filter_by(shop_id=s.id).scalar() or 0
        active_tables = Table.query.filter_by(shop_id=s.id, status='OCCUPIED').count()
        stats[s.id]   = {
            'orders': today_orders, 'pending': pending_count,
            'revenue': total_revenue, 'active_tables': active_tables
        }
    return render_template('vendor/dashboard.html', shops=shops, stats=stats)

@vendor_bp.route('/orders/<int:shop_id>')
@login_required
def orders(shop_id):
    shop   = Shop.query.get_or_404(shop_id)
    require_shop_access(shop)
    status = request.args.get('status', '')
    otype  = request.args.get('type', '')
    q      = Order.query.filter_by(shop_id=shop_id)
    if status: q = q.filter_by(status=status)
    if otype:  q = q.filter_by(order_type=otype)
    all_orders = q.order_by(Order.created_at.desc()).all()
    return render_template('vendor/orders.html', shop=shop, orders=all_orders)

@vendor_bp.route('/order/update', methods=['POST'])
@login_required
def update_order():
    data      = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON request body is required.'}), 400
    order_id  = data.get('order_id')
    new_status= data.get('status')
    order     = Order.query.get_or_404(order_id)
    require_shop_access(order.shop)
    if new_status not in ORDER_STATUSES:
        return jsonify({'success': False, 'message': 'Invalid order status.'}), 400
    order.status = new_status
    if order.kitchen_order:
        kitchen_status = 'SERVED' if new_status == 'DELIVERED' else new_status
        order.kitchen_order.status = kitchen_status
    db.session.commit()
    return jsonify({'success': True})

@vendor_bp.route('/tables/<int:shop_id>')
@login_required
def tables(shop_id):
    shop   = Shop.query.get_or_404(shop_id)
    require_shop_access(shop)
    tables = Table.query.filter_by(shop_id=shop_id).all()
    pending_reservations = TableReservation.query.filter_by(shop_id=shop_id, status='PENDING').all()
    return render_template('vendor/tables.html', shop=shop, tables=tables,
                           reservations=pending_reservations)

@vendor_bp.route('/tables/update-status', methods=['POST'])
@login_required
def update_table_status():
    data      = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON request body is required.'}), 400
    table_id  = data.get('table_id')
    new_status= data.get('status')
    table     = Table.query.get_or_404(table_id)
    require_shop_access(table.shop)
    if new_status not in TABLE_STATUSES:
        return jsonify({'success': False, 'message': 'Invalid table status.'}), 400
    table.status = new_status
    db.session.commit()
    return jsonify({'success': True})

@vendor_bp.route('/menu/<int:shop_id>')
@login_required
def menu_manage(shop_id):
    shop       = Shop.query.get_or_404(shop_id)
    require_shop_access(shop)
    categories = MenuCategory.query.filter_by(shop_id=shop_id).order_by(MenuCategory.sort_order).all()
    return render_template('vendor/menu_manage.html', shop=shop, categories=categories)

@vendor_bp.route('/menu/toggle/<int:item_id>', methods=['POST'])
@login_required
def toggle_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    require_shop_access(item.shop)
    item.is_available = not item.is_available
    db.session.commit()
    return jsonify({'success': True, 'available': item.is_available})

@vendor_bp.route('/reservations/confirm/<int:res_id>', methods=['POST'])
@login_required
def confirm_reservation(res_id):
    res = TableReservation.query.get_or_404(res_id)
    require_shop_access(res.shop)
    res.status = 'CONFIRMED'
    db.session.commit()
    return jsonify({'success': True})
