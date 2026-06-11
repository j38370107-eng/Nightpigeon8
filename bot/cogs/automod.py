import discord
from discord.ext import commands
from datetime import datetime, timedelta
import re
from collections import defaultdict, deque
from bot.utils import parse_duration, format_duration


class SpamTracker:
    def __init__(self):
        self._data: dict[tuple, deque] = defaultdict(lambda: deque())

    def add(self, guild_id: int, user_id: int, timestamp: datetime) -> list:
        key = (guild_id, user_id)
        self._data[key].append(timestamp)
        return list(self._data[key])

    def prune(self, guild_id: int, user_id: int, window: int):
        key = (guild_id, user_id)
        cutoff = datetime.utcnow() - timedelta(seconds=window)
        dq = self._data[key]
        while dq and dq[0] < cutoff:
            dq.popleft()

    def count(self, guild_id: int, user_id: int) -> int:
        key = (guild_id, user_id)
        return len(self._data[key])

    def clear(self, guild_id: int, user_id: int):
        key = (guild_id, user_id)
        self._data[key].clear()


INVITE_PATTERN = re.compile(
    r"(discord\.gg|discord\.com/invite|discordapp\.com/invite)/[a-zA-Z0-9]+",
    re.IGNORECASE,
)


class AutoMod(commands.Cog):
    """Automatic moderation: anti-spam, anti-invite, bad words, caps filter."""

    def __init__(self, bot):
        self.bot = bot
        self.spam_tracker = SpamTracker()

    def _get_cfg(self, guild_id: int) -> dict:
        return self.bot.config_manager.get(guild_id).get("automod", {})

    def _is_immune(self, member: discord.Member) -> bool:
        if member.guild_permissions.manage_messages:
            return True
        if member.guild_permissions.administrator:
            return True
        return False

    async def _take_action(self, message: discord.Message, action: str, trigger: str,
                           reason: str, duration: int = None):
        guild = message.guild
        member = message.author
        mod_cog = self.bot.get_cog("Moderation")

        await self.bot.db.log_automod(
            guild.id, member.id, trigger, action, message.content[:500]
        )

        cfg = self.bot.config_manager.get(guild.id)
        log_channel_id = cfg.get("log_channel")
        if log_channel_id:
            ch = guild.get_channel(int(log_channel_id))
            if ch:
                embed = discord.Embed(
                    title="🤖 AutoMod Action",
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
        elif action == "mute" and mod_cog:
            try:
                await message.delete()
            except discord.NotFound:
                pass
            role = await mod_cog._get_mute_role(guild)
            if not role:
                role = await mod_cog._create_mute_role(guild)
            if role not in member.roles:
                await member.add_roles(role, reason=f"AutoMod: {reason}")
                expires_at = datetime.utcnow() + timedelta(seconds=duration) if duration else None
                await self.bot.db.add_mute(guild.id, member.id, expires_at)
        elif action == "kick" and mod_cog:
            try:
                await message.delete()
            except discord.NotFound:
                pass
            try:
                await member.kick(reason=f"AutoMod: {reason}")
            except discord.Forbidden:
                pass
        elif action == "ban" and mod_cog:
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

        cfg = self._get_cfg(message.guild.id)
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

        guild_id = message.guild.id
        user_id = message.author.id

        self.spam_tracker.add(guild_id, user_id, datetime.utcnow())
        self.spam_tracker.prune(guild_id, user_id, window)
        count = self.spam_tracker.count(guild_id, user_id)

        if count >= threshold:
            self.spam_tracker.clear(guild_id, user_id)
            await self._take_action(
                message, action, "anti_spam",
                f"Sending {count} messages in {window}s", duration
            )

    async def _check_invite(self, message: discord.Message, cfg: dict):
        invite_cfg = cfg.get("anti_invite", {})
        if not invite_cfg.get("enabled", False):
            return
        if INVITE_PATTERN.search(message.content):
            action = invite_cfg.get("action", "delete")
            await self._take_action(message, action, "anti_invite", "Discord invite link detected")

    async def _check_bad_words(self, message: discord.Message, cfg: dict):
        bw_cfg = cfg.get("bad_words", {})
        if not bw_cfg.get("enabled", False):
            return
        words = bw_cfg.get("words", [])
        content_lower = message.content.lower()
        for word in words:
            if word.lower() in content_lower:
                action = bw_cfg.get("action", "delete")
                await self._take_action(message, action, "bad_words", f"Prohibited word detected")
                return

    async def _check_caps(self, message: discord.Message, cfg: dict):
        caps_cfg = cfg.get("caps_limit", {})
        if not caps_cfg.get("enabled", False):
            return
        min_length = caps_cfg.get("min_length", 10)
        percent = caps_cfg.get("percent", 70)
        content = message.content
        if len(content) < min_length:
            return
        letters = [c for c in content if c.isalpha()]
        if not letters:
            return
        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters) * 100
        if caps_ratio >= percent:
            action = caps_cfg.get("action", "delete")
            await self._take_action(message, action, "caps_limit",
                                    f"Excessive caps ({caps_ratio:.0f}%)")


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
