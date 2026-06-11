import discord
from discord.ext import commands
import re
import asyncio
import logging
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled
from bot.core.level_check import get_user_level
from bot.core.database import get_pool

log = logging.getLogger("bot.autoreply")


def _matches(trigger: str, trigger_type: str, content: str, match_case: bool) -> bool:
    if not match_case:
        trigger = trigger.lower()
        content = content.lower()
    if trigger_type == "contains":
        return trigger in content
    elif trigger_type == "exact":
        return trigger == content
    elif trigger_type == "startswith":
        return content.startswith(trigger)
    elif trigger_type == "endswith":
        return content.endswith(trigger)
    elif trigger_type == "regex":
        flags = 0 if match_case else re.IGNORECASE
        try:
            return bool(re.search(trigger, content, flags))
        except re.error:
            return False
    return False


class AutoReplyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_level(self, ctx, level: int) -> bool:
        user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
        return user_level >= level

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        config = await get_config(message.guild.id)
        if not is_plugin_enabled(config, "autoreply"):
            return

        pool = await get_pool()
        async with pool.acquire() as conn:
            rules = await conn.fetch(
                "SELECT * FROM auto_replies WHERE guild_id=$1",
                message.guild.id
            )

        for rule in rules:
            if not _matches(rule["trigger"], rule["trigger_type"], message.content, rule["match_case"]):
                continue

            ignore_roles = rule["ignore_roles"] or []
            required_roles = rule["required_roles"] or []
            ignore_channels = rule["ignore_channels"] or []
            required_channels = rule["required_channels"] or []

            member_role_ids = [r.id for r in message.author.roles]
            if any(int(r) in member_role_ids for r in ignore_roles):
                continue
            if required_roles and not any(int(r) in member_role_ids for r in required_roles):
                continue
            if message.channel.id in [int(c) for c in ignore_channels]:
                continue
            if required_channels and message.channel.id not in [int(c) for c in required_channels]:
                continue

            if rule["delete_trigger"]:
                try:
                    await message.delete()
                except Exception:
                    pass

            reply_type = rule["reply_type"]
            response = rule["response"]
            delete_after = rule["delete_after"]

            try:
                if reply_type == "dm":
                    sent = await message.author.send(response)
                elif reply_type == "reply":
                    sent = await message.reply(response)
                else:
                    sent = await message.channel.send(response)

                if delete_after and sent:
                    await asyncio.sleep(delete_after)
                    try:
                        await sent.delete()
                    except Exception:
                        pass
            except Exception as e:
                log.error(f"Autoreply error: {e}")
            break

    @commands.group(name="autoreply", invoke_without_command=True)
    @commands.guild_only()
    async def autoreply(self, ctx):
        await ctx.send("Usage: `autoreply add <type> <trigger> | <response>` | `autoreply list` | `autoreply delete <id>` | `autoreply test <message>`")

    @autoreply.command(name="add")
    async def autoreply_add(self, ctx, trigger_type: str, *, args: str):
        config = await get_config(ctx.guild.id)
        plugin_cfg = get_plugin_config(config, "autoreply")
        required_level = (plugin_cfg.get("config", {}) or {}).get("required_level", 50)
        if not await self._check_level(ctx, required_level):
            return await ctx.send("You don't have permission.")

        valid_types = ["contains", "exact", "startswith", "endswith", "regex"]
        if trigger_type not in valid_types:
            return await ctx.send(f"Invalid type. Choose from: {', '.join(valid_types)}")

        if " | " not in args:
            return await ctx.send("Use format: `<trigger> | <response>`")

        trigger, response = args.split(" | ", 1)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO auto_replies (guild_id,trigger,response,trigger_type) VALUES ($1,$2,$3,$4) RETURNING id",
                ctx.guild.id, trigger.strip(), response.strip(), trigger_type
            )
        await ctx.send(f"Auto-reply added (ID: {row['id']}). Trigger: `{trigger.strip()}`")

    @autoreply.command(name="list")
    async def autoreply_list(self, ctx):
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM auto_replies WHERE guild_id=$1 ORDER BY id", ctx.guild.id)
        if not rows:
            return await ctx.send("No auto-reply rules set.")
        lines = [f"`{r['id']}` [{r['trigger_type']}] `{r['trigger'][:30]}` → `{r['response'][:30]}`" for r in rows[:20]]
        await ctx.send("\n".join(lines))

    @autoreply.command(name="delete")
    async def autoreply_delete(self, ctx, rule_id: int):
        config = await get_config(ctx.guild.id)
        plugin_cfg = get_plugin_config(config, "autoreply")
        required_level = (plugin_cfg.get("config", {}) or {}).get("required_level", 50)
        if not await self._check_level(ctx, required_level):
            return await ctx.send("You don't have permission.")
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM auto_replies WHERE id=$1 AND guild_id=$2", rule_id, ctx.guild.id)
        await ctx.send(f"Rule {rule_id} deleted.")

    @autoreply.command(name="test")
    async def autoreply_test(self, ctx, *, message_text: str):
        pool = await get_pool()
        async with pool.acquire() as conn:
            rules = await conn.fetch("SELECT * FROM auto_replies WHERE guild_id=$1", ctx.guild.id)
        matched = [r for r in rules if _matches(r["trigger"], r["trigger_type"], message_text, r["match_case"])]
        if not matched:
            return await ctx.send("No rules would fire for that message.")
        lines = [f"`{r['id']}` [{r['trigger_type']}] `{r['trigger'][:30]}`" for r in matched]
        await ctx.send(f"Would fire:\n" + "\n".join(lines))


async def setup(bot):
    await bot.add_cog(AutoReplyCog(bot))
