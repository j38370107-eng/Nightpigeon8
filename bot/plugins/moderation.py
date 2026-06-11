import discord
from discord.ext import commands
from datetime import datetime, timezone
import logging
from bot.core.config_loader import get_config, get_plugin_config
from bot.core.level_check import get_user_level
from bot.core.duration import parse_duration, format_duration
from bot.core.database import get_pool, create_case
from bot.core.message_formatter import send_message, send_dm

log = logging.getLogger("bot.moderation")


def _get_level(config: dict, command: str, default: int = 50) -> int:
    plugin_cfg = get_plugin_config(config, "moderation")
    cfg = plugin_cfg.get("config", {}) or {}
    levels = cfg.get("levels", {}) or {}
    return levels.get(command, cfg.get("required_level", default))


async def _check_level(ctx, level: int) -> bool:
    user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
    if user_level < level:
        config = await get_config(ctx.guild.id)
        await send_message(ctx, config, "moderation", "no_permission")
        return False
    return True


class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _apply_preset_reason(self, guild_id: int, reason: str) -> str:
        config = await get_config(guild_id)
        plugin_cfg = get_plugin_config(config, "preset_reasons")
        presets = (plugin_cfg.get("config", {}) or {}).get("presets", {}) or {}
        key = reason.strip().lower()
        return presets.get(key, reason)

    @commands.command(name="ban")
    @commands.guild_only()
    async def ban(self, ctx, user: discord.Member, *, args: str = ""):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "ban", 60)):
            return

        duration_str, reason = self._parse_duration_reason(args)
        reason = await self._apply_preset_reason(ctx.guild.id, reason)
        td = None
        if duration_str:
            try:
                td = parse_duration(duration_str)
            except ValueError as e:
                return await ctx.send(str(e))

        plugin_cfg = get_plugin_config(config, "moderation")
        dm_on_action = (plugin_cfg.get("config", {}) or {}).get("dm_on_action", True)
        dur_str = format_duration(td)

        if dm_on_action:
            await send_dm(user, config, "moderation", "ban_dm",
                          server=ctx.guild.name, reason=reason, duration=dur_str)

        await ctx.guild.ban(user, reason=f"[{ctx.author}] {reason}", delete_message_days=0)

        expires_at = None
        if td:
            expires_at = datetime.now(timezone.utc) + td
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO timed_bans (guild_id, user_id, expires_at) VALUES ($1,$2,$3) ON CONFLICT (guild_id,user_id) DO UPDATE SET expires_at=$3",
                    ctx.guild.id, user.id, expires_at
                )

        case = await create_case(ctx.guild.id, user.id, str(user), ctx.author.id, str(ctx.author),
                                  "ban", reason, duration_str or None, expires_at)

        await self._post_mod_log(ctx.guild, config, case)
        await send_message(ctx, config, "moderation", "ban_reply",
                           user=str(user), case=case["case_number"], reason=reason, duration=dur_str)
        await self._check_escalation(ctx, config, user)

    @commands.command(name="forceban")
    @commands.guild_only()
    async def forceban(self, ctx, user_id: int, *, args: str = ""):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "forceban", 70)):
            return

        duration_str, reason = self._parse_duration_reason(args)
        reason = await self._apply_preset_reason(ctx.guild.id, reason)
        td = None
        if duration_str:
            try:
                td = parse_duration(duration_str)
            except ValueError as e:
                return await ctx.send(str(e))

        try:
            user_obj = discord.Object(id=user_id)
            await ctx.guild.ban(user_obj, reason=f"[{ctx.author}] {reason}", delete_message_days=0)
        except discord.NotFound:
            return await ctx.send("User not found.")
        except discord.Forbidden:
            return await ctx.send("I don't have permission to ban that user.")

        expires_at = None
        if td:
            expires_at = datetime.now(timezone.utc) + td
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO timed_bans (guild_id, user_id, expires_at) VALUES ($1,$2,$3) ON CONFLICT (guild_id,user_id) DO UPDATE SET expires_at=$3",
                    ctx.guild.id, user_id, expires_at
                )

        case = await create_case(ctx.guild.id, user_id, str(user_id), ctx.author.id, str(ctx.author),
                                  "forceban", reason, duration_str or None, expires_at)
        await self._post_mod_log(ctx.guild, config, case)
        await send_message(ctx, config, "moderation", "forceban_reply",
                           user=str(user_id), case=case["case_number"], reason=reason,
                           duration=format_duration(td))

    @commands.command(name="unban")
    @commands.guild_only()
    async def unban(self, ctx, user_id: int, *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "unban", 60)):
            return

        reason = await self._apply_preset_reason(ctx.guild.id, reason)
        try:
            user_obj = discord.Object(id=user_id)
            await ctx.guild.unban(user_obj, reason=f"[{ctx.author}] {reason}")
        except discord.NotFound:
            return await ctx.send("That user is not banned.")

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM timed_bans WHERE guild_id=$1 AND user_id=$2",
                               ctx.guild.id, user_id)

        case = await create_case(ctx.guild.id, user_id, str(user_id), ctx.author.id, str(ctx.author),
                                  "unban", reason)
        await self._post_mod_log(ctx.guild, config, case)
        await send_message(ctx, config, "moderation", "unban_reply",
                           user=str(user_id), case=case["case_number"], reason=reason)

    @commands.command(name="kick")
    @commands.guild_only()
    async def kick(self, ctx, user: discord.Member, *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "kick", 50)):
            return

        reason = await self._apply_preset_reason(ctx.guild.id, reason)
        plugin_cfg = get_plugin_config(config, "moderation")
        dm_on_action = (plugin_cfg.get("config", {}) or {}).get("dm_on_action", True)

        if dm_on_action:
            await send_dm(user, config, "moderation", "kick_dm",
                          server=ctx.guild.name, reason=reason)

        try:
            await user.kick(reason=f"[{ctx.author}] {reason}")
        except discord.Forbidden:
            return await ctx.send("I don't have permission to kick that user.")

        case = await create_case(ctx.guild.id, user.id, str(user), ctx.author.id, str(ctx.author),
                                  "kick", reason)
        await self._post_mod_log(ctx.guild, config, case)
        await send_message(ctx, config, "moderation", "kick_reply",
                           user=str(user), case=case["case_number"], reason=reason)
        await self._check_escalation(ctx, config, user)

    @commands.command(name="mute")
    @commands.guild_only()
    async def mute(self, ctx, user: discord.Member, *, args: str = ""):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "mute", 50)):
            return

        plugin_cfg = get_plugin_config(config, "moderation")
        cfg = plugin_cfg.get("config", {}) or {}
        mute_role_id = cfg.get("mute_role")
        if not mute_role_id:
            return await ctx.send("No mute role configured. Set `mute_role` in the moderation plugin config.")

        mute_role = ctx.guild.get_role(int(mute_role_id))
        if not mute_role:
            return await ctx.send("Mute role not found.")

        duration_str, reason = self._parse_duration_reason(args)
        reason = await self._apply_preset_reason(ctx.guild.id, reason)
        td = None
        if duration_str:
            try:
                td = parse_duration(duration_str)
            except ValueError as e:
                return await ctx.send(str(e))

        remove_roles = cfg.get("remove_roles_on_mute", True)
        saved_roles = []
        if remove_roles:
            saved_roles = [r.id for r in user.roles
                           if r != ctx.guild.default_role and r != mute_role and not r.managed]
            try:
                roles_to_remove = [r for r in user.roles
                                   if r != ctx.guild.default_role and r != mute_role and not r.managed]
                await user.remove_roles(*roles_to_remove, reason="Mute: removing roles")
            except discord.Forbidden:
                pass

        await user.add_roles(mute_role, reason=f"[{ctx.author}] {reason}")

        expires_at = None
        if td:
            expires_at = datetime.now(timezone.utc) + td

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO muted_users (guild_id, user_id, removed_roles, expires_at)
                   VALUES ($1,$2,$3,$4) ON CONFLICT (guild_id,user_id)
                   DO UPDATE SET removed_roles=$3, expires_at=$4""",
                ctx.guild.id, user.id, saved_roles, expires_at
            )

        dm_on_action = cfg.get("dm_on_action", True)
        if dm_on_action:
            await send_dm(user, config, "moderation", "mute_dm",
                          server=ctx.guild.name, reason=reason, duration=format_duration(td))

        case = await create_case(ctx.guild.id, user.id, str(user), ctx.author.id, str(ctx.author),
                                  "mute", reason, duration_str or None, expires_at)
        await self._post_mod_log(ctx.guild, config, case)
        await send_message(ctx, config, "moderation", "mute_reply",
                           user=str(user), case=case["case_number"], reason=reason, duration=format_duration(td))
        await self._check_escalation(ctx, config, user)

    @commands.command(name="unmute")
    @commands.guild_only()
    async def unmute(self, ctx, user: discord.Member, *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "unmute", 50)):
            return

        plugin_cfg = get_plugin_config(config, "moderation")
        cfg = plugin_cfg.get("config", {}) or {}
        mute_role_id = cfg.get("mute_role")
        if not mute_role_id:
            return await ctx.send("No mute role configured.")

        mute_role = ctx.guild.get_role(int(mute_role_id))

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT removed_roles FROM muted_users WHERE guild_id=$1 AND user_id=$2",
                ctx.guild.id, user.id
            )

        if mute_role and mute_role in user.roles:
            await user.remove_roles(mute_role, reason=f"[{ctx.author}] {reason}")

        if row and row["removed_roles"]:
            roles_to_restore = [ctx.guild.get_role(r) for r in row["removed_roles"]]
            roles_to_restore = [r for r in roles_to_restore if r]
            try:
                await user.add_roles(*roles_to_restore, reason="Unmute: restoring roles")
            except discord.Forbidden:
                pass

        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM muted_users WHERE guild_id=$1 AND user_id=$2",
                               ctx.guild.id, user.id)

        dm_on_action = cfg.get("dm_on_action", True)
        if dm_on_action:
            await send_dm(user, config, "moderation", "unmute_dm", server=ctx.guild.name)

        case = await create_case(ctx.guild.id, user.id, str(user), ctx.author.id, str(ctx.author),
                                  "unmute", reason)
        await self._post_mod_log(ctx.guild, config, case)
        await send_message(ctx, config, "moderation", "unmute_reply",
                           user=str(user), case=case["case_number"], reason=reason)

    @commands.command(name="warn")
    @commands.guild_only()
    async def warn(self, ctx, user: discord.Member, *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "warn", 25)):
            return

        reason = await self._apply_preset_reason(ctx.guild.id, reason)
        plugin_cfg = get_plugin_config(config, "moderation")
        dm_on_action = (plugin_cfg.get("config", {}) or {}).get("dm_on_action", True)

        if dm_on_action:
            await send_dm(user, config, "moderation", "warn_dm",
                          server=ctx.guild.name, reason=reason)

        case = await create_case(ctx.guild.id, user.id, str(user), ctx.author.id, str(ctx.author),
                                  "warn", reason)
        await self._post_mod_log(ctx.guild, config, case)
        await send_message(ctx, config, "moderation", "warn_reply",
                           user=str(user), case=case["case_number"], reason=reason)
        await self._check_escalation(ctx, config, user)

    @commands.command(name="addcase")
    @commands.guild_only()
    async def addcase(self, ctx, user: discord.Member, action: str, *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "addcase", 25)):
            return

        valid_actions = ["warn", "note", "kick", "ban", "mute"]
        if action.lower() not in valid_actions:
            return await ctx.send(f"Invalid action. Choose from: {', '.join(valid_actions)}")

        case = await create_case(ctx.guild.id, user.id, str(user), ctx.author.id, str(ctx.author),
                                  action.lower(), reason)
        await self._post_mod_log(ctx.guild, config, case)
        await send_message(ctx, config, "moderation", "addcase_reply",
                           user=str(user), case=case["case_number"])

    @commands.command(name="editcase")
    @commands.guild_only()
    async def editcase(self, ctx, case_id: int, field: str, *, value: str):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "editcase", 50)):
            return

        field = field.lower()
        if field not in ("reason", "duration"):
            return await ctx.send("Field must be `reason` or `duration`.")

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM cases WHERE guild_id=$1 AND case_number=$2",
                ctx.guild.id, case_id
            )
            if not row:
                return await send_message(ctx, config, "moderation", "case_not_found", case=case_id)
            if field == "reason":
                await conn.execute("UPDATE cases SET reason=$1 WHERE id=$2", value, row["id"])
            else:
                await conn.execute("UPDATE cases SET duration=$1 WHERE id=$2", value, row["id"])

        await send_message(ctx, config, "moderation", "editcase_reply", case=case_id)

    @commands.command(name="deletecase")
    @commands.guild_only()
    async def deletecase(self, ctx, case_id: int):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "deletecase", 75)):
            return

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM cases WHERE guild_id=$1 AND case_number=$2",
                ctx.guild.id, case_id
            )
            if not row:
                return await send_message(ctx, config, "moderation", "case_not_found", case=case_id)
            await conn.execute("UPDATE cases SET active=FALSE WHERE id=$1", row["id"])

        await send_message(ctx, config, "moderation", "deletecase_reply", case=case_id)

    @commands.command(name="reason")
    @commands.guild_only()
    async def reason(self, ctx, case_id: int, *, new_reason: str):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "editcase", 50)):
            return

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM cases WHERE guild_id=$1 AND case_number=$2",
                ctx.guild.id, case_id
            )
            if not row:
                return await send_message(ctx, config, "moderation", "case_not_found", case=case_id)
            await conn.execute("UPDATE cases SET reason=$1 WHERE id=$2", new_reason, row["id"])

        await send_message(ctx, config, "moderation", "editcase_reply", case=case_id)

    @commands.command(name="purge")
    @commands.guild_only()
    async def purge(self, ctx, count: int, user: discord.Member = None):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "purge", 25)):
            return

        count = min(count, 100)
        await ctx.message.delete()

        def check(m):
            if user:
                return m.author == user
            return True

        deleted = await ctx.channel.purge(limit=count, check=check)
        msg = await send_message(ctx, config, "moderation", "purge_reply", count=len(deleted))
        if msg:
            import asyncio
            await asyncio.sleep(3)
            try:
                await msg.delete()
            except Exception:
                pass

    @commands.command(name="slowmode")
    @commands.guild_only()
    async def slowmode(self, ctx, channel: discord.TextChannel, duration: str):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, _get_level(config, "slowmode", 50)):
            return

        if duration == "0":
            secs = 0
        else:
            try:
                td = parse_duration(duration)
                secs = int(td.total_seconds()) if td else 0
            except ValueError as e:
                return await ctx.send(str(e))

        await channel.edit(slowmode_delay=secs)
        await send_message(ctx, config, "moderation", "slowmode_reply",
                           channel=channel.mention, duration=duration)

    async def _post_mod_log(self, guild, config, case):
        plugin_cfg = get_plugin_config(config, "logging")
        if not plugin_cfg.get("enabled", False):
            return
        channels = (plugin_cfg.get("channels", {}) or {})
        log_channel_id = channels.get("mod_log")
        if not log_channel_id:
            return
        channel = guild.get_channel(int(log_channel_id))
        if not channel:
            return

        action_colors = {
            "ban": 0xC46D7A, "forceban": 0xC46D7A, "kick": 0xC4A46D,
            "mute": 0xC4A46D, "warn": 0xC4A46D, "unban": 0x6CBF8A,
            "unmute": 0x6CBF8A, "note": 0x6D78C4,
        }
        color = action_colors.get(case["action"], 0x6D78C4)
        embed = discord.Embed(
            title=f"Case #{case['case_number']} — {case['action'].title()}",
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="User", value=f"{case['user_tag']} (`{case['user_id']}`)", inline=True)
        embed.add_field(name="Moderator", value=f"{case['moderator_tag']}", inline=True)
        embed.add_field(name="Reason", value=case["reason"] or "No reason", inline=False)
        if case.get("duration"):
            embed.add_field(name="Duration", value=case["duration"], inline=True)
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    async def _check_escalation(self, ctx, config, user: discord.Member):
        from bot.plugins.escalation import check_manual_escalation
        try:
            await check_manual_escalation(self.bot, ctx, config, user)
        except Exception:
            pass

    def _parse_duration_reason(self, args: str) -> tuple[str | None, str]:
        if not args:
            return None, "No reason provided"
        parts = args.split()
        import re
        if parts and re.match(r"^\d+(?:s|m|h|d|w|mo|y)$", parts[0], re.IGNORECASE):
            return parts[0], " ".join(parts[1:]) or "No reason provided"
        return None, args or "No reason provided"


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
