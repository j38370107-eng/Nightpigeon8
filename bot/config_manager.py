import yaml
import os
import copy
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "default.yaml"
GUILD_CONFIG_DIR = Path("bot/data/configs")


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigManager:
    def __init__(self):
        GUILD_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEFAULT_CONFIG_PATH, "r") as f:
            self._default = yaml.safe_load(f) or {}
        self._cache: dict[int, dict] = {}

    def _guild_path(self, guild_id: int) -> Path:
        return GUILD_CONFIG_DIR / f"{guild_id}.yaml"

    def init_guild(self, guild_id: int):
        path = self._guild_path(guild_id)
        if not path.exists():
            path.write_text(yaml.dump({}))
        if guild_id in self._cache:
            del self._cache[guild_id]

    def get(self, guild_id: int) -> dict:
        if guild_id in self._cache:
            return self._cache[guild_id]
        path = self._guild_path(guild_id)
        if path.exists():
            with open(path, "r") as f:
                guild_cfg = yaml.safe_load(f) or {}
        else:
            guild_cfg = {}
        merged = _deep_merge(self._default, guild_cfg)
        self._cache[guild_id] = merged
        return merged

    def get_raw(self, guild_id: int) -> dict:
        path = self._guild_path(guild_id)
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def set(self, guild_id: int, guild_cfg: dict):
        path = self._guild_path(guild_id)
        with open(path, "w") as f:
            yaml.dump(guild_cfg, f, default_flow_style=False, allow_unicode=True)
        if guild_id in self._cache:
            del self._cache[guild_id]

    def set_key(self, guild_id: int, key: str, value):
        raw = self.get_raw(guild_id)
        keys = key.split(".")
        d = raw
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        self.set(guild_id, raw)
