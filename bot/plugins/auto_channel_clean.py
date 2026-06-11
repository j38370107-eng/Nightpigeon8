import discord
from discord.ext import commands
from discord.ext import tasks
from datetime import datetime, timezone, timedelta
import logging
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled
from bot.core.database import get_pool

log = logging.getLogger("bot.auto_channel_clean")


class AutoChannelCleanCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.clean_loop.start()

    def cog_unload(self):
        self.clean_loop.cancel()

    @tasks.loop(seconds=60)
    async def clean_loop(self):
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM auto_channel_clean")

        now = datetime.now(timezone.utc)
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                continue
            config = await get_config(guild.id)
            if not is_plugin_enabled(config, "auto_channel_clean"):
                continue

            plugin_cfg = get_plugin_config(config, "auto_channel_clean")
            channels_cfg = plugin_cfg.get("channels", []) or []

            channel_cfg = next((c for c in channels_cfg if int(c.get("channel", 0)) == row["channel_id"]), None)
            if not channel_cfg:
                continue

            last_cleaned = row["last_cleaned"]
            if last_cleaned.tzinfo is None:
                last_cleaned = last_cleaned.replace(tzinfo=timezone.utc)

            interval = row["interval_seconds"]
            if (now - last_cleaned).total_seconds() < interval:
                continue

            channel = guild.get_channel(row["channel_id"])
            if not channel:
                continue

            keep_pinned = channel_cfg.get("keep_pinned", True)
            delete_older_than = channel_cfg.get("delete_older_than")

            def check(msg):
                if keep_pinned and msg.pinned:
                    return False
                if delete_older_than:
                    cutoff = now - timedelta(seconds=delete_older_than)
                    if msg.created_at > cutoff:
                        return False
                return True

            try:
                deleted = await channel.purge(limit=100, check=check,
                                              before=discord.Object(id=discord.utils.time_snowflake(now - timedelta(seconds=1))))
                log.info(f"Auto-cleaned {len(deleted)} messages in #{channel.name} ({guild.name})")
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE auto_channel_clean SET last_cleaned=NOW() WHERE guild_id=$1 AND channel_id=$2",
                        guild.id, channel.id
                    )
            except Exception as e:
                log.error(f"Auto channel clean error: {e}")

    @clean_loop.before_loop
    async def before_clean_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(AutoChannelCleanCog(bot))
