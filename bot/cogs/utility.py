import discord
from discord.ext import commands
from datetime import datetime


class Utility(commands.Cog):
    """Utility commands: ping, uptime, help, slowmode, lock, unlock."""

    def __init__(self, bot):
        self.bot = bot
        self._start_time = datetime.utcnow()

    @commands.command(name="ping")
    async def ping(self, ctx):
        """Check bot latency."""
        latency = round(self.bot.latency * 1000)
        color = discord.Color.green() if latency < 100 else discord.Color.yellow() if latency < 200 else discord.Color.red()
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: **{latency}ms**",
            color=color,
        )
        await ctx.send(embed=embed)

    @commands.command(name="uptime")
    async def uptime(self, ctx):
        """Show how long the bot has been running."""
        delta = datetime.utcnow() - self._start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        embed = discord.Embed(
            title="⏱️ Uptime",
            description=" ".join(parts),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def slowmode(self, ctx, seconds: int = 0):
        """Set slowmode for the current channel: !slowmode 5 (0 to disable)"""
        if seconds < 0 or seconds > 21600:
            return await ctx.send(embed=discord.Embed(
                description="❌ Slowmode must be between 0 and 21600 seconds.", color=discord.Color.red()))
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            desc = f"✅ Slowmode disabled in {ctx.channel.mention}."
        else:
            desc = f"✅ Slowmode set to **{seconds}s** in {ctx.channel.mention}."
        await ctx.send(embed=discord.Embed(description=desc, color=discord.Color.green()))

    @commands.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def lock(self, ctx, channel: discord.TextChannel = None, *, reason: str = None):
        """Lock a channel (prevent @everyone from sending): !lock or !lock #channel"""
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=reason)
        await channel.send(embed=discord.Embed(
            description=f"🔒 Channel locked{f' — {reason}' if reason else ''}.",
            color=discord.Color.red(),
        ))

    @commands.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def unlock(self, ctx, channel: discord.TextChannel = None, *, reason: str = None):
        """Unlock a channel: !unlock or !unlock #channel"""
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=reason)
        await channel.send(embed=discord.Embed(
            description=f"🔓 Channel unlocked{f' — {reason}' if reason else ''}.",
            color=discord.Color.green(),
        ))

    @commands.command(name="help")
    async def help_command(self, ctx, *, command_name: str = None):
        """Show help for commands."""
        cfg = self.bot.config_manager.get(ctx.guild.id) if ctx.guild else {"prefix": "!"}
        prefix = cfg.get("prefix", "!")

        if command_name:
            cmd = self.bot.get_command(command_name)
            if not cmd:
                return await ctx.send(embed=discord.Embed(
                    description=f"❌ Command `{command_name}` not found.", color=discord.Color.red()))
            embed = discord.Embed(
                title=f"📖 `{prefix}{cmd.name}`",
                description=cmd.help or "No description.",
                color=discord.Color.blurple(),
            )
            if cmd.aliases:
                embed.add_field(name="Aliases", value=", ".join(f"`{a}`" for a in cmd.aliases))
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="📖 Command Help",
            description=f"Prefix: `{prefix}` | Use `{prefix}help <command>` for details",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="🔨 Moderation",
            value=f"`ban` `unban` `kick` `softban`\n`mute` `unmute` `timeout`\n`warn` `warnings` `clearwarnings`\n`purge` `case` `cases` `reason` `note`",
            inline=False,
        )
        embed.add_field(
            name="🛡️ AutoMod",
            value=f"Configured via `{prefix}config set automod.enabled true`\nAnti-spam, anti-invite, bad words, caps filter",
            inline=False,
        )
        embed.add_field(
            name="⚙️ Config",
            value=f"`config view` `config set` `config export`\n`config import` `config reset`\n`setprefix` `setlogchannel` `setmodlog`",
            inline=False,
        )
        embed.add_field(
            name="ℹ️ Info",
            value="`userinfo` `serverinfo` `avatar` `roleinfo`",
            inline=False,
        )
        embed.add_field(
            name="🔧 Utility",
            value="`ping` `uptime` `slowmode` `lock` `unlock`",
            inline=False,
        )
        embed.set_footer(text=f"Tip: Use {prefix}config set log_channel #channel to enable logging")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Utility(bot))
