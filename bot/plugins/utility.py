import discord
from discord.ext import commands
from datetime import datetime, timezone
import platform
import logging
import time
from bot.core.config_loader import get_config, get_plugin_config
from bot.core.level_check import get_user_level

log = logging.getLogger("bot.utility")
START_TIME = time.time()


async def _check_level(ctx, level: int) -> bool:
    user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
    return user_level >= level


class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_cmd_level(self, config, cmd, default=0):
        plugin_cfg = get_plugin_config(config, "utility")
        levels = ((plugin_cfg.get("config", {}) or {}).get("levels", {}) or {})
        return levels.get(cmd, default)

    @commands.command(name="userinfo")
    @commands.guild_only()
    async def userinfo(self, ctx, user: discord.Member = None):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_cmd_level(config, "userinfo", 0)):
            return await ctx.send("You don't have permission to use this.")
        target = user or ctx.author
        level = await get_user_level(ctx.guild.id, target.id, target)
        roles = [r.mention for r in sorted(target.roles[1:], key=lambda r: -r.position)]
        embed = discord.Embed(color=target.color or 0x6D78C4)
        embed.set_author(name=str(target), icon_url=target.display_avatar.url)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID", value=str(target.id), inline=True)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="Joined Server", value=f"<t:{int(target.joined_at.timestamp())}:R>" if target.joined_at else "Unknown", inline=True)
        embed.add_field(name="Account Created", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Roles", value=", ".join(roles[:10]) or "None", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="avatar")
    @commands.guild_only()
    async def avatar(self, ctx, user: discord.Member = None):
        target = user or ctx.author
        embed = discord.Embed(title=f"{target}'s Avatar", color=0x6D78C4)
        embed.set_image(url=target.display_avatar.url)
        embed.description = f"[Download]({target.display_avatar.url})"
        await ctx.send(embed=embed)

    @commands.command(name="banner")
    @commands.guild_only()
    async def banner(self, ctx, user: discord.Member = None):
        target = user or ctx.author
        try:
            fetched = await self.bot.fetch_user(target.id)
            if fetched.banner:
                embed = discord.Embed(title=f"{target}'s Banner", color=0x6D78C4)
                embed.set_image(url=fetched.banner.url)
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"{target} has no banner.")
        except Exception:
            await ctx.send("Could not fetch banner.")

    @commands.command(name="roles")
    @commands.guild_only()
    async def roles(self, ctx, user: discord.Member = None):
        target = user or ctx.author
        sorted_roles = sorted(target.roles[1:], key=lambda r: -r.position)
        role_list = " ".join(r.mention for r in sorted_roles) or "No roles"
        embed = discord.Embed(title=f"Roles for {target}", description=role_list, color=0x6D78C4)
        await ctx.send(embed=embed)

    @commands.command(name="joined")
    @commands.guild_only()
    async def joined(self, ctx, user: discord.Member = None):
        target = user or ctx.author
        if not target.joined_at:
            return await ctx.send("Could not determine join date.")
        sorted_members = sorted([m for m in ctx.guild.members if m.joined_at], key=lambda m: m.joined_at)
        position = sorted_members.index(target) + 1 if target in sorted_members else "?"
        embed = discord.Embed(color=0x6D78C4)
        embed.set_author(name=str(target))
        embed.add_field(name="Joined", value=f"<t:{int(target.joined_at.timestamp())}:F>", inline=True)
        embed.add_field(name="Join Position", value=f"#{position}", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="serverinfo")
    @commands.guild_only()
    async def serverinfo(self, ctx):
        g = ctx.guild
        embed = discord.Embed(title=g.name, color=0x6D78C4)
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Owner", value=str(g.owner), inline=True)
        embed.add_field(name="Members", value=str(g.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(g.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(g.roles)), inline=True)
        embed.add_field(name="Boost Level", value=str(g.premium_tier), inline=True)
        embed.add_field(name="ID", value=str(g.id), inline=True)
        embed.add_field(name="Created", value=f"<t:{int(g.created_at.timestamp())}:R>", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="botinfo")
    @commands.guild_only()
    async def botinfo(self, ctx):
        uptime_secs = int(time.time() - START_TIME)
        h, rem = divmod(uptime_secs, 3600)
        m, s = divmod(rem, 60)
        embed = discord.Embed(title="Nightpigeon Bot", color=0x6D78C4)
        embed.add_field(name="Uptime", value=f"{h}h {m}m {s}s", inline=True)
        embed.add_field(name="Ping", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="Commands", value=str(len(self.bot.commands)), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="channelinfo")
    @commands.guild_only()
    async def channelinfo(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        embed = discord.Embed(title=f"#{ch.name}", color=0x6D78C4)
        embed.add_field(name="ID", value=str(ch.id), inline=True)
        embed.add_field(name="Type", value=str(ch.type), inline=True)
        embed.add_field(name="Topic", value=ch.topic or "None", inline=False)
        embed.add_field(name="Slowmode", value=f"{ch.slowmode_delay}s", inline=True)
        embed.add_field(name="Category", value=ch.category.name if ch.category else "None", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(ch.created_at.timestamp())}:R>", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="roleinfo")
    @commands.guild_only()
    async def roleinfo(self, ctx, role: discord.Role):
        embed = discord.Embed(title=role.name, color=role.color)
        embed.add_field(name="ID", value=str(role.id), inline=True)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)
        embed.add_field(name="Hoisted", value=str(role.hoist), inline=True)
        embed.add_field(name="Mentionable", value=str(role.mentionable), inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Created", value=f"<t:{int(role.created_at.timestamp())}:R>", inline=True)
        key_perms = [p for p, v in role.permissions if v and p in (
            "administrator", "ban_members", "kick_members", "manage_guild",
            "manage_channels", "manage_roles", "manage_messages"
        )]
        embed.add_field(name="Key Permissions", value=", ".join(key_perms) or "None", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="lookup")
    @commands.guild_only()
    async def lookup(self, ctx, user_id: int):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_cmd_level(config, "lookup", 25)):
            return await ctx.send("You don't have permission.")
        try:
            user = await self.bot.fetch_user(user_id)
            embed = discord.Embed(title=str(user), color=0x6D78C4)
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="ID", value=str(user.id), inline=True)
            embed.add_field(name="Bot", value=str(user.bot), inline=True)
            embed.add_field(name="Created", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
            await ctx.send(embed=embed)
        except discord.NotFound:
            await ctx.send("User not found.")

    @commands.command(name="bansearch")
    @commands.guild_only()
    async def bansearch(self, ctx, user_id: int):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_cmd_level(config, "bansearch", 25)):
            return await ctx.send("You don't have permission.")
        try:
            ban_entry = await ctx.guild.fetch_ban(discord.Object(id=user_id))
            embed = discord.Embed(title="User is Banned", color=0xC46D7A)
            embed.add_field(name="User", value=str(ban_entry.user), inline=True)
            embed.add_field(name="Reason", value=ban_entry.reason or "No reason", inline=False)
            await ctx.send(embed=embed)
        except discord.NotFound:
            await ctx.send(f"User `{user_id}` is not banned in this server.")

    @commands.command(name="casecount")
    @commands.guild_only()
    async def casecount(self, ctx, user: discord.Member):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_cmd_level(config, "casecount", 25)):
            return await ctx.send("You don't have permission.")
        from bot.core.database import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT action, COUNT(*) as cnt FROM cases WHERE guild_id=$1 AND user_id=$2 AND active=TRUE GROUP BY action",
                ctx.guild.id, user.id
            )
        counts = {r["action"]: r["cnt"] for r in rows}
        embed = discord.Embed(title=f"Case Count for {user}", color=0x6D78C4)
        for action in ("warn", "mute", "kick", "ban", "note"):
            embed.add_field(name=action.title(), value=str(counts.get(action, 0)), inline=True)
        embed.add_field(name="Total", value=str(sum(counts.values())), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="permissions")
    @commands.guild_only()
    async def permissions(self, ctx, user: discord.Member = None, channel: discord.TextChannel = None):
        target = user or ctx.author
        if channel:
            perms = channel.permissions_for(target)
        else:
            perms = target.guild_permissions
        allowed = [p for p, v in perms if v]
        denied = [p for p, v in perms if not v]
        embed = discord.Embed(title=f"Permissions for {target}", color=0x6D78C4)
        embed.add_field(name="✅ Allowed", value="\n".join(allowed[:15]) or "None", inline=True)
        embed.add_field(name="❌ Denied", value="\n".join(denied[:15]) or "None", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="timestamp")
    @commands.guild_only()
    async def timestamp(self, ctx, *, time_str: str):
        from dateutil import parser as dateparser
        try:
            dt = dateparser.parse(time_str)
            if not dt:
                return await ctx.send("Could not parse time.")
            ts = int(dt.timestamp())
            embed = discord.Embed(title="Timestamp", color=0x6D78C4)
            embed.add_field(name="Short", value=f"`<t:{ts}:f>` → <t:{ts}:f>", inline=False)
            embed.add_field(name="Relative", value=f"`<t:{ts}:R>` → <t:{ts}:R>", inline=False)
            embed.add_field(name="Unix", value=str(ts), inline=True)
            await ctx.send(embed=embed)
        except Exception:
            await ctx.send("Could not parse time string.")

    @commands.command(name="charinfo")
    @commands.guild_only()
    async def charinfo(self, ctx, char: str):
        import unicodedata
        char = char[0] if char else ""
        if not char:
            return await ctx.send("Provide a character.")
        name = unicodedata.name(char, "Unknown")
        cp = f"U+{ord(char):04X}"
        cat = unicodedata.category(char)
        embed = discord.Embed(title=f"Character: {char}", color=0x6D78C4)
        embed.add_field(name="Name", value=name, inline=True)
        embed.add_field(name="Code Point", value=cp, inline=True)
        embed.add_field(name="Category", value=cat, inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="help")
    @commands.guild_only()
    async def help(self, ctx, command_name: str = None):
        config = await get_config(ctx.guild.id)
        if command_name:
            cmd = self.bot.get_command(command_name)
            if not cmd:
                return await ctx.send(f"Command `{command_name}` not found.")
            embed = discord.Embed(title=f"Help: {cmd.name}", color=0x6D78C4)
            embed.add_field(name="Usage", value=f"`{ctx.prefix}{cmd.name} {cmd.signature}`", inline=False)
            if cmd.help:
                embed.add_field(name="Description", value=cmd.help, inline=False)
            await ctx.send(embed=embed)
        else:
            plugins_cfg = config.get("plugins", {}) or {}
            embed = discord.Embed(title="Nightpigeon Help", color=0x6D78C4)
            enabled = [name for name, val in plugins_cfg.items() if isinstance(val, dict) and val.get("enabled", False)]
            if enabled:
                embed.description = f"Enabled plugins: {', '.join(enabled)}\nUse `{ctx.prefix}help <command>` for details."
            else:
                embed.description = f"Use `{ctx.prefix}help <command>` for details on a specific command."
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
