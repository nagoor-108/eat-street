/* ═══════════════════════════════════════════════════════════════════════
   KAKINADA EAT STREET — Main JavaScript
   ═══════════════════════════════════════════════════════════════════════ */

// ─── TOAST NOTIFICATIONS ─────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  toast.innerHTML = `${icons[type] || 'ℹ️'} ${message}`;
  container.appendChild(toast);

  // Auto-dismiss
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(-50%) translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Auto-dismiss flash messages
document.addEventListener('DOMContentLoaded', () => {
  const flash = document.getElementById('flashMsg');
  if (flash) {
    setTimeout(() => {
      flash.style.opacity = '0';
      flash.style.transition = 'opacity 0.5s';
      setTimeout(() => flash.remove(), 500);
    }, 4000);
  }
});

// ─── CART BADGE ───────────────────────────────────────────────────────────
function updateCartBadge(count) {
  let badge = document.querySelector('.cart-badge');
  const cartBtn = document.querySelector('.cart-btn');
  if (!cartBtn) return;
  if (count > 0) {
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'cart-badge';
      cartBtn.appendChild(badge);
    }
    badge.textContent = count;
  } else if (badge) {
    badge.remove();
  }
}

// ─── MOBILE MENU ──────────────────────────────────────────────────────────
function toggleMobileMenu() {
  const links = document.getElementById('navLinks');
  const ham   = document.getElementById('hamburger');
  if (links) {
    links.classList.toggle('mobile-open');
    ham.classList.toggle('open');
  }
}

// Close mobile menu on outside click
document.addEventListener('click', (e) => {
  const links = document.getElementById('navLinks');
  const ham   = document.getElementById('hamburger');
  if (links && links.classList.contains('mobile-open')) {
    if (!links.contains(e.target) && !ham.contains(e.target)) {
      links.classList.remove('mobile-open');
      ham.classList.remove('open');
    }
  }
});

// ─── DROPDOWN ─────────────────────────────────────────────────────────────
function toggleDropdown(btn) {
  const menu = document.getElementById('userDropdown');
  if (menu) {
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
  }
}

document.addEventListener('click', (e) => {
  const dd = document.getElementById('userDropdown');
  if (dd && !e.target.closest('.dropdown')) {
    dd.style.display = 'none';
  }
});

// ─── OVERLAY ──────────────────────────────────────────────────────────────
function closeOverlay() {
  document.getElementById('overlay').classList.remove('active');
  document.querySelectorAll('.modal').forEach(m => m.classList.remove('open'));
  const cart = document.getElementById('cartSidebar');
  if (cart) cart.classList.remove('open');
}

function openCartSidebar() {
  const cart = document.getElementById('cartSidebar');
  if (cart) {
    cart.classList.add('open');
    document.getElementById('overlay').classList.add('active');
  }
}

// ─── NAVBAR SCROLL EFFECT ─────────────────────────────────────────────────
window.addEventListener('scroll', () => {
  const nav = document.getElementById('navbar');
  if (nav) {
    if (window.scrollY > 50) nav.classList.add('scrolled');
    else nav.classList.remove('scrolled');
  }
});

// ─── SMOOTH SCROLL ────────────────────────────────────────────────────────
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', (e) => {
    const target = document.querySelector(anchor.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// ─── INTERSECTION OBSERVER (fade-in on scroll) ────────────────────────────
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.style.opacity = '1';
      entry.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.1 });

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.card, .food-card, .shop-card, .stat-card').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
    observer.observe(el);
  });
});

// ─── GLOBAL addToCart ─────────────────────────────────────────────────────
function addToCart(itemId, btn, shopId, qty = 1) {
  const orderType = window.selectedOrderMode || 'TAKEAWAY';
  fetch('/orders/cart/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_id: itemId, quantity: qty, order_type: orderType })
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) {
      updateCartBadge(data.cart_count);
      showToast(data.message, 'success');
      // Animate button
      if (btn) {
        btn.innerHTML = '<i class="ri-check-line"></i>';
        btn.style.background = 'var(--success)';
        setTimeout(() => {
          btn.innerHTML = '<i class="ri-add-line"></i>';
          btn.style.background = '';
        }, 1500);
      }
    } else {
      showToast(data.message || 'Error adding to cart', 'error');
    }
  })
  .catch(() => showToast('Network error. Please try again.', 'error'));
}

// ─── KEYBOARD SHORTCUTS ───────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  // Escape closes modals/overlays
  if (e.key === 'Escape') closeOverlay();
  // '/' to focus search
  if (e.key === '/' && !e.target.matches('input, textarea')) {
    e.preventDefault();
    const searchInput = document.getElementById('heroSearch') ||
                        document.getElementById('shopSearch') ||
                        document.querySelector('.search-bar input');
    if (searchInput) searchInput.focus();
  }
});
