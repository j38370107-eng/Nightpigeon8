import discord
import logging
from typing import Any

log = logging.getLogger("bot.formatter")

DEFAULTS = {
    "ban_reply":        "{user} has been banned | Case: #{case}",
    "forceban_reply":   "{user} has been forcebanned | Case: #{case}",
    "unban_reply":      "{user} has been unbanned | Case: #{case}",
    "kick_reply":       "{user} has been kicked | Case: #{case}",
    "mute_reply":       "{user} has been muted | Case: #{case}",
    "unmute_reply":     "{user} has been unmuted | Case: #{case}",
    "warn_reply":       "{user} has been warned | Case: #{case}",
    "addcase_reply":    "Case added for {user} | Case: #{case}",
    "note_reply":       "Note added for {user} | Case: #{case}",
    "deletecase_reply": "Case #{case} deleted",
    "editcase_reply":   "Case #{case} updated",
    "ban_dm":           "You have been banned from **{server}** for: {reason} | Duration: {duration}",
    "forceban_dm":      "You have been banned from **{server}** for: {reason} | Duration: {duration}",
    "kick_dm":          "You have been kicked from **{server}** for: {reason}",
    "mute_dm":          "You have been muted in **{server}** for: {reason} | Duration: {duration}",
    "unmute_dm":        "You have been unmuted in **{server}**",
    "warn_dm":          "You have been warned in **{server}** for: {reason}",
    "unban_dm":         "You have been unbanned from **{server}**",
    "no_permission":    "You do not have permission to use this command.",
    "case_not_found":   "Case #{case} not found.",
    "user_not_found":   "User not found.",
    "addrole_reply":    "Added role **{role}** to {user}",
    "removerole_reply": "Removed role **{role}** from {user}",
    "temprole_reply":   "Added role **{role}** to {user} for {duration}",
    "purge_reply":      "Deleted {count} messages.",
    "slowmode_reply":   "Slowmode set to {duration} in {channel}.",
    "locked_reply":     "🔒 This channel has been locked. Reason: {reason}",
    "unlocked_reply":   "🔓 This channel has been unlocked.",
    "note_dm":          "",
}

COLOR_MAP = {
    "ban": 0xC46D7A,
    "forceban": 0xC46D7A,
    "unban": 0x6CBF8A,
    "kick": 0xC4A46D,
    "mute": 0xC4A46D,
    "unmute": 0x6CBF8A,
    "warn": 0xC4A46D,
    "note": 0x6D78C4,
    "addcase": 0x6D78C4,
    "default": 0x6D78C4,
}


def _resolve_message_template(config: dict, plugin_name: str, key: str) -> Any:
    """Get message template from YAML config, falling back to defaults."""
    plugins = config.get("plugins", {}) or {}
    plugin = plugins.get(plugin_name, {}) or {}
    messages = plugin.get("messages", {}) or {}
    template = messages.get(key)
    if template is None:
        template = DEFAULTS.get(key, key)
    return template


def _substitute(template: str, **kwargs) -> str:
    """Safely substitute variables in a template string."""
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


def format_message(config: dict, plugin_name: str, key: str, **kwargs) -> discord.Embed | str:
    """
    Format a bot message using YAML config or defaults.
    Returns a discord.Embed if the template is an embed dict, otherwise a string.
    """
    template = _resolve_message_template(config, plugin_name, key)

    if isinstance(template, dict) and "embed" in template:
        embed_data = template["embed"]
        title = _substitute(str(embed_data.get("title", "")), **kwargs)
        description = _substitute(str(embed_data.get("description", "")), **kwargs)
        footer_text = _substitute(str(embed_data.get("footer", "")), **kwargs)
        color = embed_data.get("color", COLOR_MAP.get(key.replace("_reply", "").replace("_dm", ""), 0x6D78C4))

        embed = discord.Embed(
            title=title or None,
            description=description or None,
            color=color,
        )
        if footer_text:
            embed.set_footer(text=footer_text)
        if embed_data.get("thumbnail"):
            thumb = _substitute(str(embed_data["thumbnail"]), **kwargs)
            embed.set_thumbnail(url=thumb)
        return embed

    if isinstance(template, str):
        return _substitute(template, **kwargs)

    return str(template)


async def send_message(ctx_or_channel, config: dict, plugin_name: str, key: str, **kwargs):
    """Format and send a message to a channel."""
    content = format_message(config, plugin_name, key, **kwargs)
    if isinstance(content, discord.Embed):
        return await ctx_or_channel.send(embed=content)
    elif content:
        return await ctx_or_channel.send(content)


async def send_dm(user: discord.User | discord.Member, config: dict, plugin_name: str, key: str, **kwargs):
    """Format and DM a user. Silently fails if DMs are closed."""
    content = format_message(config, plugin_name, key, **kwargs)
    if not content:
        return
    try:
        if isinstance(content, discord.Embed):
            await user.send(embed=content)
        else:
            await user.send(content)
    except (discord.Forbidden, discord.HTTPException):
        pass
