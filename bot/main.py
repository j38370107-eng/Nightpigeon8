import discord
from discord.ext import commands
import os
import asyncio
import json
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

GUILD_CACHE_PATH = Path("bot/data/guilds.json")


class ModerationBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix="\x00",
            intents=intents,
            help_command=None,
        )
        self.config_manager = ConfigManager()
        self.db: Database = None

    async def setup_hook(self):
        self.db = Database()
        await self.db.init()

        cog_modules = [
            "bot.cogs.automod",
            "bot.cogs.logging",
            "bot.cogs.tasks",
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
        await self._write_guild_cache()
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers",
            )
        )

    async def _write_guild_cache(self):
        GUILD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        guilds = []
        for guild in self.guilds:
            self.config_manager.init_guild(guild.id)
            guilds.append({
                "id": str(guild.id),
                "name": guild.name,
                "icon": str(guild.icon.url) if guild.icon else None,
                "member_count": guild.member_count,
            })
        with open(GUILD_CACHE_PATH, "w") as f:
            json.dump(guilds, f, indent=2)
        log.info(f"Guild cache written ({len(guilds)} guilds)")

    async def on_guild_join(self, guild: discord.Guild):
        self.config_manager.init_guild(guild.id)
        await self._write_guild_cache()
        log.info(f"Joined guild: {guild.name} ({guild.id})")

    async def on_guild_remove(self, guild: discord.Guild):
        await self._write_guild_cache()
        log.info(f"Left guild: {guild.name} ({guild.id})")


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
