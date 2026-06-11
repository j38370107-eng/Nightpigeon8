# Nightpigeon

A Zeppelin-inspired, plugin-based Discord moderation bot with a FastAPI backend, PostgreSQL database, Discord OAuth2, and a Nightpigeon-themed web dashboard (dark night sky + pigeon motif).

## Run & Operate

- `python main.py` — start everything: FastAPI dashboard on port 5000 + Discord bot (if `DISCORD_TOKEN` is set)
- `python run.py` — alias for the above

## Stack

- **Bot**: discord.py 2.x, asyncpg, Python 3.11
- **API**: FastAPI + uvicorn on port 5000
- **DB**: PostgreSQL + asyncpg (raw SQL)
- **Dashboard**: Vanilla HTML/CSS/JS served as static files from `dashboard/`
- **Auth**: Discord OAuth2, JWT sessions (python-jose)
- **Config**: Per-guild YAML stored in PostgreSQL

## Where things live

- `main.py` — entrypoint: starts FastAPI + Discord bot together
- `bot/core/` — bot, database, config_loader, level_check, duration, message_formatter
- `bot/plugins/` — 25 plugin files (one per feature)
- `api/server.py` — FastAPI app factory
- `api/routes/` — auth.py, config.py, cases.py
- `dashboard/` — index.html, guilds.html, config.html, cases.html, docs.html, style.css, app.js
- `pyproject.toml` — Python dependencies managed with uv

## Required Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | **Yes** | PostgreSQL connection string |
| `DISCORD_TOKEN` | **Yes** (for bot) | Bot token from Discord developer portal |
| `CLIENT_ID` | OAuth only | Discord app client ID (for dashboard login) |
| `CLIENT_SECRET` | OAuth only | Discord app client secret |
| `REDIRECT_URI` | OAuth only | OAuth2 redirect URI (e.g. `https://yourapp.replit.app/api/auth/callback`) |
| `API_SECRET_KEY` | Recommended | JWT signing key (defaults to insecure placeholder) |
| `BOT_OWNER_ID` | Optional | Discord user ID for level 1000 access |

## Architecture decisions

- FastAPI serves both the REST API and the dashboard HTML from one process on port 5000
- The bot starts only if `DISCORD_TOKEN` is set; FastAPI always starts
- All plugin configs are read fresh from DB on every command (never cached)
- Level system: 0–100 (users + roles from YAML), 1000 for bot owner
- All moderation actions auto-create cases and post to mod-log channel if configured
- YAML config is validated before saving; bad YAML is rejected with a 400 error

## Plugins (25 total)

moderation, cases, mass_actions, levels, logging_plugin, automod, escalation,
command_aliases, preset_reasons, utility, welcome, notes, roles, starboard,
timezones, reaction_roles, tickets, autoreply, auto_reactions, auto_channel_clean,
slowmode_auto, lockdown, modnick, history, reminders

## User preferences

- Build ALL phases at once — do not split into incremental deliveries
- The pigeon image is `dashboard/pigeon.jpeg` and night sky is `dashboard/nightsky.png`
- Night sky dark theme: `--bg-deep: #0d0f1e`, accent `#7b8cde`
