import discord
from discord.ext import commands, tasks
from datetime import datetime
import logging

log = logging.getLogger("bot.tasks")


class Tasks(commands.Cog):
    """Background tasks: mute expiry, periodic cache refresh."""

    def __init__(self, bot):
        self.bot = bot
        self.unmute_task.start()

    def cog_unload(self):
        self.unmute_task.cancel()

    async def _get_mute_role(self, guild: discord.Guild) -> discord.Role | None:
        cfg = self.bot.config_manager.get(guild.id)
        plugins = cfg.get("plugins", {})
        mutes_cfg = plugins.get("mutes", {}).get("config", {})
        role_id = mutes_cfg.get("mute_role")
        if role_id:
            role = guild.get_role(int(role_id))
            if role:
                return role
        return discord.utils.get(guild.roles, name="Muted")

    @tasks.loop(minutes=1)
    async def unmute_task(self):
        expired = await self.bot.db.get_expired_mutes()
        for mute in expired:
            guild = self.bot.get_guild(mute["guild_id"])
            if not guild:
                await self.bot.db.remove_mute(mute["guild_id"], mute["user_id"])
                continue
            member = guild.get_member(mute["user_id"])
            if member:
                role = await self._get_mute_role(guild)
                if role and role in member.roles:
                    try:
                        await member.remove_roles(role, reason="Mute expired")
                        log.info(f"Auto-unmuted {member} in {guild.name}")
                    except discord.Forbidden:
                        log.warning(f"Cannot unmute {member} in {guild.name}: missing permissions")
            await self.bot.db.remove_mute(mute["guild_id"], mute["user_id"])

    @unmute_task.before_loop
    async def before_unmute(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Tasks(bot))
