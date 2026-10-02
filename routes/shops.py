from flask import Blueprint, render_template, abort
from models import Shop, MenuItem, MenuCategory, Table

shops_bp = Blueprint('shops', __name__)

@shops_bp.route('/')
def list_shops():
    shops = Shop.query.filter_by(is_active=True).order_by(Shop.rating.desc()).all()
    return render_template('shops/list.html', shops=shops)

@shops_bp.route('/<int:shop_id>')
def detail(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    categories = MenuCategory.query.filter_by(shop_id=shop_id).order_by(MenuCategory.sort_order).all()
    tables = Table.query.filter_by(shop_id=shop_id, is_active=True).all() if shop.dine_in else []
    return render_template('shops/detail.html', shop=shop, categories=categories, tables=tables)
