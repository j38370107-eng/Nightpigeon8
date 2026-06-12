---
name: asyncpg JSONB decode
description: asyncpg returns JSONB columns as native Python dicts/lists, NOT as JSON strings. Calling json.loads() on them raises TypeError which silently returns None.
---

# asyncpg JSONB column decoding

## The rule
asyncpg automatically decodes `JSON` and `JSONB` PostgreSQL columns into native Python objects (dict, list, etc.) using `json.loads` internally. The returned value is already a Python dict — **never call `json.loads()` on it again**.

**Why:** Calling `json.loads(some_dict)` raises `TypeError: the JSON object must be str, bytes or bytearray, not dict`. If wrapped in `except Exception`, this silently returns `None`, making every session lookup fail and producing a permanent 401.

**How to apply:** When reading from a JSONB column via asyncpg:
```python
# WRONG — crashes silently
return json.loads(row["data"])

# RIGHT — handle both cases defensively
data = row["data"]
return data if isinstance(data, dict) else json.loads(data)
```

This applies everywhere asyncpg is used with JSON/JSONB columns.
