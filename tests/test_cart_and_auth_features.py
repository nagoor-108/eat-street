import unittest
from app import create_app
from models import db, User, Shop, MenuItem, CartItem, Order

class TestCartAndAuthFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

    def setUp(self):
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    # ─── 1. TEST CART CLEAR ENDPOINT & CHECKOUT CLEAR ─────────────────────────
    def test_cart_clear_endpoint_and_checkout_clear(self):
        """Verify cart items are cleared on /cart/clear and on placing a new order."""
        item = MenuItem.query.filter_by(is_available=True).first()
        self.assertIsNotNone(item)

        user = User.query.filter_by(email='customer@eatstreet.in').first()
        if not user:
            user = User(name='Test Customer', email='customer@eatstreet.in', role='customer')
            user.set_password('customer123')
            db.session.add(user)
            db.session.commit()

        sid = 'test-cart-clear-session-123'
        with self.client.session_transaction() as sess:
            sess['_id'] = sid
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        # Add item to cart
        res = self.client.post('/orders/cart/add', json={
            'item_id': item.id,
            'quantity': 2,
            'order_type': 'TAKEAWAY'
        })
        self.assertEqual(res.status_code, 200)
        cart_count = CartItem.query.filter((CartItem.session_id == sid) | (CartItem.user_id == user.id)).count()
        self.assertEqual(cart_count, 1)

        # Clear cart using /orders/cart/clear
        res_clear = self.client.post('/orders/cart/clear')
        self.assertEqual(res_clear.status_code, 200)
        data = res_clear.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['cart_count'], 0)
        self.assertEqual(CartItem.query.filter((CartItem.session_id == sid) | (CartItem.user_id == user.id)).count(), 0)

        # Add item again and checkout to test cart clearance on order placement
        self.client.post('/orders/cart/add', json={
            'item_id': item.id,
            'quantity': 1,
            'order_type': 'TAKEAWAY'
        })
        self.assertEqual(CartItem.query.filter((CartItem.session_id == sid) | (CartItem.user_id == user.id)).count(), 1)

        # Checkout as logged-in user
        res_checkout = self.client.post('/orders/checkout', data={
            'order_type': 'TAKEAWAY',
            'payment_method': 'cash',
            'pickup_time': '20:00'
        }, follow_redirects=True)
        self.assertEqual(res_checkout.status_code, 200)
        # Verify cart is now completely empty
        self.assertEqual(CartItem.query.filter((CartItem.session_id == sid) | (CartItem.user_id == user.id)).count(), 0)

    # ─── 2. TEST FORGOT PASSWORD & EMAIL OTP WORKFLOW ─────────────────────────
    def test_forgot_password_and_otp_reset(self):
        """Verify requesting OTP for a registered email, entering OTP, and resetting password."""
        # Find or create a test customer
        user = User.query.filter_by(email='customer@eatstreet.in').first()
        if not user:
            user = User(name='Test Customer', email='customer@eatstreet.in', role='customer')
            user.set_password('oldpassword123')
            db.session.add(user)
            db.session.commit()
        else:
            user.set_password('oldpassword123')
            db.session.commit()

        # Step 1: Request OTP
        res_fp = self.client.post('/auth/forgot-password', data={
            'email': 'customer@eatstreet.in'
        }, follow_redirects=False)
        self.assertEqual(res_fp.status_code, 302)
        self.assertIn('/auth/reset-password', res_fp.headers['Location'])

        # Verify OTP is stored in session
        with self.client.session_transaction() as sess:
            otp = sess.get('reset_otp')
            reset_email = sess.get('reset_email')
        self.assertIsNotNone(otp)
        self.assertEqual(len(otp), 6)
        self.assertEqual(reset_email, 'customer@eatstreet.in')

        # Step 2: Try invalid OTP
        res_bad_otp = self.client.post('/auth/reset-password', data={
            'otp': '000000',
            'password': 'newpassword123',
            'confirm_password': 'newpassword123'
        })
        self.assertIn(b'Invalid OTP code', res_bad_otp.data)

        # Step 3: Try password mismatch
        res_mismatch = self.client.post('/auth/reset-password', data={
            'otp': otp,
            'password': 'newpassword123',
            'confirm_password': 'differentpassword123'
        })
        self.assertIn(b'Passwords do not match', res_mismatch.data)

        # Step 4: Submit correct OTP and matching new password
        res_success = self.client.post('/auth/reset-password', data={
            'otp': otp,
            'password': 'newpassword123',
            'confirm_password': 'newpassword123'
        }, follow_redirects=False)
        self.assertEqual(res_success.status_code, 302)
        self.assertIn('/auth/login', res_success.headers['Location'])

        # Verify the user can now authenticate with the new password
        updated_user = User.query.filter_by(email='customer@eatstreet.in').first()
        self.assertTrue(updated_user.check_password('newpassword123'))
        self.assertFalse(updated_user.check_password('oldpassword123'))

    # ─── 3. TEST RESEND OTP ───────────────────────────────────────────────────
    def test_resend_otp(self):
        """Verify resending a new OTP updates the session code."""
        # Initiate reset session
        self.client.post('/auth/forgot-password', data={'email': 'customer@eatstreet.in'})
        with self.client.session_transaction() as sess:
            first_otp = sess.get('reset_otp')

        # Resend OTP
        res_resend = self.client.post('/auth/resend-otp', follow_redirects=False)
        self.assertEqual(res_resend.status_code, 302)

        with self.client.session_transaction() as sess:
            second_otp = sess.get('reset_otp')
            resend_count = sess.get('reset_resend_count')

        self.assertIsNotNone(second_otp)
        self.assertEqual(resend_count, 1)

    # ─── 4. TEST PASSWORD VIEW TOGGLE RENDERING ───────────────────────────────
    def test_password_view_toggle_in_templates(self):
        """Verify password show/hide view buttons exist in register and login templates."""
        res_reg = self.client.get('/auth/register')
        self.assertEqual(res_reg.status_code, 200)
        self.assertIn(b'togglePasswordVisibility', res_reg.data)
        self.assertIn(b'regPwdEyeIcon', res_reg.data)
        self.assertIn(b'regConfirmPwdEyeIcon', res_reg.data)

        res_login = self.client.get('/auth/login')
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b'togglePasswordVisibility', res_login.data)
        self.assertIn(b'Forgot Password?', res_login.data)
        self.assertIn(b'/auth/forgot-password', res_login.data)

    # ─── 5. TEST DEMO CHECKOUT AJAX FLOW ──────────────────────────────────────
    def test_demo_checkout_ajax_flow(self):
        """Verify checkout handles AJAX requests and returns structured JSON for the demo payment flow."""
        shop = Shop.query.filter_by(is_active=True).first()
        self.assertIsNotNone(shop)
        item = MenuItem.query.filter_by(shop_id=shop.id, is_available=True).first()
        self.assertIsNotNone(item)

        user = User.query.filter_by(email='customer@eatstreet.in').first()
        if not user:
            user = User(name='Test Customer', email='customer@eatstreet.in', role='customer')
            user.set_password('customer123')
            db.session.add(user)
            db.session.commit()

        sid = 'test-demo-checkout-session'
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
            sess['_id'] = sid

        CartItem.query.filter((CartItem.session_id == sid) | (CartItem.user_id == user.id)).delete()
        db.session.commit()

        # Add item to cart
        self.client.post('/orders/cart/add', json={
            'item_id': item.id,
            'quantity': 2,
            'order_type': 'TAKEAWAY'
        })

        # Submit demo payment checkout as authenticated user
        checkout_res = self.client.post('/orders/checkout', data={
            'order_type': 'TAKEAWAY',
            'pickup_time': '20:15',
            'payment_method': 'upi',
            'special_note': 'Simulated demo payment test'
        }, headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'})

        self.assertEqual(checkout_res.status_code, 200)
        data = checkout_res.get_json()
        self.assertTrue(data.get('success'))
        self.assertTrue(len(data.get('order_numbers', [])) > 0)
        self.assertEqual(data.get('total_amount'), item.price * 2)

        # Cart should be cleared after order
        cart_check = CartItem.query.filter((CartItem.session_id == sid) | (CartItem.user_id == user.id)).all()
        self.assertEqual(len(cart_check), 0)

if __name__ == '__main__':
    unittest.main()
