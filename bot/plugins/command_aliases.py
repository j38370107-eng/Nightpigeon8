import discord
from discord.ext import commands
import logging
from bot.core.config_loader import get_config, get_plugin_config

log = logging.getLogger("bot.command_aliases")


class CommandAliasesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        config = await get_config(message.guild.id)
        plugin_cfg = get_plugin_config(config, "command_aliases")
        if not plugin_cfg:
            return

        aliases = (plugin_cfg.get("config", {}) or {}).get("aliases", {}) or {}
        if not aliases:
            return

        prefix = config.get("prefix", "!")
        if not message.content.startswith(prefix):
            return

        content = message.content[len(prefix):]
        parts = content.split(None, 1)
        if not parts:
            return

        alias_key = parts[0].lower()
        if alias_key in aliases:
            full_command = aliases[alias_key]
            rest = f" {parts[1]}" if len(parts) > 1 else ""
            message.content = f"{prefix}{full_command}{rest}"
            await self.bot.process_commands(message)


async def setup(bot):
    await bot.add_cog(CommandAliasesCog(bot))
