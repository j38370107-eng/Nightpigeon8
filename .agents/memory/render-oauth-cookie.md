---
name: Render OAuth cookie stripping
description: Render's reverse proxy strips Set-Cookie headers from 3xx redirect responses, breaking OAuth session cookies.
---

# Render OAuth Cookie Stripping

**The rule:** Never use a `302 RedirectResponse` with `Set-Cookie` on Render (or similar reverse-proxy hosts). The proxy strips `Set-Cookie` from 3xx responses before forwarding to the browser.

**Why:** Render's ingress proxy does not forward `Set-Cookie` headers attached to redirect responses. The browser follows the redirect but never receives the cookie, so the session is never established — causing an infinite OAuth loop.

**How to apply:** In OAuth callbacks (and anywhere else a cookie must be set alongside a redirect), return a `200 HTMLResponse` containing a `<meta http-equiv="refresh">` tag and a `<script>window.location.replace(...)</script>` instead of a `RedirectResponse`. Set the cookie on the 200 response. The browser executes the JS/meta redirect client-side AFTER storing the cookie.

```python
html = (
    "<!doctype html><html><head>"
    f'<meta http-equiv="refresh" content="0;url={dest}">'
    "</head><body>"
    f"<script>window.location.replace({repr(dest)});</script>"
    "</body></html>"
)
resp = HTMLResponse(content=html, status_code=200)
resp.set_cookie("session", token, ...)
return resp
```
