---
name: Render OAuth cookie stripping + iOS Safari SameSite
description: Cookie-based auth fails on Render/iOS Safari due to proxy header stripping and SameSite=None rejection. Use sessionStorage + Bearer token as primary auth path.
---

# Auth Session Issues on Render / iOS Safari

## Two compounding bugs

**Bug 1 — Render proxy strips Set-Cookie from 3xx responses.**
Never use `302 RedirectResponse` with `Set-Cookie`. Return a `200 HTMLResponse` instead, and do the navigation client-side via `window.location.replace(...)`.

**Bug 2 — iOS Safari rejects SameSite=None cookies.**
`SameSite=None; Secure` is only needed for cross-domain setups (separate API and dashboard subdomains). For same-domain deployments (Render single-service, Replit), use `SameSite=Lax` — it's more compatible and iOS Safari handles it correctly.

**Why:** Both bugs together make cookie-based sessions completely non-functional on Render when accessed from Safari on iOS.

## The robust fix: sessionStorage + Bearer token

Primary auth path bypasses cookies entirely:

1. **Callback page** (200 HTML): embed JWT in a `<script>` tag that stores it in `sessionStorage`, then `window.location.replace(dest)`.
2. **Frontend `apiFetch`**: read `sessionStorage.getItem('np_token')` and include as `Authorization: Bearer <token>` header on every request.
3. **Server `get_current_user`**: check `Authorization: Bearer` header first, then fall back to cookie.
4. **Logout**: return 200 HTML that calls `sessionStorage.removeItem('np_token')` before redirecting.
5. **Keep the cookie** as a fallback for browsers that block JS storage.

**SameSite rule:**
- `DASHBOARD_URL` env var set (cross-domain) + HTTPS → `SameSite=None; Secure`
- Same-domain (no `DASHBOARD_URL`) + HTTPS → `SameSite=Lax; Secure`
- HTTP dev → `SameSite=Lax; Secure=False`
