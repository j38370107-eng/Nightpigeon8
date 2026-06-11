// Nightpigeon Dashboard - Shared JS Utilities

const API_BASE = (typeof window !== 'undefined' && window.API_BASE) ? window.API_BASE : '';

// ── Fetch helpers ───────────────────────────────────────────────
async function apiFetch(path, options = {}, redirectOn401 = true) {
  const res = await fetch(API_BASE + path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (res.status === 401) {
    if (redirectOn401) {
      window.location.href = '/api/auth/login';
    }
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json().catch(() => null);
}

// ── Stars ───────────────────────────────────────────────────────
function createStars(count = 80) {
  const container = document.querySelector('.stars');
  if (!container) return;
  for (let i = 0; i < count; i++) {
    const star = document.createElement('div');
    star.className = 'star';
    const size = Math.random() * 2 + 0.5;
    const opacity = Math.random() * 0.5 + 0.2;
    const dur = Math.random() * 4 + 2;
    star.style.cssText = `
      left: ${Math.random() * 100}%;
      top: ${Math.random() * 70}%;
      width: ${size}px;
      height: ${size}px;
      --op: ${opacity};
      --dur: ${dur}s;
      animation-delay: ${Math.random() * 4}s;
    `;
    container.appendChild(star);
  }
}

// ── Current user — never auto-redirects ─────────────────────────
async function loadUser() {
  try {
    const user = await apiFetch('/api/auth/me', {}, false);
    if (!user) {
      _applyNavState(null);
      return null;
    }

    const avatarUrl = user.avatar
      ? `https://cdn.discordapp.com/avatars/${user.user_id}/${user.avatar}.png?size=64`
      : `https://cdn.discordapp.com/embed/avatars/${parseInt(user.user_id || '0') % 6}.png`;

    document.querySelectorAll('.user-badge').forEach(badge => {
      badge.innerHTML = `
        <img src="${avatarUrl}" alt="${user.username}"
             onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'" />
        ${user.username}
      `;
    });

    _applyNavState(user);
    return user;
  } catch {
    _applyNavState(null);
    return null;
  }
}

function _applyNavState(user) {
  const loginBtn  = document.getElementById('login-btn');
  const logoutBtn = document.getElementById('logout-btn');
  const userInfo  = document.getElementById('user-info');

  if (loginBtn)  loginBtn.href  = API_BASE + '/api/auth/login';
  if (logoutBtn) logoutBtn.href = API_BASE + '/api/auth/logout';

  if (user) {
    if (userInfo)  userInfo.style.display  = 'flex';
    if (logoutBtn) logoutBtn.style.display = 'inline-flex';
    if (loginBtn)  loginBtn.style.display  = 'none';
  } else {
    if (userInfo)  userInfo.style.display  = 'none';
    if (logoutBtn) logoutBtn.style.display = 'none';
    if (loginBtn)  loginBtn.style.display  = 'inline-flex';
  }
}

// ── Require login — redirects to Discord OAuth if not authed ────
async function requireAuth() {
  const user = await loadUser();
  if (!user) {
    window.location.href = API_BASE + '/api/auth/login';
    throw new Error('Redirecting to login');
  }
  return user;
}

// ── Flash messages ──────────────────────────────────────────────
function showAlert(message, type = 'info', container = null) {
  const el = document.createElement('div');
  el.className = `alert alert-${type}`;
  const icons = { error: '✕', success: '✓', info: 'ℹ' };
  el.innerHTML = `<span>${icons[type] || '!'}</span> ${message}`;
  const target = container || document.querySelector('.flash-container') || document.querySelector('main');
  if (target) {
    target.insertBefore(el, target.firstChild);
    setTimeout(() => el.remove(), 4000);
  }
}

// ── Action badge ────────────────────────────────────────────────
function actionBadge(action) {
  const labels = {
    ban: '🔨 Ban', forceban: '🔨 Force Ban', unban: '🔓 Unban',
    kick: '👢 Kick', mute: '🔇 Mute', unmute: '🔊 Unmute',
    warn: '⚠️ Warn', note: '📝 Note', addcase: '📋 Case',
  };
  const cls = `badge badge-${action}`;
  return `<span class="${cls}">${labels[action] || action}</span>`;
}

// ── Relative timestamp ──────────────────────────────────────────
function relTime(isoStr) {
  if (!isoStr) return '—';
  const date = new Date(isoStr);
  const now = Date.now();
  const diff = now - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ── Nav active link ─────────────────────────────────────────────
function highlightNav() {
  const path = window.location.pathname;
  document.querySelectorAll('.navbar-links a').forEach(a => {
    const href = a.getAttribute('href');
    if (href && path === href) {
      a.classList.add('active');
    }
  });
}

// ── Init ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  createStars();
  loadUser();
  highlightNav();
});
