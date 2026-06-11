import discord
from discord.ext import commands
import asyncio
import logging
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled

log = logging.getLogger("bot.welcome")


class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = await get_config(member.guild.id)
        if not is_plugin_enabled(config, "welcome"):
            return
        plugin_cfg = get_plugin_config(config, "welcome")

        wait_for_verify = plugin_cfg.get("wait_for_verification", False)
        if not wait_for_verify:
            await self._handle_welcome(member, plugin_cfg)

        join_role_cfg = plugin_cfg.get("join_role", {}) or {}
        if join_role_cfg.get("enabled", False):
            role_id = join_role_cfg.get("role")
            delay = join_role_cfg.get("delay", 0)
            if role_id:
                role = member.guild.get_role(int(role_id))
                if role:
                    if delay:
                        await asyncio.sleep(delay)
                    try:
                        await member.add_roles(role, reason="Auto join role")
                    except Exception as e:
                        log.error(f"Failed to add join role: {e}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.pending and not after.pending:
            config = await get_config(after.guild.id)
            if not is_plugin_enabled(config, "welcome"):
                return
            plugin_cfg = get_plugin_config(config, "welcome")
            if plugin_cfg.get("wait_for_verification", False):
                await self._handle_welcome(after, plugin_cfg)

    async def _handle_welcome(self, member: discord.Member, plugin_cfg: dict):
        welcome_cfg = plugin_cfg.get("welcome", {}) or {}
        if not welcome_cfg.get("enabled", False):
            return

        channel_id = welcome_cfg.get("channel")
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if not channel:
            return

        msg_template = welcome_cfg.get("message", "Welcome to {server}, {user}!")
        ping = welcome_cfg.get("ping", False)
        delete_after = welcome_cfg.get("delete_after")

        kwargs = dict(
            user=member.mention if ping else str(member),
            server=member.guild.name,
            member_count=member.guild.member_count,
            avatar=member.display_avatar.url,
        )

        try:
            if isinstance(msg_template, dict) and "embed" in msg_template:
                embed_data = msg_template["embed"]
                embed = discord.Embed(
                    title=embed_data.get("title", "").format(**kwargs),
                    description=embed_data.get("description", "").format(**kwargs),
                    color=embed_data.get("color", 0x6D78C4),
                )
                if embed_data.get("thumbnail"):
                    embed.set_thumbnail(url=kwargs.get("avatar", ""))
                msg = await channel.send(
                    content=member.mention if ping else None,
                    embed=embed
                )
            else:
                text = str(msg_template).format(**kwargs)
                msg = await channel.send(text)

            if delete_after:
                await asyncio.sleep(delete_after)
                try:
                    await msg.delete()
                except Exception:
                    pass
        except Exception as e:
            log.error(f"Welcome message error: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        config = await get_config(member.guild.id)
        if not is_plugin_enabled(config, "welcome"):
            return
        plugin_cfg = get_plugin_config(config, "welcome")
        farewell_cfg = plugin_cfg.get("farewell", {}) or {}
        if not farewell_cfg.get("enabled", False):
            return

        channel_id = farewell_cfg.get("channel")
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if not channel:
            return

        msg_template = farewell_cfg.get("message", "{user} has left the server.")
        kwargs = dict(
            user=str(member),
            server=member.guild.name,
            member_count=member.guild.member_count,
        )
        try:
            await channel.send(str(msg_template).format(**kwargs))
        except Exception as e:
            log.error(f"Farewell message error: {e}")


async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
