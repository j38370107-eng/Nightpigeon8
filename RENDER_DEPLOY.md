# Nightpigeon — Render Deployment Guide

## Overview: 2 Services

| Service Name             | Start Command              | Purpose                        |
|--------------------------|----------------------------|--------------------------------|
| nightpigeon-bot-api      | python main_bot_api.py     | Discord bot + all /api/ routes |
| nightpigeon-dashboard    | python dashboard_server.py | Website & dashboard UI         |

---

## Step 1 — Push to GitHub

Create a repo at https://github.com/new then run in the Replit shell:

```
git remote add origin https://github.com/YOURUSERNAME/nightpigeon.git
git push -u origin main
```

---

## Step 2 — Create Service 1: Bot + API

1. Go to https://render.com → New → Web Service
2. Connect your GitHub repo
3. Fill in:
   - Name:           nightpigeon-bot-api
   - Build Command:  pip install -r requirements.txt
   - Start Command:  python main_bot_api.py

4. Add these Environment Variables:

```
DATABASE_URL      = (your Aiven PostgreSQL connection string)
DISCORD_TOKEN     = (your Discord bot token)
CLIENT_ID         = (your Discord app client ID)
CLIENT_SECRET     = (your Discord app client secret)
API_SECRET_KEY    = (any long random string, e.g. a strong password)
REDIRECT_URI      = https://nightpigeon-bot-api.onrender.com/api/auth/callback
ALLOWED_ORIGINS   = https://nightpigeon-dashboard.onrender.com
DASHBOARD_URL     = https://nightpigeon-dashboard.onrender.com
```

5. Click Deploy and wait for it to go live.
   Note the URL (e.g. https://nightpigeon-bot-api.onrender.com)

---

## Step 3 — Create Service 2: Dashboard

1. New → Web Service (same repo)
2. Fill in:
   - Name:           nightpigeon-dashboard
   - Build Command:  pip install fastapi uvicorn
   - Start Command:  python dashboard_server.py

3. Add these Environment Variables:

```
API_URL      = https://nightpigeon-bot-api.onrender.com
DASHBOARD_URL = https://nightpigeon-dashboard.onrender.com
```

(Use the exact URL from Step 2)

4. Click Deploy.

---

## Step 4 — Add Discord OAuth Redirect

1. Go to https://discord.com/developers/applications
2. Select your application
3. Click OAuth2 in the left sidebar
4. Under Redirects, click Add Redirect and paste:

```
https://nightpigeon-bot-api.onrender.com/api/auth/callback
```

5. Click Save Changes

---

## Step 5 — Aiven Database Connection String

From your Aiven console, copy the PostgreSQL connection string. It looks like:

```
postgresql://avnadmin:PASSWORD@HOST.aivencloud.com:PORT/defaultdb?sslmode=require
```

Paste this as DATABASE_URL in Service 1 (nightpigeon-bot-api).

IMPORTANT: Make sure the URL ends with ?sslmode=require — Aiven requires SSL.

---

## Step 6 — UptimeRobot (Keep the bot always online)

Both services have a /ping endpoint that returns {"status":"ok"}.
Use UptimeRobot to ping them every 5 minutes so Render never puts them to sleep.

1. Go to https://uptimerobot.com and create a free account
2. Click New Monitor for the Bot + API service:
   - Monitor Type:   HTTP(s)
   - Friendly Name:  Nightpigeon Bot
   - URL:            https://nightpigeon-bot-api.onrender.com/ping
   - Interval:       Every 5 minutes
   - Click Save
3. Click New Monitor again for the Dashboard:
   - Monitor Type:   HTTP(s)
   - Friendly Name:  Nightpigeon Dashboard
   - URL:            https://nightpigeon-dashboard.onrender.com/ping
   - Interval:       Every 5 minutes
   - Click Save

That's it — UptimeRobot will ping both services every 5 minutes, keeping them awake 24/7.

---

## Final URLs

- Dashboard:   https://nightpigeon-dashboard.onrender.com
- API / Bot:   https://nightpigeon-bot-api.onrender.com
- Bot ping:    https://nightpigeon-bot-api.onrender.com/ping
- Dash ping:   https://nightpigeon-dashboard.onrender.com/ping

---

## Notes

- After any code changes, push to GitHub — Render will auto-redeploy both services.
- The REDIRECT_URI in your Discord app settings and the REDIRECT_URI env var must match exactly.
- If the bot disconnects, check the nightpigeon-bot-api logs in the Render dashboard.
