import discord
from discord.ext import commands
import logging
from bot.core.config_loader import get_config, get_plugin_config

log = logging.getLogger("bot.preset_reasons")


class PresetReasonsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


async def resolve_preset(guild_id: int, reason: str) -> str:
    """Resolve a preset reason code to its full text."""
    config = await get_config(guild_id)
    plugin_cfg = get_plugin_config(config, "preset_reasons")
    presets = (plugin_cfg.get("config", {}) or {}).get("presets", {}) or {}
    key = reason.strip().lower()
    return presets.get(key, reason)


async def setup(bot):
    await bot.add_cog(PresetReasonsCog(bot))
