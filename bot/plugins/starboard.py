import discord
from discord.ext import commands
import logging
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled
from bot.core.database import get_pool

log = logging.getLogger("bot.starboard")


class StarboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        config = await get_config(guild.id)
        if not is_plugin_enabled(config, "starboard"):
            return

        plugin_cfg = get_plugin_config(config, "starboard")
        cfg = plugin_cfg.get("config", {}) or {}
        starboard_channel_id = cfg.get("channel")
        threshold = cfg.get("threshold", 3)
        emoji_str = cfg.get("emoji", "⭐")
        self_star = cfg.get("self_star", False)
        ignore_channels = [int(c) for c in (cfg.get("ignore_channels", []) or [])]

        if not starboard_channel_id:
            return

        if payload.channel_id in ignore_channels:
            return

        if str(payload.emoji) != emoji_str and payload.emoji.name != emoji_str:
            return

        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        if not self_star and message.author.id == payload.user_id:
            return

        star_count = 0
        for reaction in message.reactions:
            if str(reaction.emoji) == emoji_str or (hasattr(reaction.emoji, 'name') and reaction.emoji.name == emoji_str):
                star_count = reaction.count
                break

        starboard_channel = guild.get_channel(int(starboard_channel_id))
        if not starboard_channel:
            return

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM starboard_entries WHERE guild_id=$1 AND original_message_id=$2",
                guild.id, message.id
            )

        if star_count >= threshold:
            msg_text = cfg.get("starboard_message", "⭐ {count} | {channel}").format(
                count=star_count, channel=channel.mention
            )
            embed = discord.Embed(description=message.content or "", color=0xFFD700)
            embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
            embed.add_field(name="Jump", value=f"[Click here]({message.jump_url})", inline=True)
            if message.attachments:
                embed.set_image(url=message.attachments[0].url)
            embed.set_footer(text=f"ID: {message.id}")

            async with pool.acquire() as conn:
                if row and row["starboard_message_id"]:
                    try:
                        sb_msg = await starboard_channel.fetch_message(row["starboard_message_id"])
                        await sb_msg.edit(content=msg_text, embed=embed)
                    except Exception:
                        pass
                    await conn.execute(
                        "UPDATE starboard_entries SET star_count=$1 WHERE id=$2",
                        star_count, row["id"]
                    )
                elif not row:
                    sent = await starboard_channel.send(content=msg_text, embed=embed)
                    await conn.execute(
                        """INSERT INTO starboard_entries (guild_id,original_message_id,starboard_message_id,star_count,channel_id,author_id)
                           VALUES ($1,$2,$3,$4,$5,$6)""",
                        guild.id, message.id, sent.id, star_count, channel.id, message.author.id
                    )
        elif row and row["starboard_message_id"]:
            try:
                sb_msg = await starboard_channel.fetch_message(row["starboard_message_id"])
                await sb_msg.delete()
            except Exception:
                pass
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE starboard_entries SET starboard_message_id=NULL, star_count=$1 WHERE id=$2",
                    star_count, row["id"]
                )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self.on_raw_reaction_add(payload)


async def setup(bot):
    await bot.add_cog(StarboardCog(bot))
