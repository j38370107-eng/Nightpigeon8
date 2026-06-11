import yaml
import logging
from bot.core.database import get_pool

log = logging.getLogger("bot.config")


async def get_config(guild_id: int) -> dict:
    """Fetch and parse YAML config for a guild from the database. Never cached."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT config FROM guild_configs WHERE guild_id = $1", guild_id
        )
    if not row or not row["config"].strip():
        return {}
    try:
        result = yaml.safe_load(row["config"])
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError as e:
        log.warning(f"Invalid YAML config for guild {guild_id}: {e}")
        return {}


async def get_config_text(guild_id: int) -> str:
    """Get the raw YAML config text for a guild."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT config FROM guild_configs WHERE guild_id = $1", guild_id
        )
    return row["config"] if row else ""


async def save_config(guild_id: int, config_text: str):
    """Validate and save YAML config text to the database."""
    try:
        yaml.safe_load(config_text)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO guild_configs (guild_id, config) VALUES ($1, $2)
               ON CONFLICT (guild_id) DO UPDATE SET config = $2""",
            guild_id, config_text
        )


async def ensure_guild(guild_id: int):
    """Ensure a guild has a config row (create empty if missing)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO guild_configs (guild_id, config) VALUES ($1, '') ON CONFLICT DO NOTHING",
            guild_id
        )


def get_prefix(config: dict) -> str:
    return config.get("prefix", "!")


def get_plugin_config(config: dict, plugin_name: str) -> dict:
    """Get the config block for a specific plugin."""
    plugins = config.get("plugins", {})
    if not plugins:
        return {}
    plugin = plugins.get(plugin_name, {})
    if not isinstance(plugin, dict):
        return {}
    return plugin


def is_plugin_enabled(config: dict, plugin_name: str) -> bool:
    """Check if a plugin is enabled in the config."""
    plugin = get_plugin_config(config, plugin_name)
    return plugin.get("enabled", False)
