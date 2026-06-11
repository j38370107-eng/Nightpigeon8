import discord
from discord.ext import commands
from datetime import datetime


class Info(commands.Cog):
    """Informational commands: userinfo, serverinfo, roleinfo, avatar."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="userinfo", aliases=["ui", "whois"])
    @commands.guild_only()
    async def userinfo(self, ctx, member: discord.Member = None):
        """Display info about a user: !userinfo @user"""
        member = member or ctx.author
        roles = [r.mention for r in reversed(member.roles) if r != ctx.guild.default_role]

        embed = discord.Embed(
            title=f"👤 {member}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blurple(),
            timestamp=datetime.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(
            name="Account Created",
            value=f"<t:{int(member.created_at.timestamp())}:F>\n(<t:{int(member.created_at.timestamp())}:R>)",
            inline=True,
        )
        if member.joined_at:
            embed.add_field(
                name="Joined Server",
                value=f"<t:{int(member.joined_at.timestamp())}:F>\n(<t:{int(member.joined_at.timestamp())}:R>)",
                inline=True,
            )
        embed.add_field(
            name=f"Roles ({len(roles)})",
            value=" ".join(roles[:10]) + ("..." if len(roles) > 10 else "") if roles else "None",
            inline=False,
        )

        cases = await self.bot.db.get_user_cases(ctx.guild.id, member.id)
        warns = await self.bot.db.get_warnings(ctx.guild.id, member.id)
        embed.add_field(name="Cases", value=str(len(cases)), inline=True)
        embed.add_field(name="Warnings", value=str(len(warns)), inline=True)

        if member.premium_since:
            embed.add_field(
                name="Boosting Since",
                value=f"<t:{int(member.premium_since.timestamp())}:R>",
                inline=True,
            )
        await ctx.send(embed=embed)

    @commands.command(name="serverinfo", aliases=["si", "guildinfo"])
    @commands.guild_only()
    async def serverinfo(self, ctx):
        """Display info about the server."""
        guild = ctx.guild
        embed = discord.Embed(
            title=f"🏰 {guild.name}",
            color=discord.Color.blurple(),
            timestamp=datetime.utcnow(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="ID", value=str(guild.id), inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(
            name="Created",
            value=f"<t:{int(guild.created_at.timestamp())}:R>",
            inline=True,
        )
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Boosts", value=str(guild.premium_subscription_count), inline=True)
        embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier}", inline=True)
        embed.add_field(name="Verification", value=str(guild.verification_level).title(), inline=True)
        bots = sum(1 for m in guild.members if m.bot)
        humans = guild.member_count - bots
        embed.add_field(name="Humans / Bots", value=f"{humans} / {bots}", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="avatar", aliases=["av", "pfp"])
    @commands.guild_only()
    async def avatar(self, ctx, member: discord.Member = None):
        """Display a user's avatar: !avatar @user"""
        member = member or ctx.author
        embed = discord.Embed(title=f"🖼️ {member}'s Avatar", color=discord.Color.blurple())
        embed.set_image(url=member.display_avatar.url)
        formats = []
        for fmt in ["png", "jpg", "webp"]:
            formats.append(f"[{fmt.upper()}]({member.display_avatar.with_format(fmt).url})")
        embed.add_field(name="Download", value=" | ".join(formats))
        await ctx.send(embed=embed)

    @commands.command(name="roleinfo", aliases=["ri"])
    @commands.guild_only()
    async def roleinfo(self, ctx, role: discord.Role):
        """Display info about a role: !roleinfo @role"""
        embed = discord.Embed(
            title=f"🎭 Role: {role.name}",
            color=role.color,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="ID", value=str(role.id), inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No", inline=True)
        embed.add_field(name="Position", value=str(role.position), inline=True)
        embed.add_field(
            name="Created",
            value=f"<t:{int(role.created_at.timestamp())}:R>",
            inline=True,
        )
        key_perms = [
            "administrator", "manage_guild", "manage_roles", "manage_channels",
            "manage_messages", "ban_members", "kick_members", "mention_everyone",
        ]
        active_perms = [p.replace("_", " ").title() for p, v in role.permissions if v and p in key_perms]
        if active_perms:
            embed.add_field(name="Key Permissions", value=", ".join(active_perms), inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Info(bot))
