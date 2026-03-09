/**
 * Techmatic Admin — Shared JS
 * All admin pages load this file.
 */

const API = window.TECHMATIC_ADMIN_API || 'http://localhost:8000';

/* ── Token storage ── */
function getToken() { return localStorage.getItem('ts_admin_token'); }
function setToken(t) { localStorage.setItem('ts_admin_token', t); }
function clearToken() { localStorage.removeItem('ts_admin_token'); localStorage.removeItem('ts_admin_id'); }
function getAdminId() { return localStorage.getItem('ts_admin_id'); }
function setAdminId(id) { localStorage.setItem('ts_admin_id', id); }

/* ── Auth guard — call on every protected page ── */
function requireAuth(redirectTo) {
  if (!getToken()) {
    window.location.href = redirectTo || 'login.html';
  }
}

/* ── API helper ── */
async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (token) headers['X-Admin-Token'] = token;

  const resp = await fetch(API + path, { ...options, headers });

  if (resp.status === 401) {
    clearToken();
    window.location.href = 'login.html';
    throw new Error('Unauthorized');
  }
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

/* ── Login ── */
async function adminLogin(adminId, password) {
  const data = await apiFetch('/admin/login', {
    method: 'POST',
    body: JSON.stringify({ admin_id: adminId, password }),
  });
  setToken(data.token);
  setAdminId(data.admin_id);
  return data;
}

async function adminLogout() {
  try { await apiFetch('/admin/logout', { method: 'POST' }); } catch {}
  clearToken();
  window.location.href = 'login.html';
}

/* ── Notifications ── */
let _notifTimer = null;
function showNotif(msg, type = 'success') {
  let el = document.getElementById('ts-notif');
  if (!el) {
    el = document.createElement('div');
    el.id = 'ts-notif';
    el.style.cssText = `
      position:fixed;top:16px;right:16px;z-index:9999;
      padding:12px 20px;border-radius:10px;font-size:13.5px;font-weight:500;
      display:flex;align-items:center;gap:10px;
      box-shadow:0 8px 30px rgba(0,0,0,0.18);font-family:'Segoe UI',sans-serif;
      max-width:340px;transition:all 0.3s ease;
    `;
    document.body.appendChild(el);
  }
  const cfg = {
    success: { bg:'#38a169', icon:'fa-check-circle' },
    error: { bg:'#e53e3e', icon:'fa-times-circle' },
    info: { bg:'#3182ce', icon:'fa-info-circle' },
    warning: { bg:'#d69e2e', icon:'fa-exclamation-triangle' },
  };
  const c = cfg[type] || cfg.info;
  el.style.background = c.bg;
  el.style.color = '#fff';
  el.innerHTML = `<i class="fas ${c.icon}"></i><span>${msg}</span>`;
  el.style.opacity = '1'; el.style.transform = 'translateX(0)';
  clearTimeout(_notifTimer);
  _notifTimer = setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(20px)'; }, 3500);
}

/* ── Format helpers ── */
function fmtTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-IN', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' });
  } catch { return iso; }
}
function fmtTimeAgo(iso) {
  if (!iso) return '—';
  try {
    const s = Math.floor((Date.now() - new Date(iso)) / 1000);
    if (s < 60) return s + 's ago';
    if (s < 3600) return Math.floor(s/60) + 'm ago';
    if (s < 86400) return Math.floor(s/3600) + 'h ago';
    return Math.floor(s/86400) + 'd ago';
  } catch { return iso; }
}
function esc(str) {
  const el = document.createElement('div');
  el.textContent = str || '';
  return el.innerHTML;
}
function statusBadge(status) {
  const map = {
    new: 'badge-new', contacted: 'badge-contacted',
    qualified: 'badge-qualified', closed: 'badge-closed',
  };
  return `<span class="badge ${map[status]||'badge-new'}">${status||'new'}</span>`;
}
function kbBadge(status) {
  const map = { scraped:'badge-scraped', pending:'badge-pending', error:'badge-error' };
  return `<span class="badge ${map[status]||'badge-pending'}">${status||'pending'}</span>`;
}

/* ── Sidebar active state ── */
function setSidebarActive() {
  const current = window.location.pathname.split('/').pop();
  document.querySelectorAll('.nav-item').forEach(el => {
    const href = el.getAttribute('href') || '';
    el.classList.toggle('active', href === current || href.endsWith(current));
  });
}

/* ── Logout button ── */
document.addEventListener('DOMContentLoaded', () => {
  setSidebarActive();
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) logoutBtn.addEventListener('click', () => adminLogout());
  const adminIdDisplay = document.getElementById('adminIdDisplay');
  if (adminIdDisplay) adminIdDisplay.textContent = getAdminId() || 'Admin';
});
