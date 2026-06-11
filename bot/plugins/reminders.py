import discord
from discord.ext import commands
from discord.ext import tasks
from datetime import datetime, timezone
import asyncio
import logging
from bot.core.config_loader import get_config, get_plugin_config
from bot.core.duration import parse_duration
from bot.core.database import get_pool

log = logging.getLogger("bot.reminders")


class RemindersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    @tasks.loop(seconds=30)
    async def reminder_loop(self):
        pool = await get_pool()
        now = datetime.now(timezone.utc)
        now_naive = datetime.utcnow()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM reminders WHERE remind_at <= $1", now_naive
            )
            if rows:
                await conn.execute(
                    "DELETE FROM reminders WHERE remind_at <= $1", now_naive
                )

        for row in rows:
            user = self.bot.get_user(row["user_id"])
            if not user:
                try:
                    user = await self.bot.fetch_user(row["user_id"])
                except Exception:
                    continue

            embed = discord.Embed(
                title="⏰ Reminder",
                description=row["message"],
                color=0x6D78C4,
                timestamp=now
            )
            embed.set_footer(text="Set reminder")
            try:
                await user.send(embed=embed)
            except Exception:
                if row["channel_id"]:
                    channel = self.bot.get_channel(row["channel_id"])
                    if channel:
                        try:
                            await channel.send(f"{user.mention} ⏰ **Reminder:** {row['message']}")
                        except Exception:
                            pass

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

    @commands.group(name="remind", invoke_without_command=True)
    @commands.guild_only()
    async def remind(self, ctx, target: str = None, duration: str = None, *, message: str = None):
        if target == "me" and duration and message:
            try:
                td = parse_duration(duration)
            except ValueError as e:
                return await ctx.send(str(e))

            if td is None:
                return await ctx.send("Cannot set a permanent reminder.")

            remind_at = datetime.now(timezone.utc) + td
            pool = await get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """INSERT INTO reminders (user_id, guild_id, channel_id, message, remind_at)
                       VALUES ($1,$2,$3,$4,$5) RETURNING id""",
                    ctx.author.id, ctx.guild.id, ctx.channel.id, message, remind_at
                )

            from bot.core.duration import format_duration
            await ctx.send(f"⏰ Reminder set! I'll remind you in **{format_duration(td)}** (ID: {row['id']})")
        else:
            await ctx.send("Usage: `!remind me <duration> <message>`\nExample: `!remind me 1h Do the thing`")

    @remind.command(name="list")
    async def remind_list(self, ctx):
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM reminders WHERE user_id=$1 ORDER BY remind_at ASC",
                ctx.author.id
            )
        if not rows:
            return await ctx.send("You have no pending reminders.")

        embed = discord.Embed(title="Your Reminders", color=0x6D78C4)
        for row in rows[:10]:
            ts = int(row["remind_at"].replace(tzinfo=timezone.utc).timestamp()) if row["remind_at"].tzinfo is None else int(row["remind_at"].timestamp())
            embed.add_field(
                name=f"ID: {row['id']} — <t:{ts}:R>",
                value=row["message"][:100],
                inline=False
            )
        await ctx.send(embed=embed)

    @remind.command(name="cancel")
    async def remind_cancel(self, ctx, reminder_id: int):
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM reminders WHERE id=$1 AND user_id=$2",
                reminder_id, ctx.author.id
            )
        if result == "DELETE 1":
            await ctx.send(f"Reminder {reminder_id} cancelled.")
        else:
            await ctx.send(f"Reminder {reminder_id} not found.")


async def setup(bot):
    await bot.add_cog(RemindersCog(bot))
