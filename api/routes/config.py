import httpx
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from bot.core.config_loader import get_config_text, save_config
from bot.core.level_check import BOT_OWNER_ID
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
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    access_token = user.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="No access token")

    user_guilds = await _get_user_guilds(access_token)
    user_guild_ids = {int(g["id"]) for g in user_guilds}

    bot = request.app.state.bot
    bot_guilds = []
    for guild in bot.guilds:
        if guild.id in user_guild_ids:
            bot_guilds.append({
                "id": str(guild.id),
                "name": guild.name,
                "icon": str(guild.icon.url) if guild.icon else None,
                "member_count": guild.member_count,
            })

    return bot_guilds


@router.get("/api/guilds/{guild_id}/config")
async def get_guild_config(guild_id: int, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    config_text = await get_config_text(guild_id)
    return {"config": config_text, "guild_id": str(guild_id)}


@router.put("/api/guilds/{guild_id}/config")
async def update_guild_config(guild_id: int, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = int(user.get("user_id", 0))
    access_token = user.get("access_token")

    # Check if user is in the guild and has admin level
    user_guilds = await _get_user_guilds(access_token)
    user_guild_ids = {int(g["id"]) for g in user_guilds}
    if guild_id not in user_guild_ids:
        raise HTTPException(status_code=403, detail="You are not in this guild")

    # Check level in guild
    bot = request.app.state.bot
    guild = bot.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    # Bot owner bypass
    if user_id != BOT_OWNER_ID:
        member = guild.get_member(user_id)
        if not member:
            raise HTTPException(status_code=403, detail="You are not in this guild")
        from bot.core.level_check import get_user_level
        level = await get_user_level(guild_id, user_id, member)
        if level < 100:
            raise HTTPException(status_code=403, detail="You need level 100+ to edit config")

    body = await request.json()
    config_text = body.get("config", "")

    try:
        await save_config(guild_id, config_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True}
