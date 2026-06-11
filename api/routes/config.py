import httpx
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from bot.core.config_loader import get_config_text, save_config
from api.routes.auth import get_current_user

log = logging.getLogger("api.config")

router = APIRouter()

DISCORD_API = "https://discord.com/api/v10"


async def _get_user_guilds(access_token: str) -> list:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            return []
        return resp.json()


@router.get("/api/guilds")
async def get_guilds(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Guilds are cached in the session at login time (filtered to Manage Guild / Admin)
    session_guilds = user.get("guilds", [])

    bot = getattr(request.app.state, "bot", None)
    if not bot:
        return [
            {
                "id": str(g["id"]),
                "name": g["name"],
                "icon": f"https://cdn.discordapp.com/icons/{g['id']}/{g['icon']}.png" if g.get("icon") else None,
                "member_count": None,
                "bot_present": False,
            }
            for g in session_guilds
        ]

    session_guild_ids = {int(g["id"]) for g in session_guilds}
    bot_guilds = []
    for guild in bot.guilds:
        if guild.id in session_guild_ids:
            bot_guilds.append({
                "id": str(guild.id),
                "name": guild.name,
                "icon": str(guild.icon.url) if guild.icon else None,
                "member_count": guild.member_count,
                "bot_present": True,
            })

    return bot_guilds


@router.get("/api/guilds/{guild_id}/config")
async def get_guild_config(guild_id: int, request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    config_text = await get_config_text(guild_id)
    return {"config": config_text, "guild_id": str(guild_id)}


@router.put("/api/guilds/{guild_id}/config")
async def update_guild_config(guild_id: int, request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = int(user.get("user_id", 0))
    access_token = user.get("access_token")

    # Check if user is in the guild
    user_guilds = await _get_user_guilds(access_token)
    user_guild_ids = {int(g["id"]) for g in user_guilds}
    if guild_id not in user_guild_ids:
        raise HTTPException(status_code=403, detail="You are not in this guild")

    # Check level in guild (require any level > 0)
    bot = getattr(request.app.state, "bot", None)
    if bot:
        guild = bot.get_guild(guild_id)
        if guild:
            member = guild.get_member(user_id)
            if member:
                from bot.core.level_check import get_user_level
                level = await get_user_level(guild_id, user_id, member)
                if level < 1:
                    raise HTTPException(status_code=403, detail="You need at least level 1 to edit config")

    body = await request.json()
    config_text = body.get("config", "")

    try:
        await save_config(guild_id, config_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True}
