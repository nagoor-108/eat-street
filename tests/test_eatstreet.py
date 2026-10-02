import unittest
import json
from app import create_app
from models import db, User, Shop, Table, MenuItem, TableReservation, CartItem, Order, OrderItem
from ollama_rag import is_relevant_query, chat_with_ollama, SCOPE_REFUSAL_MESSAGE

class TestEatStreetEnhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False  # disable CSRF form enforcement in test client

    def setUp(self):
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    # ─── 1. TEST DOUBLE BOOKING REJECTION ─────────────────────────────────────
    def test_double_booking_rejected(self):
        """Verify that two bookings for the same table, date, and time are rejected with HTTP 409."""
        shop = Shop.query.filter_by(is_active=True).first()
        self.assertIsNotNone(shop)
        table = Table.query.filter_by(shop_id=shop.id, is_active=True).first()
        self.assertIsNotNone(table)

        test_date = "2026-10-15"
        test_time = "19:00"

        # Clean up any existing test reservation for this slot
        TableReservation.query.filter_by(
            table_id=table.id, date=test_date, time=test_time
        ).delete()
        db.session.commit()

        # First booking - should succeed
        res1 = self.client.post(f'/dine-in/reserve/{shop.id}', data={
            'date': test_date,
            'time': test_time,
            'people_count': min(2, table.capacity),
            'seating_preference': 'Any',
            'table_id': table.id,
            'guest_name': 'Test User 1',
            'guest_phone': '9876543210',
            'note': 'Window table please'
        })
        data1 = res1.get_json()
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(data1.get('success'))

        # Second booking for the EXACT same table, date, and time - must be rejected
        res2 = self.client.post(f'/dine-in/reserve/{shop.id}', data={
            'date': test_date,
            'time': test_time,
            'people_count': min(2, table.capacity),
            'seating_preference': 'Any',
            'table_id': table.id,
            'guest_name': 'Test User 2',
            'guest_phone': '9876543211',
            'note': 'Duplicate booking attempt'
        })
        data2 = res2.get_json()
        self.assertEqual(res2.status_code, 409, f"Expected 409 Conflict, got {res2.status_code}")
        self.assertFalse(data2.get('success'))
        self.assertIn('already reserved', data2.get('message', '').lower())

    # ─── 2. TEST INSUFFICIENT CAPACITY REJECTION ──────────────────────────────
    def test_insufficient_capacity_rejected(self):
        """Verify that booking a table with insufficient capacity is rejected with HTTP 400."""
        # Find a table with small capacity (e.g. 2 seats)
        table = Table.query.filter(Table.capacity <= 4, Table.is_active == True).first()
        self.assertIsNotNone(table)
        shop = table.shop

        # Request more people than capacity
        oversized_people = table.capacity + 5
        res = self.client.post(f'/dine-in/reserve/{shop.id}', data={
            'date': '2026-10-20',
            'time': '20:00',
            'people_count': oversized_people,
            'seating_preference': 'Any',
            'table_id': table.id,
            'guest_name': 'Big Group',
            'guest_phone': '9876543210'
        })
        data = res.get_json()
        self.assertEqual(res.status_code, 400)
        self.assertFalse(data.get('success'))
        self.assertIn('capacity', data.get('message', '').lower())

    # ─── 3. TEST MULTIPLE CART ITEMS AND QUANTITY SUM ─────────────────────────
    def test_multiple_cart_items_and_quantity_sum(self):
        """Verify adding multiple items from multiple shops correctly calculates total quantity sum and displays them."""
        # Get items from two different shops
        shops = Shop.query.filter_by(is_active=True).all()
        self.assertGreaterEqual(len(shops), 2)

        item1 = MenuItem.query.filter_by(shop_id=shops[0].id, is_available=True).first()
        item2 = MenuItem.query.filter_by(shop_id=shops[1].id, is_available=True).first()
        self.assertIsNotNone(item1)
        self.assertIsNotNone(item2)

        # Clear cart for session first
        with self.client.session_transaction() as sess:
            sess['_id'] = 'test-cart-session-123'
            sid = sess['_id']

        CartItem.query.filter_by(session_id=sid).delete()
        db.session.commit()

        # Add item 1 with qty 2
        r1 = self.client.post('/orders/cart/add', json={
            'item_id': item1.id,
            'quantity': 2,
            'order_type': 'TAKEAWAY'
        })
        d1 = r1.get_json()
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(d1.get('cart_count'), 2)

        # Add item 2 from different shop with qty 3
        r2 = self.client.post('/orders/cart/add', json={
            'item_id': item2.id,
            'quantity': 3,
            'order_type': 'TAKEAWAY'
        })
        d2 = r2.get_json()
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(d2.get('cart_count'), 5, "Total cart count should equal sum of all item quantities (2 + 3 = 5)")

        # Verify Cart page contains both items, images, and prices
        cart_page = self.client.get('/orders/cart')
        self.assertEqual(cart_page.status_code, 200)
        cart_html = cart_page.get_data(as_text=True)
        self.assertIn(item1.name, cart_html)
        self.assertIn(item2.name, cart_html)
        self.assertIn('5 items', cart_html)

        # Verify /orders/cart/data returns JSON with items for "Your Order" sidebar widget
        data_res = self.client.get('/orders/cart/data')
        self.assertEqual(data_res.status_code, 200)
        cart_json = data_res.get_json()
        self.assertTrue(cart_json.get('success'))
        self.assertEqual(cart_json.get('cart_count'), 5)
        self.assertEqual(len(cart_json.get('items')), 2)
        self.assertEqual(cart_json['items'][0]['name'], item1.name)
        self.assertEqual(cart_json['items'][1]['name'], item2.name)

    # ─── 4. TEST CHECKOUT AND MY ORDERS DISPLAY ───────────────────────────────
    def test_checkout_and_my_orders(self):
        """Verify multi-shop checkout splits into separate orders and displays them in My Orders."""
        shops = Shop.query.filter_by(is_active=True).all()
        item1 = MenuItem.query.filter_by(shop_id=shops[0].id, is_available=True).first()
        item2 = MenuItem.query.filter_by(shop_id=shops[1].id, is_available=True).first()

        user = User.query.filter_by(email='customer@eatstreet.in').first()
        if not user:
            user = User(name='Test Customer', email='customer@eatstreet.in', role='customer')
            user.set_password('customer123')
            db.session.add(user)
            db.session.commit()

        with self.client.session_transaction() as sess:
            sess['_id'] = 'test-order-session-456'
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
            sid = sess['_id']

        CartItem.query.filter_by(session_id=sid).delete()
        db.session.commit()

        # Add items to cart
        self.client.post('/orders/cart/add', json={'item_id': item1.id, 'quantity': 1, 'order_type': 'TAKEAWAY'})
        self.client.post('/orders/cart/add', json={'item_id': item2.id, 'quantity': 2, 'order_type': 'TAKEAWAY'})

        # Post Checkout
        checkout_res = self.client.post('/orders/checkout', data={
            'order_type': 'TAKEAWAY',
            'pickup_time': '20:30',
            'payment_method': 'cash',
            'special_note': 'Pack neatly please'
        }, follow_redirects=True)

        self.assertEqual(checkout_res.status_code, 200)
        my_orders_html = checkout_res.get_data(as_text=True)

        # Verify My Orders page shows the orders
        self.assertIn('My Orders', my_orders_html)
        self.assertIn(shops[0].name, my_orders_html)
        self.assertIn(shops[1].name, my_orders_html)
        self.assertIn(item1.name, my_orders_html)
        self.assertIn(item2.name, my_orders_html)

    # ─── 5. TEST CHATBOT SCOPE RESTRICTION ────────────────────────────────────
    def test_chatbot_scope_restriction(self):
        """Verify that unrelated questions strictly receive the appropriate scope refusal message in selected language."""
        from ollama_rag import SCOPE_REFUSAL_MESSAGES
        unrelated_questions = [
            "Write a python program to reverse a linked list",
            "Who is the president of the United States?",
            "What is the capital of France?",
            "How do I invest in bitcoin cryptocurrency?",
            "Give me relationship advice"
        ]

        for q in unrelated_questions:
            self.assertFalse(is_relevant_query(q), f"Query '{q}' should be classified as NOT relevant")
            # Test Telugu
            reply_te = chat_with_ollama(q, context="", lang='te')
            self.assertEqual(reply_te, SCOPE_REFUSAL_MESSAGES['te'])
            # Test English
            reply_en = chat_with_ollama(q, context="", lang='en')
            self.assertEqual(reply_en, SCOPE_REFUSAL_MESSAGES['en'])
            # Test Teluglish
            reply_tg = chat_with_ollama(q, context="", lang='teluglish')
            self.assertEqual(reply_tg, SCOPE_REFUSAL_MESSAGES['teluglish'])
            # Test Hindi
            reply_hi = chat_with_ollama(q, context="", lang='hi')
            self.assertEqual(reply_hi, SCOPE_REFUSAL_MESSAGES['hi'])

        # Test relevant questions
        relevant_q = "What biryani dishes are available?"
        self.assertTrue(is_relevant_query(relevant_q))
        rel_reply = chat_with_ollama(relevant_q, context="ITEM:Chicken Dum Biryani Rs.180 [N]\nITEM:Mutton Biryani Rs.220 [N]", lang='en')
        self.assertIn("Biryani", rel_reply)
        self.assertNotEqual(rel_reply, SCOPE_REFUSAL_MESSAGES['en'])

if __name__ == '__main__':
    unittest.main()
