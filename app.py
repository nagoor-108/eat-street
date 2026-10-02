import os
import re
from flask import Flask, jsonify, request, current_app
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from config import Config
from models import db, bcrypt, User

login_manager = LoginManager()
csrf = CSRFProtect()

MENU_ITEM_IMAGE_ALIASES = {
    'chicken_lollipops': 'chicken_lollipops.jpg',
    'chicken_wings': 'chicken_wings_bbq.jpg',
    'chicken_kabab': 'chicken_kabab.jpg',
    'chicken_tikka': 'chicken_tikka.jpg',
    'chicken_malai_tikka': 'chicken_malai_tikka.jpg',
    'chicken_leg_kabab': 'chicken_leg_kabab.jpg',
    'chicken_sticks': 'chicken_sticks.jpg',
    'chicken_wing_kabab': 'chicken_wing_kabab.jpg',
    'combo_a_lollipops_wings_leg': 'combo_a.jpg',
    'combo_b_lollipops_wings_leg_kabab': 'combo_b.jpg',
    'combo_c_leg_kabab_wing_kabab_lollipops': 'combo_c.jpg',
    'combo_d_wing_kabab_lollipops_wings': 'combo_d.jpg',
    'veg_noodles': 'veg_noodles.jpg',
    'veg_fried_rice': 'veg_fried_rice.jpg',
    'veg_manchurian': 'veg_manchurian.jpg',
    'veg_spring_rolls': 'spring_rolls.jpg',
    'chicken_noodles': 'chicken_noodles.jpg',
    'chicken_fried_rice': 'chicken_fried_rice.jpg',
    'chicken_manchurian': 'chicken_manchurian.jpg',
    'chicken_65': 'chicken_65.jpg',
    'egg_frankie': 'egg_frankie.jpg',
    'chicken_frankie': 'chicken_frankie.jpg',
    'paneer_frankie': 'paneer_frankie.jpg',
    'double_egg_frankie': 'double_egg_frankie.jpg',
    'veg_frankie': 'veg_frankie.jpg',
    'mushroom_pakodi': 'mushroom_pakodi.jpg',
    'mushroom_fry': 'mushroom_fry.jpg',
    'mushroom_65': 'mushroom_chilli.jpg',
    'paneer_pakodi': 'paneer_pakodi.jpg',
    'onion_pakodi': 'onion_pakodi.jpg',
    'mix_veg_pakodi': 'mix_veg_pakodi.jpg',
    'chicken_tikka_bbq': 'chicken_tikka_bbq.jpg',
    'chicken_wings_bbq': 'chicken_wings_bbq.jpg',
    'seekh_kabab': 'seekh_kabab.jpg',
    'peri_peri_chicken': 'peri_peri_chicken.jpg',
    'bbq_paneer_tikka': 'paneer_tikka.jpg',
    'party_platter_chicken': 'bbq_party_platter.jpg',
    'party_platter_mixed': 'bbq_party_platter_mixed.jpg',
    'chicken_biryani': 'chicken_biryani.jpg',
    'chicken_dum_biryani': 'chicken_dum_biryani.jpg',
    'chicken_boneless_biryani': 'chicken_boneless_biryani.jpg',
    'mutton_biryani': 'mutton_biryani.jpg',
    'mutton_dum_biryani': 'mutton_dum_biryani.jpg',
    'veg_biryani': 'veg_biryani.jpg',
    'paneer_biryani': 'paneer_biryani.jpg',
    'chicken_shawarma': 'chicken_shawarma.jpg',
    'double_shawarma': 'double_shawarma.jpg',
    'egg_shawarma': 'egg_shawarma.jpg',
    'paneer_shawarma': 'paneer_shawarma.jpg',
    'shawarma_plate': 'shawarma_plate.jpg',
    'steamed_veg_momos': 'steamed_momos.jpg',
    'fried_veg_momos': 'fried_momos.jpg',
    'steamed_chicken_momos': 'steamed_chicken_momos.jpg',
    'fried_chicken_momos': 'fried_chicken_momos.jpg',
    'tandoor_momos': 'tandoor_momos.jpg',
    'cheese_momos': 'cheese_momos.jpg',
    'classic_waffle': 'classic_waffle.jpg',
    'chocolate_waffle': 'chocolate_waffle.jpg',
    'oreo_waffle': 'oreo_waffle.jpg',
    'strawberry_waffle': 'strawberry_waffle.jpg',
    'ice_cream_waffle': 'ice_cream_waffle.jpg',
    'chocolate_milkshake': 'chocolate_milkshake.jpg',
    'oreo_shake': 'oreo_shake.jpg',
    'vanilla_ice_cream': 'vanilla_ice_cream.jpg',
    'pani_puri': 'pani_puri.jpg',
    'bhel_puri': 'bhel_puri.jpg',
    'sev_puri': 'sev_puri.jpg',
    'samosa': 'samosa.jpg',
    'chole_bhature': 'chole_bhature.jpg',
    'pottikalu': 'pottikalu.jpg',
    'millet_idly': 'millet_idli.jpg',
    'ragi_sangati': 'ragi_sangati.jpg',
    'natukodi_pulusu': 'natukodi_pulusu.jpg',
}


def normalize_menu_item_name(name):
    return re.sub(r'[^a-z0-9]+', '_', (name or '').lower()).strip('_')


def resolve_menu_item_image(item):
    if item is None:
        return 'default_food.jpg'

    current_image = getattr(item, 'image', None) or ''
    if current_image and current_image not in ('default_food.jpg', 'default_shop.jpg'):
        return current_image

    lookup_name = normalize_menu_item_name(getattr(item, 'name', ''))
    mapped = MENU_ITEM_IMAGE_ALIASES.get(lookup_name)
    if mapped:
        return mapped

    static_dir = os.path.join(current_app.root_path, 'static', 'images')
    for candidate in (lookup_name + '.jpg', lookup_name + '.jpeg', lookup_name + '.png'):
        if os.path.exists(os.path.join(static_dir, candidate)):
            return candidate

    return 'default_food.jpg'


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Init extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.root_path, 'static', 'qrcodes'), exist_ok=True)

    # Register blueprints
    from routes.home import home_bp
    from routes.auth import auth_bp
    from routes.shops import shops_bp
    from routes.orders import orders_bp
    from routes.dine_in import dine_in_bp
    from routes.kitchen import kitchen_bp
    from routes.vendor import vendor_bp
    from routes.ai_chat import ai_chat_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(shops_bp, url_prefix='/shops')
    app.register_blueprint(orders_bp, url_prefix='/orders')
    app.register_blueprint(dine_in_bp, url_prefix='/dine-in')
    app.register_blueprint(kitchen_bp, url_prefix='/kitchen')
    app.register_blueprint(vendor_bp, url_prefix='/vendor')
    app.register_blueprint(ai_chat_bp, url_prefix='/ai')
    csrf.exempt(ai_chat_bp)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    # Inject cart count into every template
    from flask_login import current_user
    from flask import session
    from models import CartItem

    @app.context_processor
    def inject_cart():
        sid = session.get('_id', 'guest')
        total_items = db.session.query(db.func.coalesce(db.func.sum(CartItem.quantity), 0)).filter(CartItem.session_id == sid).scalar()
        return dict(cart_count=int(total_items or 0), resolve_menu_item_image=resolve_menu_item_image)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if request.is_json:
            return jsonify({'success': False, 'message': 'Your session expired. Refresh the page and try again.'}), 400
        return f'Bad request: {error.description}', 400

    return app


app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # threaded=True lets Ollama's long calls run without blocking other requests
    app.run(debug=os.environ.get('FLASK_DEBUG', '').lower() == 'true', port=5000, threaded=True)
