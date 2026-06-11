import discord
from discord.ext import commands
import re
import logging
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled
from bot.core.level_check import get_user_level
from bot.core.database import get_pool

log = logging.getLogger("bot.auto_reactions")


class AutoReactionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        config = await get_config(message.guild.id)
        if not is_plugin_enabled(config, "autoreply"):
            return

        pool = await get_pool()
        async with pool.acquire() as conn:
            rules = await conn.fetch("SELECT * FROM auto_reactions WHERE guild_id=$1", message.guild.id)

        for rule in rules:
            content_lower = message.content.lower()
            trigger = rule["trigger"].lower()
            trigger_type = rule["trigger_type"]

            matched = False
            if trigger_type == "contains":
                matched = trigger in content_lower
            elif trigger_type == "exact":
                matched = trigger == content_lower
            elif trigger_type == "startswith":
                matched = content_lower.startswith(trigger)
            elif trigger_type == "endswith":
                matched = content_lower.endswith(trigger)
            elif trigger_type == "regex":
                try:
                    matched = bool(re.search(rule["trigger"], message.content, re.IGNORECASE))
                except Exception:
                    pass

            if not matched:
                continue

            ignore_channels = rule["ignore_channels"] or []
            required_channels = rule["required_channels"] or []
            if message.channel.id in [int(c) for c in ignore_channels]:
                continue
            if required_channels and message.channel.id not in [int(c) for c in required_channels]:
                continue

            for emoji in rule["emojis"] or []:
                try:
                    await message.add_reaction(emoji)
                except Exception:
                    pass

    @commands.group(name="autoreaction", invoke_without_command=True)
    @commands.guild_only()
    async def autoreaction(self, ctx):
        await ctx.send("Usage: `autoreaction add <trigger> | <emoji1> [emoji2...]` | `autoreaction list` | `autoreaction delete <id>`")

    @autoreaction.command(name="add")
    async def ar_add(self, ctx, *, args: str):
        if " | " not in args:
            return await ctx.send("Use format: `<trigger> | <emoji1> [emoji2...]`")
        trigger, emojis_str = args.split(" | ", 1)
        emojis = emojis_str.strip().split()
        if not emojis:
            return await ctx.send("Provide at least one emoji.")

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO auto_reactions (guild_id,trigger,emojis) VALUES ($1,$2,$3) RETURNING id",
                ctx.guild.id, trigger.strip(), emojis
            )
        await ctx.send(f"Auto-reaction added (ID: {row['id']})")

    @autoreaction.command(name="list")
    async def ar_list(self, ctx):
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM auto_reactions WHERE guild_id=$1 ORDER BY id", ctx.guild.id)
        if not rows:
            return await ctx.send("No auto-reaction rules set.")
        lines = [f"`{r['id']}` `{r['trigger'][:30]}` → {' '.join(r['emojis'][:5])}" for r in rows[:20]]
        await ctx.send("\n".join(lines))

    @autoreaction.command(name="delete")
    async def ar_delete(self, ctx, rule_id: int):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM auto_reactions WHERE id=$1 AND guild_id=$2", rule_id, ctx.guild.id)
        await ctx.send(f"Rule {rule_id} deleted.")


async def setup(bot):
    await bot.add_cog(AutoReactionsCog(bot))
