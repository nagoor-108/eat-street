/* Cart JS — handles cart sidebar and quantity controls */

// Cart sidebar state
let cartSidebarOpen = false;

function openCartSidebar() {
  cartSidebarOpen = true;
  const sidebar = document.getElementById('cartSidebar');
  const overlay = document.getElementById('overlay');
  if (sidebar) sidebar.classList.add('open');
  if (overlay) overlay.classList.add('active');
}

function closeCartSidebar() {
  cartSidebarOpen = false;
  const sidebar = document.getElementById('cartSidebar');
  const overlay = document.getElementById('overlay');
  if (sidebar) sidebar.classList.remove('open');
  if (overlay) overlay.classList.remove('active');
}

// Global add to cart used from shop pages
window.selectedOrderMode = window.selectedOrderMode || 'TAKEAWAY';
