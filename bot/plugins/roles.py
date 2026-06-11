import discord
from discord.ext import commands
from datetime import datetime, timezone
import logging
from bot.core.config_loader import get_config, get_plugin_config
from bot.core.level_check import get_user_level
from bot.core.duration import parse_duration, format_duration
from bot.core.database import get_pool
from bot.core.message_formatter import send_message

log = logging.getLogger("bot.roles")


async def _check_level(ctx, level: int) -> bool:
    user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
    if user_level < level:
        config = await get_config(ctx.guild.id)
        await send_message(ctx, config, "moderation", "no_permission")
        return False
    return True


class RolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_level(self, config, cmd, default=50):
        plugin_cfg = get_plugin_config(config, "roles")
        return ((plugin_cfg.get("config", {}) or {}).get("levels", {}) or {}).get(cmd, default)

    @commands.command(name="addrole")
    @commands.guild_only()
    async def addrole(self, ctx, user: discord.Member, role: discord.Role, *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_level(config, "addrole", 50)):
            return
        try:
            await user.add_roles(role, reason=f"[{ctx.author}] {reason}")
            await send_message(ctx, config, "moderation", "addrole_reply",
                               user=str(user), role=role.name, reason=reason)
        except discord.Forbidden:
            await ctx.send("I don't have permission to add that role.")

    @commands.command(name="removerole")
    @commands.guild_only()
    async def removerole(self, ctx, user: discord.Member, role: discord.Role, *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_level(config, "removerole", 50)):
            return
        try:
            await user.remove_roles(role, reason=f"[{ctx.author}] {reason}")
            await send_message(ctx, config, "moderation", "removerole_reply",
                               user=str(user), role=role.name, reason=reason)
        except discord.Forbidden:
            await ctx.send("I don't have permission to remove that role.")

    @commands.command(name="temprole")
    @commands.guild_only()
    async def temprole(self, ctx, user: discord.Member, role: discord.Role, duration: str, *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_level(config, "temprole", 50)):
            return
        try:
            td = parse_duration(duration)
        except ValueError as e:
            return await ctx.send(str(e))

        expires_at = datetime.now(timezone.utc) + td if td else None
        try:
            await user.add_roles(role, reason=f"[TempRole] {ctx.author}: {reason}")
        except discord.Forbidden:
            return await ctx.send("I don't have permission to add that role.")

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO timed_roles (guild_id,user_id,role_id,expires_at)
                   VALUES ($1,$2,$3,$4) ON CONFLICT (guild_id,user_id,role_id) DO UPDATE SET expires_at=$4""",
                ctx.guild.id, user.id, role.id, expires_at
            )

        await send_message(ctx, config, "moderation", "temprole_reply",
                           user=str(user), role=role.name, duration=format_duration(td))


async def setup(bot):
    await bot.add_cog(RolesCog(bot))
