import discord
from discord.ext import commands
import yaml
import logging
from bot.core.config_loader import get_config, get_config_text, save_config
from bot.core.level_check import get_user_level
from bot.core.message_formatter import send_message

log = logging.getLogger("bot.levels")


class LevelsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="level")
    @commands.guild_only()
    async def level(self, ctx, user: discord.Member = None):
        target = user or ctx.author
        level = await get_user_level(ctx.guild.id, target.id, target)
        level_str = str(level)
        embed = discord.Embed(
            title=f"Level for {target}",
            description=f"**Level:** {level_str}",
            color=0x6D78C4
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="levels")
    @commands.guild_only()
    async def levels(self, ctx):
        config = await get_config(ctx.guild.id)
        levels_config = config.get("levels", {})

        if not levels_config:
            return await ctx.send("No levels configured for this server.")

        embed = discord.Embed(title="Server Levels", color=0x6D78C4)

        users = levels_config.get("users", {}) or {}
        if users:
            user_lines = []
            for uid, lvl in sorted(users.items(), key=lambda x: -x[1]):
                member = ctx.guild.get_member(int(uid))
                name = str(member) if member else f"<@{uid}>"
                user_lines.append(f"`{lvl}` — {name}")
            embed.add_field(name="Users", value="\n".join(user_lines[:20]) or "None", inline=False)

        roles = levels_config.get("roles", {}) or {}
        if roles:
            role_lines = []
            for rid, lvl in sorted(roles.items(), key=lambda x: -x[1]):
                role = ctx.guild.get_role(int(rid))
                name = role.mention if role else f"<@&{rid}>"
                role_lines.append(f"`{lvl}` — {name}")
            embed.add_field(name="Roles", value="\n".join(role_lines[:20]) or "None", inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="levelset")
    @commands.guild_only()
    async def levelset(self, ctx, user: discord.Member, level: int):
        invoker_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
        if invoker_level < 1:
            return await ctx.send("You need at least level 1 to set levels.")

        if level < 0:
            return await ctx.send("Level must be 0 or higher.")

        config_text = await get_config_text(ctx.guild.id)
        try:
            config = yaml.safe_load(config_text) or {}
        except Exception:
            config = {}

        if "levels" not in config:
            config["levels"] = {"users": {}, "roles": {}}
        if "users" not in config["levels"]:
            config["levels"]["users"] = {}

        config["levels"]["users"][str(user.id)] = level
        new_text = yaml.dump(config, default_flow_style=False, allow_unicode=True)
        await save_config(ctx.guild.id, new_text)
        await ctx.send(f"Set level {level} for {user}.")


async def setup(bot):
    await bot.add_cog(LevelsCog(bot))
