import discord
from discord.ext import commands
from datetime import datetime, timedelta
import re
from collections import defaultdict, deque


class SpamTracker:
    def __init__(self):
        self._data: dict[tuple, deque] = defaultdict(lambda: deque())

    def add(self, guild_id: int, user_id: int, timestamp: datetime) -> None:
        self._data[(guild_id, user_id)].append(timestamp)

    def prune(self, guild_id: int, user_id: int, window: int):
        key = (guild_id, user_id)
        cutoff = datetime.utcnow() - timedelta(seconds=window)
        dq = self._data[key]
        while dq and dq[0] < cutoff:
            dq.popleft()

    def count(self, guild_id: int, user_id: int) -> int:
        return len(self._data[(guild_id, user_id)])

    def clear(self, guild_id: int, user_id: int):
        self._data[(guild_id, user_id)].clear()


INVITE_PATTERN = re.compile(
    r"(discord\.gg|discord\.com/invite|discordapp\.com/invite)/[a-zA-Z0-9]+",
    re.IGNORECASE,
)


class AutoMod(commands.Cog):
    """Automatic moderation driven purely by YAML config."""

    def __init__(self, bot):
        self.bot = bot
        self.spam_tracker = SpamTracker()

    def _get_automod_cfg(self, guild_id: int) -> dict:
        cfg = self.bot.config_manager.get(guild_id)
        return cfg.get("plugins", {}).get("automod", {}).get("config", {})

    def _is_immune(self, member: discord.Member) -> bool:
        return (
            member.guild_permissions.manage_messages
            or member.guild_permissions.administrator
        )

    async def _get_mute_role(self, guild: discord.Guild) -> discord.Role | None:
        cfg = self.bot.config_manager.get(guild.id)
        plugins = cfg.get("plugins", {})
        mutes_cfg = plugins.get("mutes", {}).get("config", {})
        role_id = mutes_cfg.get("mute_role")
        if role_id:
            role = guild.get_role(int(role_id))
            if role:
                return role
        return discord.utils.get(guild.roles, name="Muted")

    async def _take_action(self, message: discord.Message, action: str,
                           trigger: str, reason: str, duration: int = None):
        guild = message.guild
        member = message.author

        await self.bot.db.log_automod(
            guild.id, member.id, trigger, action, message.content[:500]
        )

        cfg = self.bot.config_manager.get(guild.id)
        log_channel_id = cfg.get("plugins", {}).get("logs", {}).get("config", {}).get("log_channel")
        if log_channel_id:
            ch = guild.get_channel(int(log_channel_id))
            if ch:
                embed = discord.Embed(
                    title="🤖 AutoMod",
                    color=discord.Color.orange(),
                    timestamp=datetime.utcnow(),
                )
                embed.add_field(name="User", value=f"{member.mention} (`{member}`)", inline=False)
                embed.add_field(name="Trigger", value=trigger, inline=True)
                embed.add_field(name="Action", value=action.title(), inline=True)
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                embed.set_thumbnail(url=member.display_avatar.url)
                try:
                    await ch.send(embed=embed)
                except discord.Forbidden:
                    pass

        if action == "delete":
            try:
                await message.delete()
            except discord.NotFound:
                pass
        elif action == "warn":
            try:
                await message.delete()
            except discord.NotFound:
                pass
            await self.bot.db.add_warning(guild.id, member.id, self.bot.user.id, reason)
        elif action == "mute":
            try:
                await message.delete()
            except discord.NotFound:
                pass
            role = await self._get_mute_role(guild)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"AutoMod: {reason}")
                    expires_at = datetime.utcnow() + timedelta(seconds=duration) if duration else None
                    await self.bot.db.add_mute(guild.id, member.id, expires_at)
                except discord.Forbidden:
                    pass
        elif action == "kick":
            try:
                await message.delete()
            except discord.NotFound:
                pass
            try:
                await member.kick(reason=f"AutoMod: {reason}")
            except discord.Forbidden:
                pass
        elif action == "ban":
            try:
                await message.delete()
            except discord.NotFound:
                pass
            try:
                await guild.ban(member, reason=f"AutoMod: {reason}")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if self._is_immune(message.author):
            return

        cfg = self._get_automod_cfg(message.guild.id)
        if not cfg.get("enabled", False):
            return

        await self._check_spam(message, cfg)
        await self._check_invite(message, cfg)
        await self._check_bad_words(message, cfg)
        await self._check_caps(message, cfg)

    async def _check_spam(self, message: discord.Message, cfg: dict):
        spam_cfg = cfg.get("anti_spam", {})
        if not spam_cfg.get("enabled", False):
            return
        threshold = spam_cfg.get("messages", 5)
        window = spam_cfg.get("seconds", 5)
        action = spam_cfg.get("action", "mute")
        duration = spam_cfg.get("duration", 300)
        gid, uid = message.guild.id, message.author.id
        self.spam_tracker.add(gid, uid, datetime.utcnow())
        self.spam_tracker.prune(gid, uid, window)
        if self.spam_tracker.count(gid, uid) >= threshold:
            self.spam_tracker.clear(gid, uid)
            await self._take_action(
                message, action, "anti_spam",
                f"Sending {threshold}+ messages in {window}s", duration
            )

    async def _check_invite(self, message: discord.Message, cfg: dict):
        invite_cfg = cfg.get("anti_invite", {})
        if not invite_cfg.get("enabled", False):
            return
        if INVITE_PATTERN.search(message.content):
            await self._take_action(
                message, invite_cfg.get("action", "delete"),
                "anti_invite", "Discord invite link"
            )

    async def _check_bad_words(self, message: discord.Message, cfg: dict):
        bw_cfg = cfg.get("bad_words", {})
        if not bw_cfg.get("enabled", False):
            return
        content_lower = message.content.lower()
        for word in bw_cfg.get("words", []):
            if word.lower() in content_lower:
                await self._take_action(
                    message, bw_cfg.get("action", "delete"),
                    "bad_words", "Prohibited word"
                )
                return

    async def _check_caps(self, message: discord.Message, cfg: dict):
        caps_cfg = cfg.get("caps_limit", {})
        if not caps_cfg.get("enabled", False):
            return
        content = message.content
        if len(content) < caps_cfg.get("min_length", 10):
            return
        letters = [c for c in content if c.isalpha()]
        if not letters:
            return
        ratio = sum(1 for c in letters if c.isupper()) / len(letters) * 100
        if ratio >= caps_cfg.get("percent", 70):
            await self._take_action(
                message, caps_cfg.get("action", "warn"),
                "caps_limit", f"Excessive caps ({ratio:.0f}%)"
            )


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
