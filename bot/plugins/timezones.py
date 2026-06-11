import discord
from discord.ext import commands
from datetime import datetime
import pytz
import logging
import asyncio
from bot.core.config_loader import get_config, get_plugin_config
from bot.core.database import get_pool

log = logging.getLogger("bot.timezones")


class TimezonesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="timezone", invoke_without_command=True)
    @commands.guild_only()
    async def timezone(self, ctx):
        await ctx.send("Usage: `!timezone set <timezone>` | `!timezone get [@user]` | `!timezone list` | `!timezone convert <time> from <tz> to <tz>`")

    @timezone.command(name="set")
    async def tz_set(self, ctx, timezone_str: str):
        if timezone_str not in pytz.all_timezones:
            similar = [tz for tz in pytz.all_timezones if timezone_str.lower() in tz.lower()][:5]
            msg = f"Invalid timezone `{timezone_str}`."
            if similar:
                msg += f" Did you mean: {', '.join(similar)}?"
            return await ctx.send(msg)

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_timezones (user_id, timezone) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET timezone=$2",
                ctx.author.id, timezone_str
            )
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz).strftime("%H:%M %Z")
        await ctx.send(f"Your timezone has been set to **{timezone_str}** (current time: {now})")

    @timezone.command(name="get")
    async def tz_get(self, ctx, user: discord.Member = None):
        target = user or ctx.author
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT timezone FROM user_timezones WHERE user_id=$1", target.id
            )
        if not row:
            return await ctx.send(f"{target} has not set a timezone.")
        tz = pytz.timezone(row["timezone"])
        now = datetime.now(tz).strftime("%H:%M:%S %Z, %A %B %d %Y")
        await ctx.send(f"**{target}**'s timezone: **{row['timezone']}** — Current time: {now}")

    @timezone.command(name="list")
    async def tz_list(self, ctx):
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, timezone FROM user_timezones"
            )

        if not rows:
            return await ctx.send("No timezones have been set.")

        guild_rows = [(r["user_id"], r["timezone"]) for r in rows
                      if ctx.guild.get_member(r["user_id"])]

        if not guild_rows:
            return await ctx.send("No members in this server have set timezones.")

        pages = [guild_rows[i:i+10] for i in range(0, len(guild_rows), 10)]
        page = 0

        def make_embed(p):
            embed = discord.Embed(title="Member Timezones", color=0x6D78C4)
            for uid, tz_str in pages[p]:
                member = ctx.guild.get_member(uid)
                if member:
                    try:
                        tz = pytz.timezone(tz_str)
                        now = datetime.now(tz).strftime("%H:%M %Z")
                        embed.add_field(name=str(member), value=f"{tz_str} ({now})", inline=True)
                    except Exception:
                        pass
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

    @timezone.command(name="convert")
    async def tz_convert(self, ctx, time_str: str, _from: str, from_tz: str, _to: str, to_tz: str):
        try:
            from_zone = pytz.timezone(from_tz)
            to_zone = pytz.timezone(to_tz)
        except Exception:
            return await ctx.send("Invalid timezone(s).")
        try:
            from dateutil import parser as dateparser
            naive = dateparser.parse(time_str)
            if not naive:
                raise ValueError()
            localized = from_zone.localize(naive)
            converted = localized.astimezone(to_zone)
            result = converted.strftime("%H:%M:%S %Z, %A %B %d %Y")
            await ctx.send(f"`{time_str}` in **{from_tz}** → **{result}** in **{to_tz}**")
        except Exception:
            await ctx.send("Could not parse time. Use format like `14:30` or `2:30pm`.")


async def setup(bot):
    await bot.add_cog(TimezonesCog(bot))
