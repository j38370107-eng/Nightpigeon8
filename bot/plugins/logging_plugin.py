import discord
from discord.ext import commands
from datetime import datetime, timezone
import logging
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled

log = logging.getLogger("bot.logging")


class LoggingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_log_channel(self, guild, event_key: str):
        config = await get_config(guild.id)
        if not is_plugin_enabled(config, "logging"):
            return None
        plugin_cfg = get_plugin_config(config, "logging")
        channels = plugin_cfg.get("channels", {}) or {}
        channel_id = channels.get(event_key)
        if not channel_id:
            return None
        return guild.get_channel(int(channel_id))

    async def _is_ignored(self, guild, channel_id=None, member=None) -> bool:
        config = await get_config(guild.id)
        plugin_cfg = get_plugin_config(config, "logging")
        ignore_channels = plugin_cfg.get("ignore_channels", []) or []
        ignore_roles = plugin_cfg.get("ignore_roles", []) or []
        if channel_id and channel_id in [int(c) for c in ignore_channels]:
            return True
        if member:
            member_role_ids = [r.id for r in member.roles]
            for rid in ignore_roles:
                if int(rid) in member_role_ids:
                    return True
        return False

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return
        if await self._is_ignored(before.guild, before.channel.id, before.author):
            return

        channel = await self._get_log_channel(before.guild, "message_edit")
        if not channel:
            return

        embed = discord.Embed(title="Message Edited", color=0xC4A46D, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=before.content[:500] or "[empty]", inline=False)
        embed.add_field(name="After", value=after.content[:500] or "[empty]", inline=False)
        embed.add_field(name="Jump", value=f"[Link]({after.jump_url})", inline=True)
        embed.set_footer(text=f"User ID: {before.author.id}")
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if await self._is_ignored(message.guild, message.channel.id, message.author):
            return

        channel = await self._get_log_channel(message.guild, "message_delete")
        if not channel:
            return

        embed = discord.Embed(title="Message Deleted", color=0xC46D7A, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Content", value=message.content[:1000] or "[empty/attachment]", inline=False)
        embed.set_footer(text=f"User ID: {message.author.id}")
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if not messages:
            return
        guild = messages[0].guild
        if not guild:
            return

        channel = await self._get_log_channel(guild, "message_bulk_delete")
        if not channel:
            return

        embed = discord.Embed(
            title="Bulk Message Delete",
            description=f"{len(messages)} messages deleted in {messages[0].channel.mention}",
            color=0xC46D7A,
            timestamp=datetime.now(timezone.utc)
        )
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = await self._get_log_channel(member.guild, "member_join")
        if not channel:
            return

        age = (datetime.now(timezone.utc) - member.created_at).days
        embed = discord.Embed(title="Member Joined", color=0x6CBF8A, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="Account Age", value=f"{age} days", inline=True)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.set_footer(text=f"Member #{member.guild.member_count}")
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = await self._get_log_channel(member.guild, "member_leave")
        if not channel:
            return

        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        embed = discord.Embed(title="Member Left", color=0xC46D7A, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Roles", value=", ".join(roles[:10]) or "None", inline=False)
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        channel = await self._get_log_channel(guild, "member_ban")
        if not channel:
            return
        embed = discord.Embed(title="Member Banned", color=0xC46D7A, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="ID", value=str(user.id), inline=True)
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        channel = await self._get_log_channel(guild, "member_unban")
        if not channel:
            return
        embed = discord.Embed(title="Member Unbanned", color=0x6CBF8A, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="ID", value=str(user.id), inline=True)
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            channel = await self._get_log_channel(before.guild, "nickname_change")
            if channel:
                embed = discord.Embed(title="Nickname Changed", color=0x6D78C4, timestamp=datetime.now(timezone.utc))
                embed.set_author(name=str(before), icon_url=before.display_avatar.url)
                embed.add_field(name="Before", value=before.nick or before.name, inline=True)
                embed.add_field(name="After", value=after.nick or after.name, inline=True)
                try:
                    await channel.send(embed=embed)
                except Exception:
                    pass

        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            if added:
                channel = await self._get_log_channel(before.guild, "role_given")
                if channel:
                    embed = discord.Embed(title="Role Added", color=0x6CBF8A, timestamp=datetime.now(timezone.utc))
                    embed.set_author(name=str(before), icon_url=before.display_avatar.url)
                    embed.add_field(name="Roles Added", value=", ".join(r.mention for r in added), inline=False)
                    try:
                        await channel.send(embed=embed)
                    except Exception:
                        pass
            if removed:
                channel = await self._get_log_channel(before.guild, "role_removed")
                if channel:
                    embed = discord.Embed(title="Role Removed", color=0xC46D7A, timestamp=datetime.now(timezone.utc))
                    embed.set_author(name=str(before), icon_url=before.display_avatar.url)
                    embed.add_field(name="Roles Removed", value=", ".join(r.mention for r in removed), inline=False)
                    try:
                        await channel.send(embed=embed)
                    except Exception:
                        pass

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        channel = await self._get_log_channel(role.guild, "role_create")
        if not channel:
            return
        embed = discord.Embed(title="Role Created", color=0x6CBF8A, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="ID", value=str(role.id), inline=True)
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        channel = await self._get_log_channel(role.guild, "role_delete")
        if not channel:
            return
        embed = discord.Embed(title="Role Deleted", color=0xC46D7A, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Role", value=role.name, inline=True)
        embed.add_field(name="ID", value=str(role.id), inline=True)
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        log_channel = await self._get_log_channel(channel.guild, "channel_create")
        if not log_channel:
            return
        embed = discord.Embed(title="Channel Created", color=0x6CBF8A, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Channel", value=channel.mention if hasattr(channel, 'mention') else channel.name, inline=True)
        embed.add_field(name="ID", value=str(channel.id), inline=True)
        try:
            await log_channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        log_channel = await self._get_log_channel(channel.guild, "channel_delete")
        if not log_channel:
            return
        embed = discord.Embed(title="Channel Deleted", color=0xC46D7A, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Channel", value=channel.name, inline=True)
        embed.add_field(name="ID", value=str(channel.id), inline=True)
        try:
            await log_channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        channel = await self._get_log_channel(member.guild, "voice_update")
        if not channel:
            return
        embed = discord.Embed(color=0x6D78C4, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        if not before.channel and after.channel:
            embed.title = "Joined Voice Channel"
            embed.add_field(name="Channel", value=after.channel.name, inline=True)
        elif before.channel and not after.channel:
            embed.title = "Left Voice Channel"
            embed.add_field(name="Channel", value=before.channel.name, inline=True)
        elif before.channel != after.channel:
            embed.title = "Moved Voice Channel"
            embed.add_field(name="From", value=before.channel.name, inline=True)
            embed.add_field(name="To", value=after.channel.name, inline=True)
        else:
            return
        try:
            await channel.send(embed=embed)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(LoggingCog(bot))
