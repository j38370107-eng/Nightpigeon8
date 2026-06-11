import discord
from discord.ext import commands
from datetime import datetime


class Logging(commands.Cog):
    """Server event logging driven purely by YAML config."""

    def __init__(self, bot):
        self.bot = bot

    def _get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        cfg = self.bot.config_manager.get(guild.id)
        channel_id = cfg.get("plugins", {}).get("logs", {}).get("config", {}).get("log_channel")
        if channel_id:
            return guild.get_channel(int(channel_id))
        return None

    def _event_enabled(self, guild_id: int, event: str) -> bool:
        cfg = self.bot.config_manager.get(guild_id)
        include = cfg.get("plugins", {}).get("logs", {}).get("config", {}).get("include", [])
        if not include:
            return True
        return event in include

    async def _send(self, guild: discord.Guild, embed: discord.Embed):
        ch = self._get_log_channel(guild)
        if ch:
            try:
                await ch.send(embed=embed)
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not self._event_enabled(message.guild.id, "message_delete"):
            return
        if not message.content and not message.attachments:
            return
        embed = discord.Embed(title="🗑️ Message Deleted", color=discord.Color.red(), timestamp=datetime.utcnow())
        embed.add_field(name="Author", value=f"{message.author.mention} (`{message.author}`)", inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        if message.content:
            embed.add_field(name="Content", value=message.content[:1000], inline=False)
        embed.set_footer(text=f"User ID: {message.author.id}")
        await self._send(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return
        if not self._event_enabled(before.guild.id, "message_edit"):
            return
        embed = discord.Embed(title="✏️ Message Edited", color=discord.Color.blue(),
                              timestamp=datetime.utcnow(), url=after.jump_url)
        embed.add_field(name="Author", value=f"{before.author.mention} (`{before.author}`)", inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=before.content[:500] or "*empty*", inline=False)
        embed.add_field(name="After", value=after.content[:500] or "*empty*", inline=False)
        embed.set_footer(text=f"User ID: {before.author.id}")
        await self._send(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not self._event_enabled(member.guild.id, "member_join"):
            return
        age_days = (discord.utils.utcnow() - member.created_at).days
        embed = discord.Embed(title="✅ Member Joined", color=discord.Color.green(), timestamp=datetime.utcnow())
        embed.add_field(name="Member", value=f"{member.mention} (`{member}`)", inline=False)
        embed.add_field(name="Account Age", value=f"{age_days} days", inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"User ID: {member.id}")
        if age_days < 7:
            embed.color = discord.Color.yellow()
            embed.add_field(name="⚠️ New Account", value="Less than 7 days old", inline=False)
        await self._send(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not self._event_enabled(member.guild.id, "member_leave"):
            return
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        embed = discord.Embed(title="👋 Member Left", color=discord.Color.orange(), timestamp=datetime.utcnow())
        embed.add_field(name="Member", value=f"`{member}` (`{member.id}`)", inline=False)
        if roles:
            embed.add_field(name="Roles", value=", ".join(roles[:10]), inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"User ID: {member.id}")
        await self._send(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if not self._event_enabled(guild.id, "member_ban"):
            return
        embed = discord.Embed(title="🔨 Member Banned", color=discord.Color.red(), timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"`{user}` (`{user.id}`)", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if not self._event_enabled(guild.id, "member_unban"):
            return
        embed = discord.Embed(title="✅ Member Unbanned", color=discord.Color.green(), timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"`{user}` (`{user.id}`)", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        await self._send(guild, embed)


async def setup(bot):
    await bot.add_cog(Logging(bot))
