from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, bcrypt, CartItem
from urllib.parse import urljoin, urlparse
import time
import random
import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

auth_bp = Blueprint('auth', __name__)

# OTP Expiration (10 minutes)
OTP_EXPIRY_SECONDS = 600

# In-memory brute-force tracking: (ip, email) -> {'attempts': int, 'locked_until': float}
FAILED_LOGINS = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 300  # 5 minutes lockout

def _get_smtp_config():
    """Load latest SMTP config from .env and current_app."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    env_path = os.path.join(base_dir, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
    cfg = current_app.config if current_app else {}
    mail_server = os.environ.get('MAIL_SERVER') or cfg.get('MAIL_SERVER', 'smtp.gmail.com')
    mail_port = int(os.environ.get('MAIL_PORT') or cfg.get('MAIL_PORT', 587))
    mail_username = (os.environ.get('MAIL_USERNAME') or cfg.get('MAIL_USERNAME', '')).strip()
    mail_password = (os.environ.get('MAIL_PASSWORD') or cfg.get('MAIL_PASSWORD', '')).replace(' ', '').strip()
    mail_use_tls = str(os.environ.get('MAIL_USE_TLS', cfg.get('MAIL_USE_TLS', 'true'))).lower() == 'true'
    mail_use_ssl = str(os.environ.get('MAIL_USE_SSL', cfg.get('MAIL_USE_SSL', 'false'))).lower() == 'true'
    sender_addr = os.environ.get('MAIL_DEFAULT_SENDER') or cfg.get('MAIL_DEFAULT_SENDER') or f'Eat Street Kakinada <{mail_username}>'
    return {
        'server': mail_server,
        'port': mail_port,
        'username': mail_username,
        'password': mail_password,
        'use_tls': mail_use_tls,
        'use_ssl': mail_use_ssl,
        'sender': sender_addr,
        'configured': bool(mail_username and mail_password)
    }

def _send_otp_email(to_email, otp_code):
    """Sends a verification OTP via SMTP if configured; otherwise logs it in development mode.
    Returns: (is_smtp_sent: bool, status_msg: str)
    """
    conf = _get_smtp_config()
    mail_server = conf['server']
    mail_port = conf['port']
    mail_username = conf['username']
    mail_password = conf['password']
    mail_use_tls = conf['use_tls']
    mail_use_ssl = conf['use_ssl']
    sender_addr = conf['sender']

    if mail_server and mail_username and mail_password:
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f'Eat Street - Your Password Reset OTP ({otp_code})'
            msg['From'] = f'Eat Street Kakinada <{sender_addr}>'
            msg['To'] = to_email
            msg['Reply-To'] = sender_addr
            msg['Auto-Submitted'] = 'auto-generated'
            msg['X-Auto-Response-Suppress'] = 'All'

            text_body = f"""Hello,

Your 6-digit One-Time Password (OTP) for resetting your Eat Street account password is:

    {otp_code}

This OTP is valid for 10 minutes. If you did not request a password reset, please ignore this email.

Warm regards,
Eat Street Kakinada Team
"""
            html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background-color:#121212;color:#ffffff;padding:24px;margin:0;">
  <div style="max-width:480px;margin:0 auto;background:#1e1e1e;border-radius:16px;border:1px solid rgba(255,255,255,0.1);padding:32px;text-align:center;">
    <div style="font-size:32px;margin-bottom:8px;">🍴</div>
    <h2 style="color:#ff3b00;margin:0 0 8px;font-size:22px;">Eat Street Kakinada</h2>
    <p style="color:#aaa;font-size:14px;margin:0 0 24px;">Password Reset Verification Code</p>
    
    <div style="background:rgba(255,59,0,0.1);border:1px dashed #ff3b00;border-radius:12px;padding:16px;margin-bottom:24px;">
      <span style="font-family:monospace;font-size:32px;font-weight:bold;letter-spacing:6px;color:#ff3b00;">{otp_code}</span>
    </div>
    
    <p style="color:#bbb;font-size:13px;line-height:1.5;margin-bottom:20px;">
      This OTP is valid for <strong>10 minutes</strong>. Please enter this code on the password reset page to choose a new password.
    </p>
    
    <p style="color:#666;font-size:11px;margin:0;border-top:1px solid rgba(255,255,255,0.08);padding-top:16px;">
      If you did not request this password reset, no action is needed. Your account remains secure.
    </p>
  </div>
</body>
</html>
"""
            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            if mail_use_ssl or mail_port == 465:
                with smtplib.SMTP_SSL(mail_server, mail_port, timeout=15) as server:
                    server.login(mail_username, mail_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(mail_server, mail_port, timeout=15) as server:
                    if mail_use_tls:
                        server.starttls()
                    server.login(mail_username, mail_password)
                    server.send_message(msg)
            print(f"[SMTP Success] OTP email sent successfully to {to_email}")
            return True, "Email sent via SMTP."
        except Exception as e:
            print(f"[SMTP Error] Failed to send email to {to_email}: {e}")
            return False, f"SMTP Error: {e}"
    else:
        # Development / local mode: log to console without raw non-ascii characters
        print("\n==========================================")
        print(f"[DEV EMAIL OTP DISPATCH] To: {to_email}")
        print(f"OTP Code: {otp_code} (Valid for 10 minutes)")
        print("==========================================\n")
        return False, "SMTP credentials not configured in .env file (MAIL_USERNAME / MAIL_PASSWORD)."

def _get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'

def _is_locked_out(ip, email):
    now = time.time()
    for key in [(ip, email), (ip, 'global')]:
        record = FAILED_LOGINS.get(key)
        if record and record.get('locked_until', 0) > now:
            remaining = int(record['locked_until'] - now)
            return True, remaining
    return False, 0

def _record_failed_attempt(ip, email):
    now = time.time()
    key = (ip, email)
    record = FAILED_LOGINS.setdefault(key, {'attempts': 0, 'locked_until': 0})
    record['attempts'] += 1
    if record['attempts'] >= MAX_FAILED_ATTEMPTS:
        record['locked_until'] = now + LOCKOUT_DURATION_SECONDS
        record['attempts'] = 0
        return True, LOCKOUT_DURATION_SECONDS, 0
    remaining_attempts = MAX_FAILED_ATTEMPTS - record['attempts']
    return False, 0, remaining_attempts

def _reset_failed_attempts(ip, email):
    FAILED_LOGINS.pop((ip, email), None)
    FAILED_LOGINS.pop((ip, 'global'), None)

def _generate_security_challenge():
    num1 = random.randint(2, 9)
    num2 = random.randint(1, 9)
    session['sec_captcha_q'] = f"{num1} + {num2}"
    session['sec_captcha_a'] = str(num1 + num2)
    return session['sec_captcha_q']

def _safe_next_url(target):
    """Only redirect to a local path after login."""
    if not target or not target.startswith('/') or target.startswith('//') or '\\' in target:
        return None
    host_url = urlparse(request.host_url)
    candidate = urlparse(urljoin(request.host_url, target))
    return target if candidate.scheme in ('http', 'https') and candidate.netloc == host_url.netloc else None

@auth_bp.route('/refresh-captcha')
def refresh_captcha():
    q = _generate_security_challenge()
    return jsonify({'success': True, 'question': q})

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home.index'))

    ip = _get_client_ip()

    if request.method == 'POST':
        # 1. Honeypot check (anti-bot trap)
        if request.form.get('company_code_hp'):
            flash('Security verification failed.', 'danger')
            return redirect(url_for('auth.login'))

        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        captcha_ans = request.form.get('security_captcha', '').strip()
        remember = request.form.get('remember') == 'on'

        # 2. Brute-force Lockout Check
        is_locked, remaining_sec = _is_locked_out(ip, email)
        if is_locked:
            mins = remaining_sec // 60
            secs = remaining_sec % 60
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            flash(f'🔒 Security Lockout Active: Too many failed attempts. Please wait {time_str} before retrying.', 'danger')
            _generate_security_challenge()
            return render_template('auth/login.html', captcha_question=session.get('sec_captcha_q'), is_locked=True, remaining_sec=remaining_sec)

        # 3. Security Challenge Verification (if active in session)
        expected_ans = session.get('sec_captcha_a')
        if expected_ans and captcha_ans != expected_ans:
            is_locked, lock_dur, rem = _record_failed_attempt(ip, email)
            _generate_security_challenge()
            if is_locked:
                flash('🔒 Incorrect security challenge. Account locked for 5 minutes due to multiple failures.', 'danger')
            else:
                flash(f'⚠️ Incorrect security verification answer. {rem} attempt(s) remaining.', 'warning')
            return render_template('auth/login.html', captcha_question=session.get('sec_captcha_q'))

        # 4. User Credential Verification
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash('This account is deactivated. Please contact support.', 'danger')
                _generate_security_challenge()
                return render_template('auth/login.html', captcha_question=session.get('sec_captcha_q'))

            # Clear failed attempts upon successful authentication
            _reset_failed_attempts(ip, email)
            session.pop('sec_captcha_a', None)
            session.pop('sec_captcha_q', None)

            login_user(user, remember=remember)
            sid = session.get('_id')
            if sid:
                CartItem.query.filter_by(session_id=sid).update({'user_id': user.id})
                db.session.commit()

            next_page = _safe_next_url(request.args.get('next') or request.form.get('next'))
            flash(f'Welcome back, {user.name}! 🍴', 'success')
            if next_page:
                return redirect(next_page)
            if user.role in ('vendor', 'admin'):
                return redirect(url_for('vendor.dashboard'))
            return redirect(url_for('home.index'))
        else:
            # Timing attack mitigation
            if not user:
                bcrypt.generate_password_hash("dummy_pwd_timing_check")

            is_locked, lock_dur, rem = _record_failed_attempt(ip, email)
            _generate_security_challenge()
            if is_locked:
                flash('🔒 Security Lockout: Multiple invalid login attempts detected. Access blocked for 5 minutes.', 'danger')
            else:
                flash(f'Invalid email or password. {rem} attempt(s) remaining before security lockout.', 'danger')
            return render_template('auth/login.html', captcha_question=session.get('sec_captcha_q'))

    # GET request - generate security challenge
    challenge_q = _generate_security_challenge()
    is_locked, remaining_sec = _is_locked_out(ip, '')
    return render_template('auth/login.html', captcha_question=challenge_q, is_locked=is_locked, remaining_sec=remaining_sec)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home.index'))
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        phone    = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')
        if not all([name, email, password]):
            flash('Please fill all required fields.', 'warning')
            return redirect(url_for('auth.register', next=request.args.get('next')))
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.register', next=request.args.get('next')))
        if len(password) < 8:
            flash('Password must contain at least 8 characters.', 'warning')
            return redirect(url_for('auth.register', next=request.args.get('next')))
        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please login.', 'warning')
            return redirect(url_for('auth.login', next=request.args.get('next')))
        user = User(name=name, email=email, phone=phone, role='customer')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)

        sid = session.get('_id')
        if sid:
            CartItem.query.filter_by(session_id=sid).update({'user_id': user.id})
            db.session.commit()

        next_page = _safe_next_url(request.args.get('next') or request.form.get('next'))
        flash(f'Account created! Welcome to Eat Street, {name}! 🎉', 'success')
        return redirect(next_page or url_for('home.index'))
    return render_template('auth/register.html')

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    # Do not let the next browser user inherit a previous guest-order session.
    session.pop('_id', None)
    session.pop('dine_in_table', None)
    session.pop('dine_in_shop', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('home.index'))

@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html')


def _is_smtp_configured():
    conf = _get_smtp_config()
    return conf['configured']


# ─── FORGOT PASSWORD (EMAIL OTP) ──────────────────────────────────────────────
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('home.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Please enter your registered email address.', 'warning')
            return redirect(url_for('auth.forgot_password'))

        user = User.query.filter_by(email=email).first()
        if not user:
            user_name = email.split('@')[0].capitalize()
            user = User(name=user_name, email=email, role='customer')
            user.set_password(secrets.token_urlsafe(16))
            db.session.add(user)
            db.session.commit()

        otp = f"{secrets.randbelow(900000) + 100000}"
        session['reset_email'] = email
        session['reset_otp'] = otp
        session['reset_otp_time'] = time.time()
        session['reset_resend_count'] = 0

        is_smtp, msg = _send_otp_email(email, otp)
        if is_smtp:
            flash(f'A 6-digit verification OTP has been sent to your email ({email}). Please check your Inbox / Spam folder.', 'success')
        else:
            flash(f'Preview Mode Active: OTP generated below for testing. Configure Gmail in .env to receive live emails.', 'info')
        return redirect(url_for('auth.reset_password'))

    return render_template('auth/forgot_password.html')


# ─── RESET PASSWORD (OTP VERIFICATION & UPDATE) ──────────────────────────────
@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if current_user.is_authenticated:
        return redirect(url_for('home.index'))

    email = session.get('reset_email')
    stored_otp = session.get('reset_otp')
    otp_time = session.get('reset_otp_time', 0)
    dev_otp = stored_otp if not _is_smtp_configured() else None

    if not email or not stored_otp:
        flash('Please request a password reset OTP first.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    now = time.time()
    if now - otp_time > OTP_EXPIRY_SECONDS:
        session.pop('reset_otp', None)
        session.pop('reset_email', None)
        session.pop('reset_otp_time', None)
        flash('Your verification OTP has expired. Please request a new one.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        submitted_otp = request.form.get('otp', '').strip()
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not submitted_otp or not new_password or not confirm_password:
            flash('Please complete all required fields.', 'warning')
            return render_template('auth/reset_password.html', email_hint=email, dev_otp=dev_otp)

        if submitted_otp != stored_otp:
            flash('Invalid OTP code. Please check and enter the correct 6-digit code.', 'danger')
            return render_template('auth/reset_password.html', email_hint=email, dev_otp=dev_otp)

        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html', email_hint=email, dev_otp=dev_otp)

        if len(new_password) < 8:
            flash('Password must contain at least 8 characters.', 'warning')
            return render_template('auth/reset_password.html', email_hint=email, dev_otp=dev_otp)

        user = User.query.filter_by(email=email).first()
        if user:
            user.set_password(new_password)
            db.session.commit()

            # Clear reset session data
            session.pop('reset_otp', None)
            session.pop('reset_email', None)
            session.pop('reset_otp_time', None)
            session.pop('reset_resend_count', None)

            flash('🎉 Password reset successfully! You can now log in with your new password.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('User account not found. Please try again.', 'danger')
            return redirect(url_for('auth.forgot_password'))

    return render_template('auth/reset_password.html', email_hint=email, dev_otp=dev_otp)


# ─── RESEND OTP ───────────────────────────────────────────────────────────────
@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    email = session.get('reset_email')
    if not email:
        flash('Please enter your email to request an OTP.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    resend_count = session.get('reset_resend_count', 0)
    if resend_count >= 5:
        flash('Maximum resend attempts reached. Please wait a few minutes.', 'danger')
        return redirect(url_for('auth.reset_password'))

    new_otp = f"{secrets.randbelow(900000) + 100000}"
    session['reset_otp'] = new_otp
    session['reset_otp_time'] = time.time()
    session['reset_resend_count'] = resend_count + 1

    is_smtp, msg = _send_otp_email(email, new_otp)
    if is_smtp:
        flash(f'A fresh 6-digit OTP has been sent to your email ({email}). Please check your inbox.', 'success')
    else:
        flash(f'Preview Mode: Fresh OTP generated below. Configure Gmail in .env to receive live emails.', 'info')
    return redirect(url_for('auth.reset_password'))

