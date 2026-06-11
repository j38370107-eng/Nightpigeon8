import discord
from datetime import datetime, timedelta
import re


def parse_duration(duration_str: str) -> int | None:
    """Parse a duration string like 1h30m, 2d, 30s into seconds."""
    if not duration_str:
        return None
    pattern = re.compile(r"(\d+)\s*([smhdw])")
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    total = 0
    matches = pattern.findall(duration_str.lower())
    if not matches:
        return None
    for value, unit in matches:
        total += int(value) * multipliers[unit]
    return total if total > 0 else None


def format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds is None:
        return "permanent"
    intervals = [
        ("week", 604800),
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
        ("second", 1),
    ]
    parts = []
    remaining = seconds
    for name, count in intervals:
        value = remaining // count
        if value:
            remaining -= value * count
            parts.append(f"{value} {name}{'s' if value != 1 else ''}")
    return ", ".join(parts) if parts else "0 seconds"


def action_color(action: str) -> discord.Color:
    colors = {
        "ban": discord.Color.red(),
        "unban": discord.Color.green(),
        "kick": discord.Color.orange(),
        "mute": discord.Color.gold(),
        "unmute": discord.Color.green(),
        "warn": discord.Color.yellow(),
        "timeout": discord.Color.orange(),
        "note": discord.Color.blurple(),
        "softban": discord.Color.dark_orange(),
    }
    return colors.get(action.lower(), discord.Color.greyple())


def action_emoji(action: str) -> str:
    emojis = {
        "ban": "🔨",
        "unban": "✅",
        "kick": "👢",
        "mute": "🔇",
        "unmute": "🔊",
        "warn": "⚠️",
        "timeout": "⏰",
        "note": "📝",
        "softban": "🪃",
    }
    return emojis.get(action.lower(), "⚙️")


def mod_embed(action: str, user: discord.User | discord.Member, moderator: discord.Member,
              reason: str = None, duration: int = None, case_number: int = None) -> discord.Embed:
    emoji = action_emoji(action)
    color = action_color(action)
    embed = discord.Embed(
        title=f"{emoji} {action.title()}",
        color=color,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="User", value=f"{user.mention} (`{user}` | `{user.id}`)", inline=False)
    embed.add_field(name="Moderator", value=f"{moderator.mention} (`{moderator}`)", inline=False)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    if duration is not None:
        embed.add_field(name="Duration", value=format_duration(duration), inline=True)
        expires = datetime.utcnow() + timedelta(seconds=duration)
        embed.add_field(name="Expires", value=f"<t:{int(expires.timestamp())}:R>", inline=True)
    if case_number is not None:
        embed.set_footer(text=f"Case #{case_number}")
    embed.set_thumbnail(url=user.display_avatar.url)
    return embed


def case_embed(case) -> discord.Embed:
    action = case["action"]
    emoji = action_emoji(action)
    color = action_color(action)
    embed = discord.Embed(
        title=f"{emoji} Case #{case['case_number']} — {action.title()}",
        color=color,
    )
    embed.add_field(name="User", value=f"`{case['user_tag']}` (`{case['user_id']}`)", inline=True)
    embed.add_field(name="Moderator", value=f"`{case['mod_tag']}`", inline=True)
    embed.add_field(name="Reason", value=case["reason"] or "No reason provided", inline=False)
    if case["duration"]:
        embed.add_field(name="Duration", value=format_duration(case["duration"]), inline=True)
    embed.set_footer(text=f"Created: {case['created_at'][:19]} UTC")
    return embed
