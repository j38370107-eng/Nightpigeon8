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

3. Add this Environment Variable:

```
API_URL = https://nightpigeon-bot-api.onrender.com
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

## Final URLs

- Dashboard:  https://nightpigeon-dashboard.onrender.com
- API / Bot:  https://nightpigeon-bot-api.onrender.com
- Health check: https://nightpigeon-bot-api.onrender.com/api/healthz

---

## Notes

- Free Render services sleep after 15 min of inactivity and take ~30 sec to wake up.
  Upgrade to Starter ($7/mo) if you need the bot always online.
- After any code changes, push to GitHub and Render will auto-redeploy.
- The REDIRECT_URI in your Discord app settings and the REDIRECT_URI env var must match exactly.
