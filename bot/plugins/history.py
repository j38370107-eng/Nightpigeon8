import discord
from discord.ext import commands
from datetime import timezone
import asyncio
import logging
from bot.core.config_loader import get_config, get_plugin_config
from bot.core.level_check import get_user_level
from bot.core.database import get_pool
from bot.core.message_formatter import send_message

log = logging.getLogger("bot.history")


async def _check_level(ctx, level: int) -> bool:
    user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
    if user_level < level:
        config = await get_config(ctx.guild.id)
        await send_message(ctx, config, "moderation", "no_permission")
        return False
    return True


ACTION_ICONS = {
    "ban": "🔨", "forceban": "🔨", "unban": "🔓", "kick": "👢",
    "mute": "🔇", "unmute": "🔊", "warn": "⚠️", "note": "📝",
    "addcase": "📋"
}


class HistoryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="history")
    @commands.guild_only()
    async def history(self, ctx, user: discord.Member):
        config = await get_config(ctx.guild.id)
        plugin_cfg = get_plugin_config(config, "history")
        required_level = (plugin_cfg.get("config", {}) or {}).get("required_level", 25)
        if not await _check_level(ctx, required_level):
            return

        pool = await get_pool()
        async with pool.acquire() as conn:
            cases = await conn.fetch(
                """SELECT * FROM cases WHERE guild_id=$1 AND user_id=$2
                   ORDER BY created_at ASC""",
                ctx.guild.id, user.id
            )
            automod = await conn.fetch(
                """SELECT rule, hit_count, last_hit FROM automod_hits
                   WHERE guild_id=$1 AND user_id=$2""",
                ctx.guild.id, user.id
            )

        events = []
        for case in cases:
            ts = case["created_at"]
            if ts and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            icon = ACTION_ICONS.get(case["action"], "📌")
            dur = f" ({case['duration']})" if case["duration"] else ""
            active_str = "" if case["active"] else " *(deleted)*"
            events.append((
                ts,
                f"{icon} **Case #{case['case_number']}** — {case['action'].title()}{dur}{active_str}\n"
                f"  Reason: {case['reason']}\n  Mod: {case['moderator_tag']}"
            ))

        if not events:
            return await ctx.send(f"No history found for {user}.")

        per_page = 5
        pages = [events[i:i+per_page] for i in range(0, len(events), per_page)]
        page = 0

        def make_embed(p):
            embed = discord.Embed(
                title=f"History for {user}",
                description=f"{len(events)} total events",
                color=0x6D78C4
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            for ts, text in pages[p]:
                ts_str = f"<t:{int(ts.timestamp())}:R>" if ts else "Unknown"
                embed.add_field(name=ts_str, value=text, inline=False)

            if automod and p == 0:
                am_lines = [f"`{r['rule']}`: {r['hit_count']} hits" for r in automod[:5]]
                embed.add_field(name="Automod Hits", value="\n".join(am_lines), inline=False)

            embed.set_footer(text=f"Page {p+1}/{len(pages)}")
            return embed

        msg = await ctx.send(embed=make_embed(0))
        if len(pages) <= 1:
            return

        await msg.add_reaction("◀")
        await msg.add_reaction("▶")

        def check(r, u):
            return u == ctx.author and str(r.emoji) in ("◀", "▶") and r.message.id == msg.id

        while True:
            try:
                reaction, _ = await self.bot.wait_for("reaction_add", timeout=60, check=check)
                if str(reaction.emoji) == "▶" and page < len(pages) - 1:
                    page += 1
                elif str(reaction.emoji) == "◀" and page > 0:
                    page -= 1
                await msg.edit(embed=make_embed(page))
                try:
                    await msg.remove_reaction(reaction, ctx.author)
                except Exception:
                    pass
            except asyncio.TimeoutError:
                break


async def setup(bot):
    await bot.add_cog(HistoryCog(bot))
