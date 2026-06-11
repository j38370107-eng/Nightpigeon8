import discord
from discord.ext import commands
import asyncio
import logging
from bot.core.config_loader import get_config, get_plugin_config
from bot.core.level_check import get_user_level
from bot.core.database import get_pool, create_case
from bot.core.message_formatter import send_message

log = logging.getLogger("bot.notes")


async def _check_level(ctx, level: int) -> bool:
    user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
    if user_level < level:
        config = await get_config(ctx.guild.id)
        await send_message(ctx, config, "moderation", "no_permission")
        return False
    return True


class NotesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_level(self, config, cmd, default=25):
        plugin_cfg = get_plugin_config(config, "notes")
        return ((plugin_cfg.get("config", {}) or {}).get("levels", {}) or {}).get(cmd, default)

    @commands.command(name="note")
    @commands.guild_only()
    async def note(self, ctx, user: discord.Member, *, text: str):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_level(config, "note", 25)):
            return
        case = await create_case(ctx.guild.id, user.id, str(user),
                                  ctx.author.id, str(ctx.author), "note", text)
        await send_message(ctx, config, "moderation", "note_reply",
                           user=str(user), case=case["case_number"])

    @commands.command(name="viewnote")
    @commands.guild_only()
    async def viewnote(self, ctx, case_id: int):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_level(config, "viewnote", 25)):
            return
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM cases WHERE guild_id=$1 AND case_number=$2 AND action='note'",
                ctx.guild.id, case_id
            )
        if not row:
            return await ctx.send(f"Note case #{case_id} not found.")
        embed = discord.Embed(title=f"Note #{row['case_number']}", color=0x6D78C4)
        embed.add_field(name="User", value=f"{row['user_tag']} (`{row['user_id']}`)", inline=True)
        embed.add_field(name="Moderator", value=row["moderator_tag"], inline=True)
        embed.add_field(name="Note", value=row["reason"], inline=False)
        from datetime import timezone
        if row["created_at"]:
            embed.add_field(name="Date", value=f"<t:{int(row['created_at'].replace(tzinfo=timezone.utc).timestamp())}:R>", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="viewnotes")
    @commands.guild_only()
    async def viewnotes(self, ctx, user: discord.Member):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_level(config, "viewnotes", 25)):
            return
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM cases WHERE guild_id=$1 AND user_id=$2 AND action='note' AND active=TRUE ORDER BY case_number DESC",
                ctx.guild.id, user.id
            )
        if not rows:
            return await ctx.send(f"No notes found for {user}.")

        pages = [rows[i:i+5] for i in range(0, len(rows), 5)]
        page = 0

        def make_embed(p):
            embed = discord.Embed(title=f"Notes for {user} ({len(rows)} total)", color=0x6D78C4)
            for row in pages[p]:
                embed.add_field(
                    name=f"Note #{row['case_number']} by {row['moderator_tag']}",
                    value=row["reason"][:200],
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

    @commands.command(name="deletenote")
    @commands.guild_only()
    async def deletenote(self, ctx, case_id: int):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_level(config, "deletenote", 50)):
            return
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM cases WHERE guild_id=$1 AND case_number=$2 AND action='note'",
                ctx.guild.id, case_id
            )
            if not row:
                return await ctx.send(f"Note #{case_id} not found.")
            await conn.execute("UPDATE cases SET active=FALSE WHERE id=$1", row["id"])
        await ctx.send(f"Note #{case_id} deleted.")

    @commands.command(name="notesearch")
    @commands.guild_only()
    async def notesearch(self, ctx, user: discord.Member, *, search_term: str):
        config = await get_config(ctx.guild.id)
        if not await _check_level(ctx, self._get_level(config, "notesearch", 25)):
            return
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM cases WHERE guild_id=$1 AND user_id=$2 AND action='note' AND active=TRUE AND LOWER(reason) LIKE $3",
                ctx.guild.id, user.id, f"%{search_term.lower()}%"
            )
        if not rows:
            return await ctx.send(f"No notes found containing `{search_term}`.")
        embed = discord.Embed(title=f"Notes matching '{search_term}' for {user}", color=0x6D78C4)
        for row in rows[:10]:
            embed.add_field(
                name=f"Note #{row['case_number']}",
                value=row["reason"][:200],
                inline=False
            )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(NotesCog(bot))
