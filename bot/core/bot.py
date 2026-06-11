import discord
from discord.ext import commands
import logging
from pathlib import Path
from bot.core.database import init_db
from bot.core.config_loader import get_prefix, get_config, ensure_guild

log = logging.getLogger("bot")

PLUGINS = [
    "bot.plugins.moderation",
    "bot.plugins.mass_actions",
    "bot.plugins.cases",
    "bot.plugins.levels",
    "bot.plugins.logging_plugin",
    "bot.plugins.automod",
    "bot.plugins.escalation",
    "bot.plugins.command_aliases",
    "bot.plugins.preset_reasons",
    "bot.plugins.utility",
    "bot.plugins.welcome",
    "bot.plugins.notes",
    "bot.plugins.roles",
    "bot.plugins.starboard",
    "bot.plugins.timezones",
    "bot.plugins.reaction_roles",
    "bot.plugins.tickets",
    "bot.plugins.autoreply",
    "bot.plugins.auto_reactions",
    "bot.plugins.auto_channel_clean",
    "bot.plugins.slowmode_auto",
    "bot.plugins.lockdown",
    "bot.plugins.modnick",
    "bot.plugins.history",
    "bot.plugins.reminders",
]


async def _get_prefix(bot, message):
    if not message.guild:
        return "!"
    try:
        config = await get_config(message.guild.id)
        return get_prefix(config)
    except Exception:
        return "!"


class NightpigeonBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=_get_prefix,
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        await init_db()
        for plugin in PLUGINS:
            try:
                await self.load_extension(plugin)
                log.info(f"Loaded plugin: {plugin}")
            except Exception as e:
                log.error(f"Failed to load plugin {plugin}: {e}", exc_info=True)

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        log.info(f"Serving {len(self.guilds)} guild(s)")
        for guild in self.guilds:
            await ensure_guild(guild.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers",
            )
        )

    async def on_guild_join(self, guild: discord.Guild):
        await ensure_guild(guild.id)
        log.info(f"Joined guild: {guild.name} ({guild.id})")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument: `{error.param.name}`")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"Bad argument: {error}")
            return
        log.error(f"Unhandled command error in {ctx.command}: {error}", exc_info=error)
