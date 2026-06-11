import os
import discord
import logging
from functools import wraps
from bot.core.config_loader import get_config
from bot.core.message_formatter import send_message

log = logging.getLogger("bot.levels")

BOT_OWNER_ID = int(os.environ.get("BOT_OWNER_ID", "0"))


async def get_user_level(guild_id: int, user_id: int, member: discord.Member | None) -> int:
    """Returns the highest permission level for a user in a guild."""
    if user_id == BOT_OWNER_ID and BOT_OWNER_ID != 0:
        return 1000

    config = await get_config(guild_id)
    levels_config = config.get("levels", {})

    if not levels_config:
        return 0

    highest = 0

    # Check user-level overrides
    users = levels_config.get("users", {}) or {}
    user_key = str(user_id)
    if user_key in users:
        val = users[user_key]
        if isinstance(val, int):
            highest = max(highest, min(val, 100) if val < 1000 else 100)

    # Check role-level overrides
    if member:
        roles_config = levels_config.get("roles", {}) or {}
        for role in member.roles:
            role_key = str(role.id)
            if role_key in roles_config:
                val = roles_config[role_key]
                if isinstance(val, int):
                    highest = max(highest, min(val, 100))

    return highest


def require_level(level: int):
    """Decorator for bot commands that enforces a minimum permission level."""
    def decorator(func):
        @wraps(func)
        async def wrapper(cog, ctx, *args, **kwargs):
            user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
            if user_level < level:
                config = await get_config(ctx.guild.id)
                await send_message(ctx, config, "moderation", "no_permission")
                return
            return await func(cog, ctx, *args, **kwargs)
        return wrapper
    return decorator


def require_level_value(level: int):
    """Returns a check function for use with commands.check()."""
    async def predicate(ctx):
        user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
        return user_level >= level
    return predicate
