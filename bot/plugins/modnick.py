import discord
from discord.ext import commands
import re
import unicodedata
import logging
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled

log = logging.getLogger("bot.modnick")

HOIST_CHARS = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
INVISIBLE_PATTERN = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u206a-\u206f\uFEFF\u00AD]")


def _is_problematic(name: str, cfg: dict) -> bool:
    if cfg.get("block_hoisting", True):
        if name and name[0] in HOIST_CHARS:
            return True
    if cfg.get("block_invisible", True):
        if INVISIBLE_PATTERN.search(name):
            return True
    if cfg.get("block_too_short", True):
        visible = len([c for c in name if not unicodedata.combining(c) and not INVISIBLE_PATTERN.match(c)])
        if visible < 2:
            return True
    for pattern in (cfg.get("custom_patterns", []) or []):
        try:
            if re.search(pattern, name, re.IGNORECASE):
                return True
        except Exception:
            pass
    return False


class ModnickCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_and_rename(self, member: discord.Member):
        config = await get_config(member.guild.id)
        if not is_plugin_enabled(config, "modnick"):
            return
        plugin_cfg = get_plugin_config(config, "modnick")
        cfg = plugin_cfg.get("config", {}) or {}

        display = member.display_name
        if not _is_problematic(display, cfg):
            return

        replacement = cfg.get("replacement_name", "Moderated Username")
        try:
            await member.edit(nick=replacement, reason="[Modnick] Problematic display name")
            log.info(f"Renamed {member} ({member.id}) to '{replacement}' in {member.guild.name}")

            log_channel_id = cfg.get("log_channel")
            if log_channel_id:
                channel = member.guild.get_channel(int(log_channel_id))
                if channel:
                    embed = discord.Embed(
                        title="Nickname Moderated",
                        description=f"{member.mention} was renamed to `{replacement}`",
                        color=0xC4A46D
                    )
                    embed.add_field(name="Original Name", value=display or "[empty]", inline=True)
                    await channel.send(embed=embed)
        except discord.Forbidden:
            pass
        except Exception as e:
            log.error(f"Modnick error: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = await get_config(member.guild.id)
        if not is_plugin_enabled(config, "modnick"):
            return
        plugin_cfg = get_plugin_config(config, "modnick")
        if (plugin_cfg.get("config", {}) or {}).get("rename_on_join", True):
            await self._check_and_rename(member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.display_name == after.display_name:
            return
        config = await get_config(after.guild.id)
        if not is_plugin_enabled(config, "modnick"):
            return
        plugin_cfg = get_plugin_config(config, "modnick")
        if (plugin_cfg.get("config", {}) or {}).get("rename_on_update", True):
            await self._check_and_rename(after)


async def setup(bot):
    await bot.add_cog(ModnickCog(bot))
