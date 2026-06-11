import discord
from discord.ext import commands
from collections import defaultdict, deque
from datetime import datetime, timezone
import re
import logging
import unicodedata
import asyncio
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled
from bot.core.database import get_pool, create_case
from bot.core.duration import parse_duration, format_duration
from bot.core.message_formatter import send_dm

log = logging.getLogger("bot.automod")

_msg_cache: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))
_repeat_cache: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))
_attach_cache: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))


def _wildcard_match(pattern: str, text: str) -> bool:
    regex = re.escape(pattern).replace(r"\*", ".*")
    return bool(re.search(regex, text, re.IGNORECASE))


def _count_emojis(text: str) -> int:
    emoji_pattern = re.compile(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F9FF\U00002702-\U000027B0"
        r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
        r"\u2600-\u26FF\u2700-\u27BF]|<a?:[a-zA-Z0-9_]+:\d+>",
        flags=re.UNICODE
    )
    return len(emoji_pattern.findall(text))


def _has_zalgo(text: str) -> bool:
    for char in text:
        cat = unicodedata.category(char)
        if cat in ("Mn", "Me", "Mc"):
            combining = unicodedata.combining(char)
            if combining > 0:
                return True
    return False


def _count_urls(text: str) -> int:
    return len(re.findall(r"https?://\S+|discord\.gg/\S+", text))


class AutomodCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_rule(self, config: dict, rule_name: str) -> dict | None:
        plugin_cfg = get_plugin_config(config, "automod")
        if not plugin_cfg.get("enabled", False):
            return None
        rules = plugin_cfg.get("rules", {}) or {}
        rule = rules.get(rule_name, {}) or {}
        if not rule.get("enabled", False):
            return None
        return rule

    async def _is_exempt(self, config: dict, message: discord.Message) -> bool:
        plugin_cfg = get_plugin_config(config, "automod")
        ignore_roles = [int(r) for r in (plugin_cfg.get("ignore_roles", []) or [])]
        ignore_channels = [int(c) for c in (plugin_cfg.get("ignore_channels", []) or [])]
        if message.channel.id in ignore_channels:
            return True
        member_role_ids = [r.id for r in message.author.roles]
        for rid in ignore_roles:
            if rid in member_role_ids:
                return True
        return False

    async def _apply_action(self, message: discord.Message, rule: dict, rule_name: str, config: dict):
        action = rule.get("action", {}) or {}
        msg_text = rule.get("message", "")

        if action.get("delete"):
            try:
                await message.delete()
            except Exception:
                pass

        if action.get("dm_user") and msg_text:
            try:
                await message.author.send(msg_text)
            except Exception:
                pass

        if action.get("reply") and msg_text:
            try:
                reply_msg = await message.channel.send(f"{message.author.mention} {msg_text}")
                await asyncio.sleep(5)
                await reply_msg.delete()
            except Exception:
                pass

        member = message.author
        guild = message.guild

        if action.get("warn"):
            await create_case(guild.id, member.id, str(member),
                              self.bot.user.id, str(self.bot.user),
                              "warn", f"[Automod:{rule_name}] {msg_text or 'Rule triggered'}")

        mute_dur = action.get("mute")
        if mute_dur:
            try:
                td = parse_duration(mute_dur)
                mute_cfg = get_plugin_config(config, "moderation").get("config", {}) or {}
                mute_role_id = mute_cfg.get("mute_role")
                if mute_role_id:
                    mute_role = guild.get_role(int(mute_role_id))
                    if mute_role:
                        await member.add_roles(mute_role, reason=f"[Automod:{rule_name}]")
                        expires_at = datetime.now(timezone.utc) + td if td else None
                        pool = await get_pool()
                        async with pool.acquire() as conn:
                            await conn.execute(
                                "INSERT INTO muted_users (guild_id,user_id,removed_roles,expires_at) VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
                                guild.id, member.id, [], expires_at
                            )
                        await create_case(guild.id, member.id, str(member),
                                          self.bot.user.id, str(self.bot.user),
                                          "mute", f"[Automod:{rule_name}]", mute_dur, expires_at)
            except Exception as e:
                log.error(f"Automod mute error: {e}")

        if action.get("kick"):
            try:
                await member.kick(reason=f"[Automod:{rule_name}]")
                await create_case(guild.id, member.id, str(member),
                                  self.bot.user.id, str(self.bot.user),
                                  "kick", f"[Automod:{rule_name}]")
            except Exception:
                pass

        ban_dur = action.get("ban")
        if ban_dur:
            try:
                td = parse_duration(ban_dur) if ban_dur not in (True, False) else None
                await guild.ban(member, reason=f"[Automod:{rule_name}]", delete_message_days=0)
                expires_at = datetime.now(timezone.utc) + td if td else None
                if td:
                    pool = await get_pool()
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO timed_bans (guild_id,user_id,expires_at) VALUES ($1,$2,$3) ON CONFLICT DO UPDATE SET expires_at=$3",
                            guild.id, member.id, expires_at
                        )
                await create_case(guild.id, member.id, str(member),
                                  self.bot.user.id, str(self.bot.user),
                                  "ban", f"[Automod:{rule_name}]",
                                  ban_dur if isinstance(ban_dur, str) else None, expires_at)
            except Exception:
                pass

        log_channel_id = action.get("log_channel")
        if log_channel_id:
            channel = guild.get_channel(int(log_channel_id))
            if channel:
                embed = discord.Embed(
                    title=f"Automod: {rule_name}",
                    description=f"{member.mention} triggered rule `{rule_name}`",
                    color=0xC4A46D,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Message", value=message.content[:200] if message.content else "[deleted]", inline=False)
                try:
                    await channel.send(embed=embed)
                except Exception:
                    pass

        await self._record_automod_hit(guild.id, member.id, rule_name)
        await self._check_automod_escalation(message, config, rule_name)

    async def _record_automod_hit(self, guild_id, user_id, rule_name):
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO automod_hits (guild_id,user_id,rule,hit_count,last_hit)
                       VALUES ($1,$2,$3,1,NOW())
                       ON CONFLICT (guild_id,user_id,rule) DO UPDATE
                       SET hit_count=automod_hits.hit_count+1, last_hit=NOW()""",
                    guild_id, user_id, rule_name
                )
        except Exception:
            pass

    async def _check_automod_escalation(self, message, config, rule_name):
        from bot.plugins.escalation import check_automod_escalation
        try:
            await check_automod_escalation(self.bot, message, config, rule_name)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        config = await get_config(message.guild.id)
        if not is_plugin_enabled(config, "automod"):
            return
        if await self._is_exempt(config, message):
            return

        await self._check_spam(message, config)
        await self._check_bad_words(message, config)
        await self._check_invite_links(message, config)
        await self._check_mass_mentions(message, config)
        await self._check_caps_spam(message, config)
        await self._check_link_spam(message, config)
        await self._check_repeated_text(message, config)
        await self._check_mass_emojis(message, config)
        await self._check_zalgo(message, config)
        await self._check_newline_spam(message, config)
        await self._check_attachment_spam(message, config)
        await self._check_mention_everyone(message, config)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = await get_config(member.guild.id)
        rule = await self._get_rule(config, "new_account_gate")
        if not rule:
            return
        min_age = rule.get("min_age_days", 7)
        age_days = (datetime.now(timezone.utc) - member.created_at).days
        if age_days < min_age:
            action = rule.get("action", {}) or {}
            msg_text = rule.get("message", "")
            if action.get("dm_user") and msg_text:
                try:
                    await member.send(msg_text)
                except Exception:
                    pass
            if action.get("kick"):
                try:
                    await member.kick(reason="[Automod:new_account_gate] Account too new")
                except Exception:
                    pass
            log_channel_id = action.get("log_channel")
            if log_channel_id:
                channel = member.guild.get_channel(int(log_channel_id))
                if channel:
                    embed = discord.Embed(
                        title="New Account Gate",
                        description=f"{member.mention} account is {age_days} days old (min: {min_age})",
                        color=0xC4A46D,
                        timestamp=datetime.now(timezone.utc)
                    )
                    try:
                        await channel.send(embed=embed)
                    except Exception:
                        pass

    async def _check_spam(self, message, config):
        rule = await self._get_rule(config, "spam")
        if not rule:
            return
        max_msgs = rule.get("max_messages", 5)
        per_secs = rule.get("per_seconds", 4)
        now = message.created_at.timestamp()
        cache = _msg_cache[message.guild.id][message.author.id]
        cache.append(now)
        while cache and cache[0] < now - per_secs:
            cache.popleft()
        if len(cache) >= max_msgs:
            cache.clear()
            await self._apply_action(message, rule, "spam", config)

    async def _check_bad_words(self, message, config):
        rule = await self._get_rule(config, "bad_words")
        if not rule:
            return
        words = rule.get("words", []) or []
        content = message.content.lower()
        for word in words:
            if _wildcard_match(word, content):
                await self._apply_action(message, rule, "bad_words", config)
                return

    async def _check_invite_links(self, message, config):
        rule = await self._get_rule(config, "invite_links")
        if not rule:
            return
        if not re.search(r"discord\.gg/\S+|discord\.com/invite/\S+", message.content, re.IGNORECASE):
            return
        allow_own = rule.get("allow_own_server", True)
        if allow_own:
            invites = re.findall(r"discord\.gg/(\S+)|discord\.com/invite/(\S+)", message.content, re.IGNORECASE)
            for match in invites:
                code = match[0] or match[1]
                try:
                    invite = await message.guild.fetch_invite(code)
                    if invite.guild and invite.guild.id == message.guild.id:
                        return
                except Exception:
                    pass
        await self._apply_action(message, rule, "invite_links", config)

    async def _check_mass_mentions(self, message, config):
        rule = await self._get_rule(config, "mass_mentions")
        if not rule:
            return
        max_mentions = rule.get("max_mentions", 5)
        total = len(message.mentions) + len(message.role_mentions)
        if total >= max_mentions:
            await self._apply_action(message, rule, "mass_mentions", config)

    async def _check_caps_spam(self, message, config):
        rule = await self._get_rule(config, "caps_spam")
        if not rule:
            return
        min_len = rule.get("min_length", 10)
        max_pct = rule.get("max_caps_percent", 70)
        text = message.content
        if len(text) < min_len:
            return
        letters = [c for c in text if c.isalpha()]
        if not letters:
            return
        caps_pct = sum(1 for c in letters if c.isupper()) / len(letters) * 100
        if caps_pct >= max_pct:
            await self._apply_action(message, rule, "caps_spam", config)

    async def _check_link_spam(self, message, config):
        rule = await self._get_rule(config, "link_spam")
        if not rule:
            return
        max_links = rule.get("max_links", 3)
        if _count_urls(message.content) >= max_links:
            await self._apply_action(message, rule, "link_spam", config)

    async def _check_repeated_text(self, message, config):
        rule = await self._get_rule(config, "repeated_text")
        if not rule:
            return
        max_repeats = rule.get("max_repeats", 3)
        per_secs = rule.get("per_seconds", 10)
        now = message.created_at.timestamp()
        cache = _repeat_cache[message.guild.id][message.author.id]
        cache.append((now, message.content.lower().strip()))
        while cache and cache[0][0] < now - per_secs:
            cache.popleft()
        content = message.content.lower().strip()
        count = sum(1 for _, c in cache if c == content)
        if count >= max_repeats:
            cache.clear()
            await self._apply_action(message, rule, "repeated_text", config)

    async def _check_mass_emojis(self, message, config):
        rule = await self._get_rule(config, "mass_emojis")
        if not rule:
            return
        max_emojis = rule.get("max_emojis", 10)
        if _count_emojis(message.content) >= max_emojis:
            await self._apply_action(message, rule, "mass_emojis", config)

    async def _check_zalgo(self, message, config):
        rule = await self._get_rule(config, "zalgo")
        if not rule:
            return
        if _has_zalgo(message.content):
            await self._apply_action(message, rule, "zalgo", config)

    async def _check_newline_spam(self, message, config):
        rule = await self._get_rule(config, "newline_spam")
        if not rule:
            return
        max_newlines = rule.get("max_newlines", 8)
        if message.content.count("\n") >= max_newlines:
            await self._apply_action(message, rule, "newline_spam", config)

    async def _check_attachment_spam(self, message, config):
        rule = await self._get_rule(config, "attachment_spam")
        if not rule:
            return
        max_attach = rule.get("max_attachments", 3)
        per_secs = rule.get("per_seconds", 5)
        if not message.attachments:
            return
        now = message.created_at.timestamp()
        cache = _attach_cache[message.guild.id][message.author.id]
        cache.append(now)
        while cache and cache[0] < now - per_secs:
            cache.popleft()
        if len(cache) >= max_attach:
            cache.clear()
            await self._apply_action(message, rule, "attachment_spam", config)

    async def _check_mention_everyone(self, message, config):
        rule = await self._get_rule(config, "mention_everyone_attempt")
        if not rule:
            return
        if "@everyone" in message.content or "@here" in message.content:
            if not message.mention_everyone:
                await self._apply_action(message, rule, "mention_everyone_attempt", config)


async def setup(bot):
    await bot.add_cog(AutomodCog(bot))
