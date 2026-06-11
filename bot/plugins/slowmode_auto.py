import discord
from discord.ext import commands
from collections import defaultdict, deque
from datetime import datetime, timezone
import asyncio
import logging
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled

log = logging.getLogger("bot.slowmode_auto")

_msg_times: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))
_slowmode_active: dict[int, dict[int, asyncio.Task]] = defaultdict(dict)


class SlowmodeAutoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        config = await get_config(message.guild.id)
        if not is_plugin_enabled(config, "slowmode_auto"):
            return

        plugin_cfg = get_plugin_config(config, "slowmode_auto")
        ignore_roles = [int(r) for r in (plugin_cfg.get("ignore_roles", []) or [])]
        ignore_channels = [int(c) for c in (plugin_cfg.get("ignore_channels", []) or [])]
        rules = plugin_cfg.get("rules", []) or []

        if message.channel.id in ignore_channels:
            return
        member_roles = [r.id for r in message.author.roles]
        if any(r in member_roles for r in ignore_roles):
            return

        now = message.created_at.timestamp()

        for rule in rules:
            rule_channel = rule.get("channel")
            if rule_channel and int(rule_channel) != message.channel.id:
                continue

            msgs_per_secs = rule.get("messages_per_seconds", 10)
            window = rule.get("window_seconds", 5)
            apply_slowmode = rule.get("apply_slowmode", 3)
            remove_after = rule.get("remove_after_seconds", 30)

            cache = _msg_times[message.guild.id][message.channel.id]
            cache.append(now)
            while cache and cache[0] < now - window:
                cache.popleft()

            if len(cache) >= msgs_per_secs:
                channel = message.channel
                if isinstance(channel, discord.TextChannel) and channel.slowmode_delay != apply_slowmode:
                    try:
                        await channel.edit(slowmode_delay=apply_slowmode)
                        log.info(f"Applied {apply_slowmode}s slowmode to #{channel.name}")
                    except Exception:
                        pass

                    task_key = (message.guild.id, channel.id)
                    if task_key in _slowmode_active.get(message.guild.id, {}):
                        _slowmode_active[message.guild.id][channel.id].cancel()

                    async def remove_slowmode(ch, delay):
                        await asyncio.sleep(delay)
                        try:
                            await ch.edit(slowmode_delay=0)
                            log.info(f"Removed slowmode from #{ch.name}")
                        except Exception:
                            pass

                    task = asyncio.create_task(remove_slowmode(channel, remove_after))
                    _slowmode_active[message.guild.id][channel.id] = task
                break


async def setup(bot):
    await bot.add_cog(SlowmodeAutoCog(bot))
