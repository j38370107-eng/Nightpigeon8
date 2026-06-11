import discord
from discord.ext import commands
from datetime import datetime, timezone
import asyncio
import logging
from bot.core.config_loader import get_config, get_plugin_config
from bot.core.level_check import get_user_level
from bot.core.duration import parse_duration, format_duration
from bot.core.database import get_pool, create_case
from bot.core.message_formatter import send_message, send_dm

log = logging.getLogger("bot.mass_actions")


class MassActionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_level(self, ctx, level: int) -> bool:
        user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
        if user_level < level:
            config = await get_config(ctx.guild.id)
            await send_message(ctx, config, "moderation", "no_permission")
            return False
        return True

    def _get_mass_limit(self, config):
        plugin_cfg = get_plugin_config(config, "mass_actions")
        return (plugin_cfg.get("config", {}) or {}).get("mass_limit", 20)

    def _parse_mass_args(self, ctx, args: tuple):
        """Parse members + optional duration + reason from args."""
        members = []
        duration_str = None
        reason_parts = []
        import re
        duration_pattern = re.compile(r"^\d+(?:s|m|h|d|w|mo|y)$", re.IGNORECASE)

        for arg in args:
            if isinstance(arg, (discord.Member, discord.User)):
                members.append(arg)
            elif isinstance(arg, str):
                if not members and duration_pattern.match(arg):
                    duration_str = arg
                else:
                    reason_parts.append(arg)

        reason = " ".join(reason_parts) or "No reason provided"
        return members, duration_str, reason

    @commands.command(name="masswarn")
    @commands.guild_only()
    async def masswarn(self, ctx, members: commands.Greedy[discord.Member], *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        if not await self._check_level(ctx, 50):
            return

        limit = self._get_mass_limit(config)
        members = members[:limit]
        if not members:
            return await ctx.send("No valid members provided.")

        msg = await ctx.send(f"Processing mass warn for {len(members)} users...")
        success, failed = 0, 0

        plugin_cfg = get_plugin_config(config, "moderation")
        dm_on_action = (plugin_cfg.get("config", {}) or {}).get("dm_on_action", True)

        for member in members:
            try:
                if dm_on_action:
                    await send_dm(member, config, "moderation", "warn_dm",
                                  server=ctx.guild.name, reason=reason)
                await create_case(ctx.guild.id, member.id, str(member),
                                  ctx.author.id, str(ctx.author), "warn", reason)
                success += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.5)

        await msg.edit(content=f"Mass warn complete. ✅ Success: {success}, ❌ Failed: {failed}")

    @commands.command(name="massmute")
    @commands.guild_only()
    async def massmute(self, ctx, members: commands.Greedy[discord.Member], *, args: str = ""):
        config = await get_config(ctx.guild.id)
        if not await self._check_level(ctx, 50):
            return

        import re
        parts = args.split()
        duration_str, reason = None, "No reason provided"
        if parts and re.match(r"^\d+(?:s|m|h|d|w|mo|y)$", parts[0], re.IGNORECASE):
            duration_str = parts[0]
            reason = " ".join(parts[1:]) or "No reason provided"
        else:
            reason = args or "No reason provided"

        td = None
        if duration_str:
            try:
                td = parse_duration(duration_str)
            except ValueError as e:
                return await ctx.send(str(e))

        plugin_cfg = get_plugin_config(config, "moderation")
        cfg = plugin_cfg.get("config", {}) or {}
        mute_role_id = cfg.get("mute_role")
        if not mute_role_id:
            return await ctx.send("No mute role configured.")

        mute_role = ctx.guild.get_role(int(mute_role_id))
        if not mute_role:
            return await ctx.send("Mute role not found.")

        limit = self._get_mass_limit(config)
        members = members[:limit]
        if not members:
            return await ctx.send("No valid members provided.")

        msg = await ctx.send(f"Processing mass mute for {len(members)} users...")
        success, failed = 0, 0
        expires_at = datetime.now(timezone.utc) + td if td else None

        for member in members:
            try:
                await member.add_roles(mute_role, reason=f"[Mass Mute] {ctx.author}")
                pool = await get_pool()
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO muted_users (guild_id,user_id,removed_roles,expires_at) VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
                        ctx.guild.id, member.id, [], expires_at
                    )
                await create_case(ctx.guild.id, member.id, str(member),
                                  ctx.author.id, str(ctx.author), "mute", reason,
                                  duration_str, expires_at)
                success += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.5)

        await msg.edit(content=f"Mass mute complete. ✅ Success: {success}, ❌ Failed: {failed}")

    @commands.command(name="masskick")
    @commands.guild_only()
    async def masskick(self, ctx, members: commands.Greedy[discord.Member], *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        if not await self._check_level(ctx, 50):
            return

        limit = self._get_mass_limit(config)
        members = members[:limit]
        if not members:
            return await ctx.send("No valid members provided.")

        msg = await ctx.send(f"Processing mass kick for {len(members)} users...")
        success, failed = 0, 0

        for member in members:
            try:
                await member.kick(reason=f"[Mass Kick] {ctx.author}: {reason}")
                await create_case(ctx.guild.id, member.id, str(member),
                                  ctx.author.id, str(ctx.author), "kick", reason)
                success += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.5)

        await msg.edit(content=f"Mass kick complete. ✅ Success: {success}, ❌ Failed: {failed}")

    @commands.command(name="massban")
    @commands.guild_only()
    async def massban(self, ctx, members: commands.Greedy[discord.Member], *, args: str = ""):
        config = await get_config(ctx.guild.id)
        if not await self._check_level(ctx, 60):
            return

        import re
        parts = args.split()
        duration_str, reason = None, "No reason provided"
        if parts and re.match(r"^\d+(?:s|m|h|d|w|mo|y)$", parts[0], re.IGNORECASE):
            duration_str = parts[0]
            reason = " ".join(parts[1:]) or "No reason provided"
        else:
            reason = args or "No reason provided"

        td = None
        if duration_str:
            try:
                td = parse_duration(duration_str)
            except ValueError as e:
                return await ctx.send(str(e))

        limit = self._get_mass_limit(config)
        members = members[:limit]
        if not members:
            return await ctx.send("No valid members provided.")

        msg = await ctx.send(f"Processing mass ban for {len(members)} users...")
        success, failed = 0, 0
        expires_at = datetime.now(timezone.utc) + td if td else None

        for member in members:
            try:
                await ctx.guild.ban(member, reason=f"[Mass Ban] {ctx.author}: {reason}", delete_message_days=0)
                if td:
                    pool = await get_pool()
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO timed_bans (guild_id,user_id,expires_at) VALUES ($1,$2,$3) ON CONFLICT DO UPDATE SET expires_at=$3",
                            ctx.guild.id, member.id, expires_at
                        )
                await create_case(ctx.guild.id, member.id, str(member),
                                  ctx.author.id, str(ctx.author), "ban", reason,
                                  duration_str, expires_at)
                success += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.5)

        await msg.edit(content=f"Mass ban complete. ✅ Success: {success}, ❌ Failed: {failed}")

    @commands.command(name="massunban")
    @commands.guild_only()
    async def massunban(self, ctx, *user_ids: int):
        config = await get_config(ctx.guild.id)
        if not await self._check_level(ctx, 60):
            return

        if not user_ids:
            return await ctx.send("Provide user IDs to unban.")

        reason_words = []
        ids = []
        for uid in user_ids:
            ids.append(uid)

        reason = "Mass unban"
        msg = await ctx.send(f"Processing mass unban for {len(ids)} users...")
        success, failed = 0, 0

        pool = await get_pool()
        for user_id in ids:
            try:
                await ctx.guild.unban(discord.Object(id=user_id), reason=f"[Mass Unban] {ctx.author}")
                async with pool.acquire() as conn:
                    await conn.execute("DELETE FROM timed_bans WHERE guild_id=$1 AND user_id=$2",
                                       ctx.guild.id, user_id)
                await create_case(ctx.guild.id, user_id, str(user_id),
                                  ctx.author.id, str(ctx.author), "unban", reason)
                success += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.5)

        await msg.edit(content=f"Mass unban complete. ✅ Success: {success}, ❌ Failed: {failed}")


async def setup(bot):
    await bot.add_cog(MassActionsCog(bot))
