import discord
from discord.ext import commands
import json
import logging
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled
from bot.core.level_check import get_user_level
from bot.core.database import get_pool
from bot.core.message_formatter import send_message

log = logging.getLogger("bot.lockdown")


async def _check_level(ctx, level: int) -> bool:
    user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
    if user_level < level:
        config = await get_config(ctx.guild.id)
        await send_message(ctx, config, "moderation", "no_permission")
        return False
    return True


class LockdownCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_level(self, config, cmd, default=60):
        plugin_cfg = get_plugin_config(config, "lockdown")
        return ((plugin_cfg.get("config", {}) or {}).get("levels", {}) or {}).get(cmd, default)

    async def _lock_channel(self, channel: discord.TextChannel, reason: str, config: dict):
        everyone = channel.guild.default_role
        overwrite = channel.overwrites_for(everyone)
        original = {
            "send_messages": overwrite.send_messages,
            "add_reactions": overwrite.add_reactions,
        }
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO lockdown_state (guild_id,channel_id,original_perms)
                   VALUES ($1,$2,$3) ON CONFLICT (guild_id,channel_id) DO UPDATE SET original_perms=$3""",
                channel.guild.id, channel.id, json.dumps(original)
            )
        overwrite.send_messages = False
        await channel.set_permissions(everyone, overwrite=overwrite, reason=reason)

        plugin_cfg = get_plugin_config(config, "lockdown")
        locked_msg = (plugin_cfg.get("config", {}) or {}).get("messages", {}).get("locked", "🔒 This channel has been locked. Reason: {reason}")
        try:
            await channel.send(locked_msg.format(reason=reason))
        except Exception:
            pass

    async def _unlock_channel(self, channel: discord.TextChannel, config: dict):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT original_perms FROM lockdown_state WHERE guild_id=$1 AND channel_id=$2",
                channel.guild.id, channel.id
            )

        everyone = channel.guild.default_role
        overwrite = channel.overwrites_for(everyone)

        if row and row["original_perms"]:
            original = row["original_perms"]
            overwrite.send_messages = original.get("send_messages")
            overwrite.add_reactions = original.get("add_reactions")
        else:
            overwrite.send_messages = None

        await channel.set_permissions(everyone, overwrite=overwrite, reason="Unlock")
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM lockdown_state WHERE guild_id=$1 AND channel_id=$2",
                               channel.guild.id, channel.id)

        plugin_cfg = get_plugin_config(config, "lockdown")
        unlocked_msg = (plugin_cfg.get("config", {}) or {}).get("messages", {}).get("unlocked", "🔓 This channel has been unlocked.")
        try:
            await channel.send(unlocked_msg)
        except Exception:
            pass

    @commands.command(name="lockdown")
    @commands.guild_only()
    async def lockdown(self, ctx, channel_or_flag: str = None, *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_level(config, "lockdown", 60)):
            return

        if channel_or_flag == "-server":
            plugin_cfg = get_plugin_config(config, "lockdown")
            cfg = plugin_cfg.get("config", {}) or {}
            lockdown_channels = cfg.get("lockdown_channels", []) or []

            if lockdown_channels:
                channels = [ctx.guild.get_channel(int(c)) for c in lockdown_channels]
                channels = [c for c in channels if c and isinstance(c, discord.TextChannel)]
            else:
                channels = [c for c in ctx.guild.channels if isinstance(c, discord.TextChannel)]

            count = 0
            for ch in channels:
                try:
                    await self._lock_channel(ch, reason, config)
                    count += 1
                except Exception:
                    pass
            await ctx.send(f"🔒 Server lockdown: locked {count} channels. Reason: {reason}")

            log_channel_id = (plugin_cfg.get("config", {}) or {}).get("log_channel")
            if log_channel_id:
                log_ch = ctx.guild.get_channel(int(log_channel_id))
                if log_ch:
                    await log_ch.send(embed=discord.Embed(
                        title="Server Lockdown",
                        description=f"Locked {count} channels by {ctx.author.mention}\nReason: {reason}",
                        color=0xC46D7A
                    ))
        else:
            channel = ctx.channel
            if channel_or_flag:
                try:
                    channel = await commands.TextChannelConverter().convert(ctx, channel_or_flag)
                except Exception:
                    reason = f"{channel_or_flag} {reason}".strip()

            await self._lock_channel(channel, reason, config)

    @commands.command(name="unlock")
    @commands.guild_only()
    async def unlock(self, ctx, channel_or_flag: str = None, *, reason: str = ""):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_level(config, "unlock", 60)):
            return

        if channel_or_flag == "-server":
            plugin_cfg = get_plugin_config(config, "lockdown")
            cfg = plugin_cfg.get("config", {}) or {}
            lockdown_channels = cfg.get("lockdown_channels", []) or []

            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT channel_id FROM lockdown_state WHERE guild_id=$1", ctx.guild.id
                )
            channel_ids = [r["channel_id"] for r in rows] if rows else [int(c) for c in lockdown_channels]
            channels = [ctx.guild.get_channel(cid) for cid in channel_ids]
            channels = [c for c in channels if c and isinstance(c, discord.TextChannel)]

            count = 0
            for ch in channels:
                try:
                    await self._unlock_channel(ch, config)
                    count += 1
                except Exception:
                    pass
            await ctx.send(f"🔓 Server unlock: unlocked {count} channels.")
        else:
            channel = ctx.channel
            if channel_or_flag:
                try:
                    channel = await commands.TextChannelConverter().convert(ctx, channel_or_flag)
                except Exception:
                    pass
            await self._unlock_channel(channel, config)


async def setup(bot):
    await bot.add_cog(LockdownCog(bot))
