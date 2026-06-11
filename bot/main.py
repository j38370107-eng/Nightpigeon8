import discord
from discord.ext import commands
import os
import asyncio
import logging
from pathlib import Path
from bot.config_manager import ConfigManager
from bot.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")


class ModerationBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=self._get_prefix,
            intents=intents,
            case_insensitive=True,
            help_command=None,
        )
        self.config_manager = ConfigManager()
        self.db: Database = None

    async def _get_prefix(self, bot, message: discord.Message):
        if not message.guild:
            return "!"
        cfg = self.config_manager.get(message.guild.id)
        return cfg.get("prefix", "!")

    async def setup_hook(self):
        self.db = Database()
        await self.db.init()

        cog_modules = [
            "bot.cogs.moderation",
            "bot.cogs.automod",
            "bot.cogs.logging",
            "bot.cogs.config",
            "bot.cogs.info",
            "bot.cogs.utility",
        ]
        for module in cog_modules:
            try:
                await self.load_extension(module)
                log.info(f"Loaded cog: {module}")
            except Exception as e:
                log.error(f"Failed to load cog {module}: {e}")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        log.info(f"Serving {len(self.guilds)} guild(s)")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers | !help",
            )
        )

    async def on_guild_join(self, guild: discord.Guild):
        self.config_manager.init_guild(guild.id)
        log.info(f"Joined guild: {guild.name} ({guild.id})")

    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                embed=discord.Embed(
                    description="❌ You don't have permission to use this command.",
                    color=discord.Color.red(),
                )
            )
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send(
                embed=discord.Embed(
                    description=f"❌ I'm missing permissions: `{', '.join(error.missing_permissions)}`",
                    color=discord.Color.red(),
                )
            )
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(
                embed=discord.Embed(
                    description="❌ Member not found.",
                    color=discord.Color.red(),
                )
            )
        elif isinstance(error, commands.BadArgument):
            await ctx.send(
                embed=discord.Embed(
                    description=f"❌ Bad argument: {error}",
                    color=discord.Color.red(),
                )
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                embed=discord.Embed(
                    description=f"❌ Missing argument: `{error.param.name}`",
                    color=discord.Color.red(),
                )
            )
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(
                embed=discord.Embed(
                    description="❌ You don't have permission to use this command.",
                    color=discord.Color.red(),
                )
            )
        else:
            log.error(f"Unhandled error in command {ctx.command}: {error}", exc_info=error)
            await ctx.send(
                embed=discord.Embed(
                    description=f"❌ An unexpected error occurred.",
                    color=discord.Color.red(),
                )
            )


async def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        log.error("DISCORD_TOKEN environment variable not set!")
        return

    bot = ModerationBot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
