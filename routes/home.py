from flask import Blueprint, render_template, request, jsonify, abort
from models import Shop, MenuItem, MenuCategory
import math

home_bp = Blueprint('home', __name__)

@home_bp.route('/')
def index():
    featured_shops = Shop.query.filter_by(is_active=True).order_by(Shop.rating.desc()).limit(6).all()
    featured_items = MenuItem.query.filter_by(is_featured=True, is_available=True).limit(8).all()
    categories = ['Chicken Snacks', 'Biryani', 'Fast Food', 'BBQ & Grill',
                  'Momos', 'Shawarma', 'Rolls & Wraps', 'Desserts & Waffles', 'Chaat & Snacks']
    return render_template('index.html',
                           shops=featured_shops,
                           featured_items=featured_items,
                           categories=categories)

@home_bp.route('/search')
def search():
    q = request.args.get('q', '').strip()
    veg = request.args.get('veg', '')
    max_price = request.args.get('max_price', '')
    category = request.args.get('category', '')

    items_query = MenuItem.query.filter_by(is_available=True)
    if q:
        items_query = items_query.filter(MenuItem.name.ilike(f'%{q}%'))
    if veg:
        items_query = items_query.filter(MenuItem.veg_nonveg == veg)
    if max_price:
        try:
            price_limit = float(max_price)
        except ValueError:
            abort(400, description='max_price must be a number.')
        if not math.isfinite(price_limit) or price_limit < 0:
            abort(400, description='max_price must be a non-negative number.')
        items_query = items_query.filter(MenuItem.price <= price_limit)

    shops_query = Shop.query.filter_by(is_active=True)
    if q:
        shops_query = shops_query.filter(Shop.name.ilike(f'%{q}%') | Shop.category.ilike(f'%{q}%'))
    if category:
        shops_query = shops_query.filter(Shop.category == category)

    return render_template('search.html',
                           items=items_query.limit(30).all(),
                           shops=shops_query.limit(10).all(),
                           query=q)

@home_bp.route('/ai-test')
def ai_test():
    return render_template('ai_test.html')
