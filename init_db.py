"""
Database initializer — creates tables and seeds with Kakinada Eat Street data.
Run: python init_db.py
"""
import os, sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import secrets
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from models import db, User, Shop, MenuCategory, MenuItem, Table
import qrcode
import uuid


def make_qr(data: str, filename: str):
    """Generate a QR code and save it."""
    qr_dir = os.path.join(os.path.dirname(__file__), 'static', 'qrcodes')
    os.makedirs(qr_dir, exist_ok=True)
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#FF3B00", back_color="white")
    img.save(os.path.join(qr_dir, filename))
    return filename


def seed(reset=False):
    app = create_app()
    with app.app_context():
        db.create_all()
        if Shop.query.first() and not reset:
            print("Database already contains data. Use: python init_db.py --reset")
            return
        if reset:
            db.drop_all()
        db.create_all()
        print("✅ Tables created.")
        demo_password = os.environ.get('DEMO_PASSWORD') or secrets.token_urlsafe(12)

        # ─── ADMIN USER ─────────────────────────────────────────────────────
        admin = User(name='Eat Street Admin', email='admin@eatstreet.in',
                     phone='9999999999', role='admin')
        admin.set_password(demo_password)
        db.session.add(admin)

        # ─── VENDOR USERS ────────────────────────────────────────────────────
        vendors = []
        vendor_data = [
            ('Ravi Kumar', 'ravi@eatstreet.in', '9876543210'),
            ('Suresh Babu', 'suresh@eatstreet.in', '9876543211'),
            ('Anitha Reddy', 'anitha@eatstreet.in', '9876543212'),
            ('Mohammed Ali', 'ali@eatstreet.in', '9876543213'),
            ('Bullet Sharma', 'bullet@eatstreet.in', '9876543214'),
        ]
        for name, email, phone in vendor_data:
            v = User(name=name, email=email, phone=phone, role='vendor')
            v.set_password(demo_password)
            db.session.add(v)
            vendors.append(v)

        # Sample customer
        customer = User(name='Test Customer', email='customer@test.in',
                        phone='9000000001', role='customer')
        customer.set_password(demo_password)
        db.session.add(customer)
        db.session.flush()

        # ─── SHOPS ────────────────────────────────────────────────────────────
        shops_data = [
            # (code, name, telugu, desc, category, rating, reviews, opening, closing, dine_in, takeaway, delivery, vendor_idx)
            ('ES001', 'Chicken Corner', 'చికెన్ కార్నర్',
             'Famous for crispy chicken lollipops, kababs and tikka. A must-visit at Eat Street!',
             'Chicken Snacks', 4.5, 312, '17:00', '23:30', True, True, False, 0),

            ('ES002', 'Fast Food Plaza', 'ఫాస్ట్ ఫుడ్ ప్లాజా',
             'Your go-to stop for quick bites — noodles, fried rice, manchurian and more.',
             'Fast Food', 4.2, 198, '12:00', '23:00', True, True, True, 1),

            ('ES003', 'Frankie Corner', 'ఫ్రాంకీ కార్నర్',
             'Delicious wraps and frankies made fresh with egg, chicken or paneer.',
             'Rolls & Wraps', 4.3, 145, '16:00', '22:30', False, True, False, 2),

            ('ES004', 'Mushroom Magic', 'మష్రూమ్ మేజిక్',
             'Specialty: Crispy Mushroom Pakodi — a vegetarian delight loved by all.',
             'Snacks', 4.6, 89, '16:00', '22:00', False, True, False, 3),

            ('ES005', 'Bullet BBQ', 'బులెట్ బీబీక్యూ',
             'Premium BBQ & grilled specials. Accepts party orders and franchise enquiries.',
             'BBQ & Grill', 4.7, 276, '17:00', '23:30', True, True, True, 4),

            ('ES006', 'Biryani House', 'బిర్యాని హౌస్',
             'Authentic Hyderabadi and Kakinada-style biryanis cooked in traditional dum style.',
             'Biryani', 4.4, 421, '12:00', '23:00', True, True, True, 0),

            ('ES007', 'Shawarma Street', 'షావర్మా స్ట్రీట్',
             'Middle-Eastern style shawarmas with homemade sauces and fresh bread.',
             'Shawarma', 4.1, 167, '16:00', '23:00', False, True, False, 1),

            ('ES008', 'Momos & More', 'మొమోస్ & మోర్',
             'Steamed, fried and tandoor momos with spicy dipping sauces.',
             'Momos', 4.3, 203, '14:00', '22:30', False, True, False, 2),

            ('ES009', 'Waffle World', 'వఫుల్ వరల్డ్',
             'Belgian waffles, ice cream, shakes and desserts for the sweet tooth.',
             'Desserts & Waffles', 4.5, 134, '15:00', '23:00', True, True, False, 3),

            ('ES010', 'Chaat & Chat', 'చాట్ & చాట్',
             'Traditional Indian chaat, samosas, pani puri and regional Andhra snacks.',
             'Chaat & Snacks', 4.2, 310, '14:00', '22:00', False, True, False, 4),
        ]

        shop_img_map = {
            'Chicken Corner': 'shop_chicken_corner.jpg',
            'Fast Food Plaza': 'shop_fast_food_plaza.jpg',
            'Frankie Corner': 'shop_frankie_corner.jpg',
            'Mushroom Magic': 'shop_mushroom_magic.jpg',
            'Bullet BBQ': 'shop_bullet_bbq.jpg',
            'Biryani House': 'shop_biryani_house.jpg',
            'Shawarma Street': 'shop_shawarma_street.jpg',
            'Momos & More': 'shop_momos_more.jpg',
            'Waffle World': 'shop_waffle_world.jpg',
            'Chaat & Chat': 'shop_chaat_chat.jpg'
        }
        shop_objects = []
        for s in shops_data:
            shop = Shop(
                shop_code=s[0], name=s[1], telugu_name=s[2], description=s[3],
                category=s[4], rating=s[5], total_reviews=s[6],
                opening_time=s[7], closing_time=s[8],
                dine_in=s[9], takeaway=s[10], delivery=s[11],
                table_booking=s[9], qr_ordering=s[9],
                image=shop_img_map.get(s[1], 'default_shop.jpg'),
                vendor_id=vendors[s[12]].id
            )
            db.session.add(shop)
            shop_objects.append(shop)

        db.session.flush()

        # ─── MENU DATA ────────────────────────────────────────────────────────
        # ES001 — Chicken Corner
        s = shop_objects[0]
        cats = {
            'Regular': MenuCategory(shop_id=s.id, name='Regular Menu', sort_order=1),
            'Combo':   MenuCategory(shop_id=s.id, name='Combo Deals', sort_order=2),
        }
        for c in cats.values(): db.session.add(c)
        db.session.flush()

        items_es001 = [
            # (name, price, qty_desc, veg, featured, prep, cat_key)
            ('Chicken Lollipops',   120, '4 pcs',     'non-veg', True,  15, 'Regular'),
            ('Chicken Wings',       110, '6 pcs',     'non-veg', True,  12, 'Regular'),
            ('Chicken Kabab',        70, '1 serving', 'non-veg', False, 10, 'Regular'),
            ('Chicken Tikka',        70, '1 serving', 'non-veg', True,  12, 'Regular'),
            ('Chicken Malai Tikka',  80, '1 serving', 'non-veg', False, 12, 'Regular'),
            ('Chicken Leg Kabab',    60, '1 serving', 'non-veg', False, 10, 'Regular'),
            ('Chicken Sticks',       25, '1 serving', 'non-veg', False,  8, 'Regular'),
            ('Chicken Wing Kabab',   50, '1 serving', 'non-veg', False, 10, 'Regular'),
            ('Combo A — Lollipops + Wings + Leg', 150, '2p+2p+1p', 'non-veg', False, 15, 'Combo'),
            ('Combo B — Lollipops + Wings + Leg Kabab', 200, '3p+3p+1p', 'non-veg', False, 18, 'Combo'),
            ('Combo C — Leg Kabab + Wing Kabab + Lollipops', 210, '1p+2p+2p', 'non-veg', False, 18, 'Combo'),
            ('Combo D — Wing Kabab + Lollipops + Wings', 180, '1p+2p+4p', 'non-veg', False, 18, 'Combo'),
        ]
        for n, p, q, v, f, pt, cat in items_es001:
            db.session.add(MenuItem(shop_id=s.id, category_id=cats[cat].id,
                name=n, price=p, quantity_desc=q, veg_nonveg=v, is_featured=f, preparation_time=pt))

        # ES002 — Fast Food Plaza
        s = shop_objects[1]
        c_veg = MenuCategory(shop_id=s.id, name='Vegetarian', sort_order=1)
        c_chk = MenuCategory(shop_id=s.id, name='Chicken', sort_order=2)
        db.session.add_all([c_veg, c_chk])
        db.session.flush()
        items_es002 = [
            ('Veg Noodles',      80, '1 plate', 'veg',     True,  10, c_veg.id),
            ('Veg Fried Rice',   80, '1 plate', 'veg',     False, 10, c_veg.id),
            ('Veg Manchurian',   90, '1 plate', 'veg',     False, 12, c_veg.id),
            ('Veg Spring Rolls', 60, '4 pcs',   'veg',     False,  8, c_veg.id),
            ('Chicken Noodles', 100, '1 plate', 'non-veg', True,  12, c_chk.id),
            ('Chicken Fried Rice',100,'1 plate','non-veg', False, 12, c_chk.id),
            ('Chicken Manchurian',110,'1 plate','non-veg', True,  15, c_chk.id),
            ('Chicken 65',       120, '1 plate','non-veg', True,  15, c_chk.id),
        ]
        for n, p, q, v, f, pt, cid in items_es002:
            db.session.add(MenuItem(shop_id=s.id, category_id=cid,
                name=n, price=p, quantity_desc=q, veg_nonveg=v, is_featured=f, preparation_time=pt))

        # ES003 — Frankie Corner
        s = shop_objects[2]
        c_f = MenuCategory(shop_id=s.id, name='Frankies & Rolls', sort_order=1)
        db.session.add(c_f); db.session.flush()
        items_es003 = [
            ('Egg Frankie',     60, '1 roll', 'egg',     True,  8),
            ('Chicken Frankie', 80, '1 roll', 'non-veg', True,  8),
            ('Paneer Frankie',  70, '1 roll', 'veg',     True,  8),
            ('Double Egg Frankie', 80, '1 roll', 'egg',  False, 10),
            ('Veg Frankie',     50, '1 roll', 'veg',     False, 8),
        ]
        for n, p, q, v, f, pt in items_es003:
            db.session.add(MenuItem(shop_id=s.id, category_id=c_f.id,
                name=n, price=p, quantity_desc=q, veg_nonveg=v, is_featured=f, preparation_time=pt))

        # ES004 — Mushroom Magic
        s = shop_objects[3]
        c_m = MenuCategory(shop_id=s.id, name='Mushroom Specials', sort_order=1)
        c_s = MenuCategory(shop_id=s.id, name='Other Snacks', sort_order=2)
        db.session.add_all([c_m, c_s]); db.session.flush()
        items_es004 = [
            ('Mushroom Pakodi',   70, '1 plate', 'veg', True,  10, c_m.id),
            ('Mushroom Fry',      80, '1 plate', 'veg', False, 12, c_m.id),
            ('Mushroom 65',       90, '1 plate', 'veg', True,  12, c_m.id),
            ('Paneer Pakodi',     80, '1 plate', 'veg', False, 10, c_s.id),
            ('Onion Pakodi',      50, '1 plate', 'veg', False, 8,  c_s.id),
            ('Mix Veg Pakodi',    60, '1 plate', 'veg', False, 8,  c_s.id),
        ]
        for n, p, q, v, f, pt, cid in items_es004:
            db.session.add(MenuItem(shop_id=s.id, category_id=cid,
                name=n, price=p, quantity_desc=q, veg_nonveg=v, is_featured=f, preparation_time=pt))

        # ES005 — Bullet BBQ
        s = shop_objects[4]
        c_b = MenuCategory(shop_id=s.id, name='BBQ Specials', sort_order=1)
        c_p = MenuCategory(shop_id=s.id, name='Party Platters', sort_order=2)
        db.session.add_all([c_b, c_p]); db.session.flush()
        items_es005 = [
            ('Chicken Tikka BBQ',      120, '1 serving', 'non-veg', True,  20, c_b.id),
            ('Chicken Wings BBQ',      130, '6 pcs',     'non-veg', True,  20, c_b.id),
            ('Seekh Kabab',            110, '2 pcs',     'non-veg', True,  18, c_b.id),
            ('Peri-Peri Chicken',      140, '1 serving', 'non-veg', False, 20, c_b.id),
            ('BBQ Paneer Tikka',       110, '1 serving', 'veg',     True,  15, c_b.id),
            ('Party Platter — Chicken', 550, '500g',    'non-veg', False, 30, c_p.id),
            ('Party Platter — Mixed',   750, '750g',    'non-veg', False, 35, c_p.id),
        ]
        for n, p, q, v, f, pt, cid in items_es005:
            db.session.add(MenuItem(shop_id=s.id, category_id=cid,
                name=n, price=p, quantity_desc=q, veg_nonveg=v, is_featured=f, preparation_time=pt))

        # ES006 — Biryani House
        s = shop_objects[5]
        c_b1 = MenuCategory(shop_id=s.id, name='Chicken Biryani', sort_order=1)
        c_b2 = MenuCategory(shop_id=s.id, name='Mutton Biryani', sort_order=2)
        c_b3 = MenuCategory(shop_id=s.id, name='Veg Biryani', sort_order=3)
        db.session.add_all([c_b1, c_b2, c_b3]); db.session.flush()
        items_es006 = [
            ('Chicken Biryani',        160, '1 plate', 'non-veg', True,  25, c_b1.id),
            ('Chicken Dum Biryani',    180, '1 plate', 'non-veg', True,  30, c_b1.id),
            ('Chicken Boneless Biryani',200,'1 plate', 'non-veg', False, 30, c_b1.id),
            ('Mutton Biryani',         220, '1 plate', 'non-veg', True,  35, c_b2.id),
            ('Mutton Dum Biryani',     250, '1 plate', 'non-veg', False, 40, c_b2.id),
            ('Veg Biryani',            120, '1 plate', 'veg',     True,  20, c_b3.id),
            ('Paneer Biryani',         150, '1 plate', 'veg',     False, 20, c_b3.id),
        ]
        for n, p, q, v, f, pt, cid in items_es006:
            db.session.add(MenuItem(shop_id=s.id, category_id=cid,
                name=n, price=p, quantity_desc=q, veg_nonveg=v, is_featured=f, preparation_time=pt))

        # ES007 — Shawarma Street
        s = shop_objects[6]
        c_sw = MenuCategory(shop_id=s.id, name='Shawarma', sort_order=1)
        db.session.add(c_sw); db.session.flush()
        items_es007 = [
            ('Chicken Shawarma',    80, '1 roll', 'non-veg', True,  10),
            ('Double Shawarma',    130, '1 roll', 'non-veg', True,  10),
            ('Egg Shawarma',        70, '1 roll', 'egg',     False, 10),
            ('Paneer Shawarma',     80, '1 roll', 'veg',     True,  10),
            ('Shawarma Plate',     150, '1 plate','non-veg', False, 15),
        ]
        for n, p, q, v, f, pt in items_es007:
            db.session.add(MenuItem(shop_id=s.id, category_id=c_sw.id,
                name=n, price=p, quantity_desc=q, veg_nonveg=v, is_featured=f, preparation_time=pt))

        # ES008 — Momos & More
        s = shop_objects[7]
        c_mm = MenuCategory(shop_id=s.id, name='Momos', sort_order=1)
        db.session.add(c_mm); db.session.flush()
        items_es008 = [
            ('Steamed Veg Momos',     70, '6 pcs',  'veg',     True,  12),
            ('Fried Veg Momos',       80, '6 pcs',  'veg',     False, 12),
            ('Steamed Chicken Momos', 90, '6 pcs',  'non-veg', True,  15),
            ('Fried Chicken Momos',  100, '6 pcs',  'non-veg', True,  15),
            ('Tandoor Momos',        110, '6 pcs',  'non-veg', False, 18),
            ('Cheese Momos',          90, '6 pcs',  'veg',     False, 15),
        ]
        for n, p, q, v, f, pt in items_es008:
            db.session.add(MenuItem(shop_id=s.id, category_id=c_mm.id,
                name=n, price=p, quantity_desc=q, veg_nonveg=v, is_featured=f, preparation_time=pt))

        # ES009 — Waffle World
        s = shop_objects[8]
        c_w = MenuCategory(shop_id=s.id, name='Waffles', sort_order=1)
        c_d = MenuCategory(shop_id=s.id, name='Desserts & Shakes', sort_order=2)
        db.session.add_all([c_w, c_d]); db.session.flush()
        items_es009 = [
            ('Classic Waffle',        80,  '1 pc',   'veg', True,  10, c_w.id),
            ('Chocolate Waffle',      100, '1 pc',   'veg', True,  10, c_w.id),
            ('Oreo Waffle',           110, '1 pc',   'veg', False, 10, c_w.id),
            ('Strawberry Waffle',     100, '1 pc',   'veg', False, 10, c_w.id),
            ('Ice Cream Waffle',      130, '1 plate','veg', False, 12, c_w.id),
            ('Chocolate Milkshake',    80, '300ml',  'veg', True,   5, c_d.id),
            ('Oreo Shake',             90, '300ml',  'veg', False,  5, c_d.id),
            ('Vanilla Ice Cream',      60, '2 scoops','veg',False,  5, c_d.id),
        ]
        for n, p, q, v, f, pt, cid in items_es009:
            db.session.add(MenuItem(shop_id=s.id, category_id=cid,
                name=n, price=p, quantity_desc=q, veg_nonveg=v, is_featured=f, preparation_time=pt))

        # ES010 — Chaat & Chat
        s = shop_objects[9]
        c_ch = MenuCategory(shop_id=s.id, name='Chaat', sort_order=1)
        c_an = MenuCategory(shop_id=s.id, name='Andhra Snacks', sort_order=2)
        db.session.add_all([c_ch, c_an]); db.session.flush()
        items_es010 = [
            ('Pani Puri',          40, '6 pcs',   'veg', True,   5, c_ch.id),
            ('Bhel Puri',          50, '1 plate', 'veg', False,  5, c_ch.id),
            ('Sev Puri',           50, '6 pcs',   'veg', False,  5, c_ch.id),
            ('Samosa',             20, '2 pcs',   'veg', True,   5, c_ch.id),
            ('Chole Bhature',     100, '1 plate', 'veg', True,   8, c_ch.id),
            ('Pottikalu',          60, '1 plate', 'veg', True,  10, c_an.id),
            ('Millet Idly',        60, '3 pcs',   'veg', False, 15, c_an.id),
            ('Ragi Sangati',       80, '1 plate', 'veg', False, 15, c_an.id),
            ('Natukodi Pulusu',   150, '1 plate', 'non-veg', True, 20, c_an.id),
        ]
        for n, p, q, v, f, pt, cid in items_es010:
            db.session.add(MenuItem(shop_id=s.id, category_id=cid,
                name=n, price=p, quantity_desc=q, veg_nonveg=v, is_featured=f, preparation_time=pt))

        db.session.flush()

        # ─── TABLES ───────────────────────────────────────────────────────────
        table_configs = [
            (0, 8),   # shop_idx, num_tables
            (1, 6),
            (4, 10),
            (5, 8),
            (8, 6),
        ]
        locations = ['Window', 'Near entrance', 'Family area', 'Quiet area']
        caps = [2, 4, 4, 6, 4, 8, 2, 6, 4, 8]
        base_url = "http://localhost:5000"
        for shop_idx, num_tables in table_configs:
            shop = shop_objects[shop_idx]
            for t in range(1, num_tables + 1):
                qr_data = f"{base_url}/dine-in/qr/{shop.shop_code}-T{t:02d}"
                qr_file = f"{shop.shop_code}_T{t:02d}.png"
                try:
                    make_qr(qr_data, qr_file)
                except Exception:
                    pass
                tbl = Table(
                    shop_id=shop.id,
                    table_number=f"T{t:02d}",
                    capacity=caps[(t - 1) % len(caps)],
                    status='AVAILABLE',
                    qr_code=f"{shop.shop_code}-T{t:02d}",
                    location_desc=locations[(t - 1) % len(locations)]
                )
                db.session.add(tbl)

        db.session.commit()
        print("OK Tables created.")
        print("OK Database seeded successfully!")
        print(f"   Shops:   {Shop.query.count()}")
        print(f"   Items:   {MenuItem.query.count()}")
        print(f"   Tables:  {Table.query.count()}")
        print("\nDemo login credentials:")
        print(f"   Admin:    admin@eatstreet.in / {demo_password}")
        print(f"   Vendor:   ravi@eatstreet.in / {demo_password}")
        print(f"   Customer: customer@test.in / {demo_password}")


if __name__ == '__main__':
    seed(reset='--reset' in sys.argv)
