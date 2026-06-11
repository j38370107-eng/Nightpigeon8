import discord
from discord.ext import commands
from datetime import datetime


class Logging(commands.Cog):
    """Server event logging: message edits/deletes, member join/leave, bans."""

    def __init__(self, bot):
        self.bot = bot

    def _get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        cfg = self.bot.config_manager.get(guild.id)
        channel_id = cfg.get("log_channel")
        if channel_id:
            return guild.get_channel(int(channel_id))
        return None

    def _logging_enabled(self, guild_id: int, event: str) -> bool:
        cfg = self.bot.config_manager.get(guild_id)
        return cfg.get("logging", {}).get(event, True)

    async def _send_log(self, guild: discord.Guild, embed: discord.Embed):
        channel = self._get_log_channel(guild)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not self._logging_enabled(message.guild.id, "message_delete"):
            return
        if not message.content and not message.attachments:
            return

        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Author", value=f"{message.author.mention} (`{message.author}`)", inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        if message.content:
            content = message.content[:1000] + ("..." if len(message.content) > 1000 else "")
            embed.add_field(name="Content", value=content, inline=False)
        if message.attachments:
            embed.add_field(
                name="Attachments",
                value="\n".join(a.filename for a in message.attachments),
                inline=False,
            )
        embed.set_footer(text=f"User ID: {message.author.id} | Message ID: {message.id}")
        await self._send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return
        if not self._logging_enabled(before.guild.id, "message_edit"):
            return

        embed = discord.Embed(
            title="✏️ Message Edited",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow(),
            url=after.jump_url,
        )
        embed.add_field(name="Author", value=f"{before.author.mention} (`{before.author}`)", inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        before_content = before.content[:500] + ("..." if len(before.content) > 500 else "")
        after_content = after.content[:500] + ("..." if len(after.content) > 500 else "")
        embed.add_field(name="Before", value=before_content or "*empty*", inline=False)
        embed.add_field(name="After", value=after_content or "*empty*", inline=False)
        embed.set_footer(text=f"User ID: {before.author.id} | Message ID: {before.id}")
        await self._send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not self._logging_enabled(member.guild.id, "member_join"):
            return

        created = member.created_at
        age_days = (discord.utils.utcnow() - created).days

        embed = discord.Embed(
            title="✅ Member Joined",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Member", value=f"{member.mention} (`{member}`)", inline=False)
        embed.add_field(name="Account Created", value=f"<t:{int(created.timestamp())}:R> ({age_days} days old)", inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"User ID: {member.id}")

        if age_days < 7:
            embed.add_field(name="⚠️ New Account", value=f"Account is only {age_days} days old!", inline=False)
            embed.color = discord.Color.yellow()

        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not self._logging_enabled(member.guild.id, "member_leave"):
            return

        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        embed = discord.Embed(
            title="👋 Member Left",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Member", value=f"`{member}` (`{member.id}`)", inline=False)
        if roles:
            embed.add_field(name="Roles", value=", ".join(roles[:10]), inline=False)
        joined = member.joined_at
        if joined:
            embed.add_field(name="Joined", value=f"<t:{int(joined.timestamp())}:R>", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"User ID: {member.id}")
        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if not self._logging_enabled(guild.id, "member_ban"):
            return

        embed = discord.Embed(
            title="🔨 Member Banned",
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="User", value=f"`{user}` (`{user.id}`)", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        await self._send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if not self._logging_enabled(guild.id, "member_unban"):
            return

        embed = discord.Embed(
            title="✅ Member Unbanned",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="User", value=f"`{user}` (`{user.id}`)", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        await self._send_log(guild, embed)


async def setup(bot):
    await bot.add_cog(Logging(bot))
