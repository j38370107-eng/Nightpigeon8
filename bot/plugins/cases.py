import discord
from discord.ext import commands
from datetime import timezone
import logging
from bot.core.config_loader import get_config, get_plugin_config
from bot.core.level_check import get_user_level
from bot.core.database import get_pool
from bot.core.message_formatter import send_message

log = logging.getLogger("bot.cases")


class CasesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_level(self, ctx, level: int) -> bool:
        user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
        if user_level < level:
            config = await get_config(ctx.guild.id)
            await send_message(ctx, config, "moderation", "no_permission")
            return False
        return True

    @commands.command(name="case")
    @commands.guild_only()
    async def case(self, ctx, case_id: int):
        config = await get_config(ctx.guild.id)
        plugin_cfg = get_plugin_config(config, "cases")
        required_level = (plugin_cfg.get("config", {}) or {}).get("required_level", 25)
        if not await self._check_level(ctx, required_level):
            return

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM cases WHERE guild_id=$1 AND case_number=$2",
                ctx.guild.id, case_id
            )

        if not row:
            return await send_message(ctx, config, "moderation", "case_not_found", case=case_id)

        embed = discord.Embed(
            title=f"Case #{row['case_number']} — {row['action'].title()}",
            color=0x6D78C4,
        )
        embed.add_field(name="User", value=f"{row['user_tag']} (`{row['user_id']}`)", inline=True)
        embed.add_field(name="Moderator", value=row["moderator_tag"], inline=True)
        embed.add_field(name="Reason", value=row["reason"] or "No reason", inline=False)
        if row["duration"]:
            embed.add_field(name="Duration", value=row["duration"], inline=True)
        if row["created_at"]:
            embed.add_field(name="Date", value=f"<t:{int(row['created_at'].replace(tzinfo=timezone.utc).timestamp())}:f>", inline=True)
        embed.add_field(name="Active", value="Yes" if row["active"] else "No (deleted)", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="cases")
    @commands.guild_only()
    async def cases(self, ctx, user: discord.Member):
        config = await get_config(ctx.guild.id)
        plugin_cfg = get_plugin_config(config, "cases")
        cfg = plugin_cfg.get("config", {}) or {}
        required_level = cfg.get("required_level", 25)
        per_page = cfg.get("cases_per_page", 5)

        if not await self._check_level(ctx, required_level):
            return

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM cases WHERE guild_id=$1 AND user_id=$2 AND active=TRUE ORDER BY case_number DESC",
                ctx.guild.id, user.id
            )

        if not rows:
            return await ctx.send(f"No active cases found for {user}.")

        pages = [rows[i:i+per_page] for i in range(0, len(rows), per_page)]
        page = 0

        def make_embed(p):
            embed = discord.Embed(
                title=f"Cases for {user} ({len(rows)} total)",
                color=0x6D78C4,
            )
            for row in pages[p]:
                dur = f" | {row['duration']}" if row["duration"] else ""
                embed.add_field(
                    name=f"Case #{row['case_number']} — {row['action'].title()}{dur}",
                    value=f"Reason: {row['reason']}\nMod: {row['moderator_tag']}",
                    inline=False
                )
            embed.set_footer(text=f"Page {p+1}/{len(pages)}")
            return embed

        msg = await ctx.send(embed=make_embed(0))
        if len(pages) <= 1:
            return

        await msg.add_reaction("◀")
        await msg.add_reaction("▶")

        def check(r, u):
            return u == ctx.author and str(r.emoji) in ("◀", "▶") and r.message.id == msg.id

        import asyncio
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

    @commands.command(name="servercases")
    @commands.guild_only()
    async def servercases(self, ctx):
        config = await get_config(ctx.guild.id)
        plugin_cfg = get_plugin_config(config, "cases")
        required_level = (plugin_cfg.get("config", {}) or {}).get("required_level", 25)

        if not await self._check_level(ctx, required_level):
            return

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM cases WHERE guild_id=$1 AND active=TRUE ORDER BY case_number DESC LIMIT 50",
                ctx.guild.id
            )

        if not rows:
            return await ctx.send("No cases found for this server.")

        pages = [rows[i:i+10] for i in range(0, len(rows), 10)]
        page = 0

        def make_embed(p):
            embed = discord.Embed(title=f"Server Cases ({len(rows)} total)", color=0x6D78C4)
            for row in pages[p]:
                embed.add_field(
                    name=f"#{row['case_number']} — {row['action'].title()} | {row['user_tag']}",
                    value=f"Reason: {row['reason'][:80]} | Mod: {row['moderator_tag']}",
                    inline=False
                )
            embed.set_footer(text=f"Page {p+1}/{len(pages)}")
            return embed

        msg = await ctx.send(embed=make_embed(0))
        if len(pages) <= 1:
            return

        await msg.add_reaction("◀")
        await msg.add_reaction("▶")

        def check(r, u):
            return u == ctx.author and str(r.emoji) in ("◀", "▶") and r.message.id == msg.id

        import asyncio
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
    await bot.add_cog(CasesCog(bot))
