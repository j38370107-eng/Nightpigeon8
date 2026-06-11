import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from bot.utils import parse_duration, format_duration, mod_embed, action_color
import asyncio


class Moderation(commands.Cog):
    """Core moderation commands: ban, kick, mute, warn, etc."""

    def __init__(self, bot):
        self.bot = bot
        self.unmute_task.start()

    def cog_unload(self):
        self.unmute_task.cancel()

    async def _get_mute_role(self, guild: discord.Guild) -> discord.Role | None:
        cfg = self.bot.config_manager.get(guild.id)
        role_id = cfg.get("mute_role")
        if role_id:
            role = guild.get_role(int(role_id))
            if role:
                return role
        role = discord.utils.get(guild.roles, name="Muted")
        if role:
            return role
        return None

    async def _create_mute_role(self, guild: discord.Guild) -> discord.Role:
        role = await guild.create_role(
            name="Muted",
            color=discord.Color.dark_gray(),
            reason="Auto-created mute role by bot",
        )
        for channel in guild.channels:
            try:
                await channel.set_permissions(
                    role,
                    send_messages=False,
                    speak=False,
                    add_reactions=False,
                    reason="Mute role setup",
                )
            except discord.Forbidden:
                pass
        return role

    async def _dm_user(self, user: discord.Member, action: str, guild: discord.Guild,
                       reason: str = None, duration: int = None):
        cfg = self.bot.config_manager.get(guild.id)
        if not cfg.get("moderation", {}).get("dm_on_action", True):
            return
        try:
            desc = f"You have been **{action}d** from **{guild.name}**."
            if reason:
                desc += f"\n**Reason:** {reason}"
            if duration:
                desc += f"\n**Duration:** {format_duration(duration)}"
            embed = discord.Embed(description=desc, color=action_color(action), timestamp=datetime.utcnow())
            embed.set_footer(text=guild.name, icon_url=guild.icon.url if guild.icon else None)
            await user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self, ctx, member: discord.Member, duration: str = None, *, reason: str = None):
        """Ban a member. Optionally with a duration (tempban): !ban @user 7d Spamming"""
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(embed=discord.Embed(
                description="❌ You cannot ban someone with an equal or higher role.", color=discord.Color.red()))

        dur_seconds = parse_duration(duration) if duration else None
        if duration and not dur_seconds:
            reason = f"{duration} {reason}".strip() if reason else duration
            dur_seconds = None

        await self._dm_user(member, "ban", ctx.guild, reason, dur_seconds)
        await ctx.guild.ban(member, reason=f"[{ctx.author}] {reason or 'No reason provided'}", delete_message_days=0)

        case_num = await self.bot.db.add_case(
            ctx.guild.id, "ban", member.id, str(member), ctx.author.id, str(ctx.author),
            reason, dur_seconds
        )
        if dur_seconds:
            expires = datetime.utcnow() + timedelta(seconds=dur_seconds)
            await self.bot.db.add_case(
                ctx.guild.id, "tempban", member.id, str(member), ctx.author.id, str(ctx.author),
                f"Tempban expires <t:{int(expires.timestamp())}:R>", dur_seconds
            )

        embed = mod_embed("ban", member, ctx.author, reason, dur_seconds, case_num)
        await ctx.send(embed=embed)
        await self._send_mod_log(ctx.guild, embed)

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(self, ctx, user_id: int, *, reason: str = None):
        """Unban a user by their ID: !unban 123456789"""
        try:
            ban_entry = await ctx.guild.fetch_ban(discord.Object(id=user_id))
        except discord.NotFound:
            return await ctx.send(embed=discord.Embed(
                description="❌ That user is not banned.", color=discord.Color.red()))

        user = ban_entry.user
        await ctx.guild.unban(user, reason=f"[{ctx.author}] {reason or 'No reason provided'}")
        case_num = await self.bot.db.add_case(
            ctx.guild.id, "unban", user.id, str(user), ctx.author.id, str(ctx.author), reason
        )
        embed = mod_embed("unban", user, ctx.author, reason, case_number=case_num)
        await ctx.send(embed=embed)
        await self._send_mod_log(ctx.guild, embed)

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx, member: discord.Member, *, reason: str = None):
        """Kick a member: !kick @user Reason"""
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(embed=discord.Embed(
                description="❌ You cannot kick someone with an equal or higher role.", color=discord.Color.red()))

        await self._dm_user(member, "kick", ctx.guild, reason)
        await member.kick(reason=f"[{ctx.author}] {reason or 'No reason provided'}")
        case_num = await self.bot.db.add_case(
            ctx.guild.id, "kick", member.id, str(member), ctx.author.id, str(ctx.author), reason
        )
        embed = mod_embed("kick", member, ctx.author, reason, case_number=case_num)
        await ctx.send(embed=embed)
        await self._send_mod_log(ctx.guild, embed)

    @commands.command(name="softban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def softban(self, ctx, member: discord.Member, *, reason: str = None):
        """Softban (ban + unban to delete messages): !softban @user Spam"""
        await self._dm_user(member, "softban", ctx.guild, reason)
        await ctx.guild.ban(member, reason=f"[{ctx.author}] Softban: {reason or 'No reason'}", delete_message_days=7)
        await ctx.guild.unban(member, reason="Softban - removing messages only")
        case_num = await self.bot.db.add_case(
            ctx.guild.id, "softban", member.id, str(member), ctx.author.id, str(ctx.author), reason
        )
        embed = mod_embed("softban", member, ctx.author, reason, case_number=case_num)
        await ctx.send(embed=embed)
        await self._send_mod_log(ctx.guild, embed)

    @commands.command(name="mute")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def mute(self, ctx, member: discord.Member, duration: str = None, *, reason: str = None):
        """Mute a member: !mute @user 1h Spamming"""
        role = await self._get_mute_role(ctx.guild)
        if not role:
            async with ctx.typing():
                role = await self._create_mute_role(ctx.guild)
                self.bot.config_manager.set_key(ctx.guild.id, "mute_role", role.id)

        if role in member.roles:
            return await ctx.send(embed=discord.Embed(
                description="❌ That member is already muted.", color=discord.Color.red()))

        dur_seconds = parse_duration(duration) if duration else None
        if duration and not dur_seconds:
            reason = f"{duration} {reason}".strip() if reason else duration
            dur_seconds = None

        if not dur_seconds:
            cfg = self.bot.config_manager.get(ctx.guild.id)
            dur_seconds = cfg.get("moderation", {}).get("default_mute_duration")

        expires_at = datetime.utcnow() + timedelta(seconds=dur_seconds) if dur_seconds else None
        await member.add_roles(role, reason=f"[{ctx.author}] {reason or 'No reason'}")
        await self.bot.db.add_mute(ctx.guild.id, member.id, expires_at)
        await self._dm_user(member, "mute", ctx.guild, reason, dur_seconds)

        case_num = await self.bot.db.add_case(
            ctx.guild.id, "mute", member.id, str(member), ctx.author.id, str(ctx.author),
            reason, dur_seconds
        )
        embed = mod_embed("mute", member, ctx.author, reason, dur_seconds, case_num)
        await ctx.send(embed=embed)
        await self._send_mod_log(ctx.guild, embed)

    @commands.command(name="unmute")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def unmute(self, ctx, member: discord.Member, *, reason: str = None):
        """Unmute a member: !unmute @user"""
        role = await self._get_mute_role(ctx.guild)
        if not role or role not in member.roles:
            return await ctx.send(embed=discord.Embed(
                description="❌ That member is not muted.", color=discord.Color.red()))

        await member.remove_roles(role, reason=f"[{ctx.author}] {reason or 'Unmuted'}")
        await self.bot.db.remove_mute(ctx.guild.id, member.id)
        case_num = await self.bot.db.add_case(
            ctx.guild.id, "unmute", member.id, str(member), ctx.author.id, str(ctx.author), reason
        )
        embed = mod_embed("unmute", member, ctx.author, reason, case_number=case_num)
        await ctx.send(embed=embed)
        await self._send_mod_log(ctx.guild, embed)

    @commands.command(name="timeout")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def timeout(self, ctx, member: discord.Member, duration: str, *, reason: str = None):
        """Timeout a member using Discord's native timeout: !timeout @user 10m"""
        dur_seconds = parse_duration(duration)
        if not dur_seconds:
            return await ctx.send(embed=discord.Embed(
                description="❌ Invalid duration. Use e.g. `10m`, `1h`, `1d`.", color=discord.Color.red()))
        if dur_seconds > 2419200:
            return await ctx.send(embed=discord.Embed(
                description="❌ Maximum timeout duration is 28 days.", color=discord.Color.red()))

        until = discord.utils.utcnow() + timedelta(seconds=dur_seconds)
        await member.timeout(until, reason=f"[{ctx.author}] {reason or 'No reason'}")
        await self._dm_user(member, "timeout", ctx.guild, reason, dur_seconds)
        case_num = await self.bot.db.add_case(
            ctx.guild.id, "timeout", member.id, str(member), ctx.author.id, str(ctx.author),
            reason, dur_seconds
        )
        embed = mod_embed("timeout", member, ctx.author, reason, dur_seconds, case_num)
        await ctx.send(embed=embed)
        await self._send_mod_log(ctx.guild, embed)

    @commands.command(name="warn")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def warn(self, ctx, member: discord.Member, *, reason: str = None):
        """Warn a member: !warn @user Reason"""
        if member.bot:
            return await ctx.send(embed=discord.Embed(
                description="❌ You cannot warn a bot.", color=discord.Color.red()))

        total = await self.bot.db.add_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        case_num = await self.bot.db.add_case(
            ctx.guild.id, "warn", member.id, str(member), ctx.author.id, str(ctx.author), reason
        )
        await self._dm_user(member, "warn", ctx.guild, reason)
        embed = mod_embed("warn", member, ctx.author, reason, case_number=case_num)
        embed.add_field(name="Total Warnings", value=str(total), inline=True)
        await ctx.send(embed=embed)
        await self._send_mod_log(ctx.guild, embed)

    @commands.command(name="warnings", aliases=["infractions"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def warnings(self, ctx, member: discord.Member):
        """View warnings for a member: !warnings @user"""
        warns = await self.bot.db.get_warnings(ctx.guild.id, member.id)
        embed = discord.Embed(
            title=f"⚠️ Warnings for {member}",
            color=discord.Color.yellow(),
            description=f"**Total:** {len(warns)} warning(s)"
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        for i, w in enumerate(warns[:10], 1):
            embed.add_field(
                name=f"Warning #{i}",
                value=f"**Reason:** {w['reason'] or 'None'}\n**Date:** {w['created_at'][:10]}",
                inline=False
            )
        if len(warns) > 10:
            embed.set_footer(text=f"Showing 10 of {len(warns)} warnings")
        await ctx.send(embed=embed)

    @commands.command(name="clearwarnings", aliases=["clearwarns"])
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def clearwarnings(self, ctx, member: discord.Member):
        """Clear all warnings for a member: !clearwarnings @user"""
        count = await self.bot.db.clear_warnings(ctx.guild.id, member.id)
        await ctx.send(embed=discord.Embed(
            description=f"✅ Cleared **{count}** warning(s) for {member.mention}.",
            color=discord.Color.green()
        ))

    @commands.command(name="purge", aliases=["clear"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.guild_only()
    async def purge(self, ctx, amount: int, member: discord.Member = None):
        """Purge messages: !purge 10 or !purge 10 @user"""
        if amount < 1 or amount > 500:
            return await ctx.send(embed=discord.Embed(
                description="❌ Amount must be between 1 and 500.", color=discord.Color.red()))

        await ctx.message.delete()
        check = (lambda m: m.author == member) if member else None
        deleted = await ctx.channel.purge(limit=amount, check=check)
        msg = await ctx.send(embed=discord.Embed(
            description=f"🗑️ Deleted **{len(deleted)}** message(s){f' from {member.mention}' if member else ''}.",
            color=discord.Color.green()
        ))
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except discord.NotFound:
            pass

    @commands.command(name="case")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def case(self, ctx, case_number: int):
        """View a specific case: !case 5"""
        from bot.utils import case_embed
        c = await self.bot.db.get_case(ctx.guild.id, case_number)
        if not c:
            return await ctx.send(embed=discord.Embed(
                description=f"❌ Case #{case_number} not found.", color=discord.Color.red()))
        await ctx.send(embed=case_embed(c))

    @commands.command(name="cases", aliases=["history"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def cases(self, ctx, member: discord.Member = None):
        """View recent cases or cases for a user: !cases or !cases @user"""
        from bot.utils import case_embed
        if member:
            case_list = await self.bot.db.get_user_cases(ctx.guild.id, member.id)
            title = f"Cases for {member}"
        else:
            case_list = await self.bot.db.get_recent_cases(ctx.guild.id, 10)
            title = "Recent Cases"

        if not case_list:
            return await ctx.send(embed=discord.Embed(
                description="No cases found.", color=discord.Color.blurple()))

        embed = discord.Embed(title=f"📋 {title}", color=discord.Color.blurple())
        for c in case_list[:10]:
            from bot.utils import action_emoji
            emoji = action_emoji(c["action"])
            embed.add_field(
                name=f"{emoji} Case #{c['case_number']} — {c['action'].title()}",
                value=f"**User:** `{c['user_tag']}`\n**Reason:** {c['reason'] or 'None'}\n**Date:** {c['created_at'][:10]}",
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command(name="reason")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def reason(self, ctx, case_number: int, *, new_reason: str):
        """Update the reason for a case: !reason 5 New reason here"""
        c = await self.bot.db.get_case(ctx.guild.id, case_number)
        if not c:
            return await ctx.send(embed=discord.Embed(
                description=f"❌ Case #{case_number} not found.", color=discord.Color.red()))
        await self.bot.db.update_case_reason(ctx.guild.id, case_number, new_reason)
        await ctx.send(embed=discord.Embed(
            description=f"✅ Updated reason for case **#{case_number}**.",
            color=discord.Color.green()
        ))

    @commands.command(name="note")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def note(self, ctx, member: discord.Member, *, text: str):
        """Add a note to a member's record: !note @user This user was warned verbally"""
        case_num = await self.bot.db.add_case(
            ctx.guild.id, "note", member.id, str(member), ctx.author.id, str(ctx.author), text
        )
        await ctx.send(embed=discord.Embed(
            description=f"📝 Note added as **Case #{case_num}** for {member.mention}.",
            color=discord.Color.blurple()
        ))

    @tasks.loop(minutes=1)
    async def unmute_task(self):
        expired = await self.bot.db.get_expired_mutes()
        for mute in expired:
            guild = self.bot.get_guild(mute["guild_id"])
            if not guild:
                continue
            member = guild.get_member(mute["user_id"])
            if member:
                role = await self._get_mute_role(guild)
                if role and role in member.roles:
                    try:
                        await member.remove_roles(role, reason="Mute expired")
                    except discord.Forbidden:
                        pass
            await self.bot.db.remove_mute(mute["guild_id"], mute["user_id"])

    @unmute_task.before_loop
    async def before_unmute(self):
        await self.bot.wait_until_ready()

    async def _send_mod_log(self, guild: discord.Guild, embed: discord.Embed):
        cfg = self.bot.config_manager.get(guild.id)
        channel_id = cfg.get("mod_log_channel") or cfg.get("log_channel")
        if channel_id:
            channel = guild.get_channel(int(channel_id))
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass


async def setup(bot):
    await bot.add_cog(Moderation(bot))
