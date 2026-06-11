import discord
import logging
from bot.core.config_loader import get_config, get_plugin_config
from bot.core.database import get_pool, create_case
from bot.core.duration import parse_duration
from datetime import datetime, timezone

log = logging.getLogger("bot.escalation")


async def check_manual_escalation(bot, ctx, config, user: discord.Member):
    plugin_cfg = get_plugin_config(config, "escalation")
    if not plugin_cfg.get("enabled", False):
        return
    manual_cfg = (plugin_cfg.get("manual", {}) or {})
    if not manual_cfg.get("enabled", False):
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT COUNT(*) as cnt FROM cases
               WHERE guild_id=$1 AND user_id=$2 AND action IN ('warn','mute','kick') AND active=TRUE""",
            ctx.guild.id, user.id
        )
    count = row["cnt"] if row else 0

    thresholds = sorted(manual_cfg.get("thresholds", []) or [], key=lambda x: x["count"])
    action_to_apply = None
    for threshold in thresholds:
        if count >= threshold["count"]:
            action_to_apply = threshold

    if not action_to_apply:
        return

    action = action_to_apply.get("action", "warn")
    reason = action_to_apply.get("reason", f"Automatic escalation: {count} infractions")
    duration_str = action_to_apply.get("duration")

    await _apply_escalation_action(bot, ctx.guild, user, action, reason, duration_str, config)


async def check_automod_escalation(bot, message: discord.Message, config, rule_name: str):
    plugin_cfg = get_plugin_config(config, "escalation")
    if not plugin_cfg.get("enabled", False):
        return
    automod_cfg = plugin_cfg.get("automod", {}) or {}
    if not automod_cfg.get("enabled", False):
        return

    rule_escalation = automod_cfg.get(rule_name, {}) or {}
    thresholds = rule_escalation.get("thresholds", []) or []
    if not thresholds:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT hit_count FROM automod_hits WHERE guild_id=$1 AND user_id=$2 AND rule=$3",
            message.guild.id, message.author.id, rule_name
        )
    count = row["hit_count"] if row else 0

    thresholds = sorted(thresholds, key=lambda x: x["count"])
    action_to_apply = None
    for threshold in thresholds:
        if count >= threshold["count"]:
            action_to_apply = threshold

    if not action_to_apply:
        return

    member = message.author
    if not isinstance(member, discord.Member):
        return

    action = action_to_apply.get("action", "warn")
    reason = f"[Automod Escalation:{rule_name}] {count} hits"
    duration_str = action_to_apply.get("duration")

    await _apply_escalation_action(bot, message.guild, member, action, reason, duration_str, config)


async def _apply_escalation_action(bot, guild, member, action, reason, duration_str, config):
    try:
        if action == "warn":
            await create_case(guild.id, member.id, str(member),
                              bot.user.id, str(bot.user), "warn", reason)

        elif action == "mute":
            plugin_cfg = get_plugin_config(config, "moderation")
            cfg = plugin_cfg.get("config", {}) or {}
            mute_role_id = cfg.get("mute_role")
            if mute_role_id:
                mute_role = guild.get_role(int(mute_role_id))
                if mute_role:
                    await member.add_roles(mute_role, reason=reason)
                    td = parse_duration(duration_str) if duration_str else None
                    expires_at = datetime.now(timezone.utc) + td if td else None
                    pool = await get_pool()
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO muted_users (guild_id,user_id,removed_roles,expires_at) VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
                            guild.id, member.id, [], expires_at
                        )
                    await create_case(guild.id, member.id, str(member),
                                      bot.user.id, str(bot.user), "mute", reason,
                                      duration_str, expires_at)

        elif action == "kick":
            await member.kick(reason=reason)
            await create_case(guild.id, member.id, str(member),
                              bot.user.id, str(bot.user), "kick", reason)

        elif action == "ban":
            td = parse_duration(duration_str) if duration_str else None
            expires_at = datetime.now(timezone.utc) + td if td else None
            await guild.ban(member, reason=reason, delete_message_days=0)
            if td:
                pool = await get_pool()
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO timed_bans (guild_id,user_id,expires_at) VALUES ($1,$2,$3) ON CONFLICT DO UPDATE SET expires_at=$3",
                        guild.id, member.id, expires_at
                    )
            await create_case(guild.id, member.id, str(member),
                              bot.user.id, str(bot.user), "ban", reason,
                              duration_str, expires_at)
    except Exception as e:
        log.error(f"Escalation action error: {e}")


async def setup(bot):
    pass
