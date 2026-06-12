import asyncpg
import os
import logging

log = logging.getLogger("bot.database")

_pool: asyncpg.Pool = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db() first.")
    return _pool


async def init_db():
    global _pool
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL environment variable not set!")

    _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
    log.info("Database pool created")
    await _create_tables()
    log.info("Database tables ensured")


async def _create_tables():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id BIGINT PRIMARY KEY,
                config TEXT NOT NULL DEFAULT ''
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                case_number INT NOT NULL,
                user_id BIGINT NOT NULL,
                user_tag TEXT,
                moderator_id BIGINT NOT NULL,
                moderator_tag TEXT,
                action TEXT NOT NULL,
                reason TEXT DEFAULT 'No reason provided',
                duration TEXT DEFAULT NULL,
                expires_at TIMESTAMP DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                active BOOLEAN DEFAULT TRUE
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                creator_id BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(guild_id, name)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS muted_users (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                removed_roles BIGINT[],
                expires_at TIMESTAMP DEFAULT NULL,
                UNIQUE(guild_id, user_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS timed_bans (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                UNIQUE(guild_id, user_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS timed_roles (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                UNIQUE(guild_id, user_id, role_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT,
                channel_id BIGINT,
                message TEXT NOT NULL,
                remind_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS starboard_entries (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                original_message_id BIGINT NOT NULL UNIQUE,
                starboard_message_id BIGINT,
                star_count INT DEFAULT 0,
                channel_id BIGINT,
                author_id BIGINT
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reaction_roles (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                type TEXT NOT NULL,
                identifier TEXT NOT NULL,
                role_id BIGINT NOT NULL
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL UNIQUE,
                user_id BIGINT NOT NULL,
                ticket_number INT NOT NULL,
                status TEXT DEFAULT 'open',
                claimed_by BIGINT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_blacklist (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                reason TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_timezones (
                user_id BIGINT PRIMARY KEY,
                timezone TEXT NOT NULL
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_replies (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                trigger TEXT NOT NULL,
                response TEXT NOT NULL,
                trigger_type TEXT DEFAULT 'contains',
                match_case BOOLEAN DEFAULT FALSE,
                reply_type TEXT DEFAULT 'message',
                delete_trigger BOOLEAN DEFAULT FALSE,
                delete_after INT DEFAULT NULL,
                ignore_roles BIGINT[] DEFAULT '{}',
                ignore_channels BIGINT[] DEFAULT '{}',
                required_roles BIGINT[] DEFAULT '{}',
                required_channels BIGINT[] DEFAULT '{}'
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_reactions (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                trigger TEXT NOT NULL,
                trigger_type TEXT DEFAULT 'contains',
                emojis TEXT[] NOT NULL,
                ignore_channels BIGINT[] DEFAULT '{}',
                required_channels BIGINT[] DEFAULT '{}'
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_channel_clean (
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                interval_seconds INT NOT NULL,
                last_cleaned TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (guild_id, channel_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                return_url TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            ALTER TABLE oauth_states ADD COLUMN IF NOT EXISTS return_url TEXT
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lockdown_state (
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                original_perms JSONB,
                locked_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (guild_id, channel_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS automod_hits (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                rule TEXT NOT NULL,
                hit_count INT DEFAULT 1,
                last_hit TIMESTAMP DEFAULT NOW(),
                UNIQUE(guild_id, user_id, rule)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL
            )
        """)


async def get_next_case_number(guild_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COALESCE(MAX(case_number), 0) + 1 as next FROM cases WHERE guild_id = $1",
            guild_id
        )
        return row["next"]


async def create_case(guild_id: int, user_id: int, user_tag: str,
                       moderator_id: int, moderator_tag: str, action: str,
                       reason: str = "No reason provided", duration: str = None,
                       expires_at=None) -> dict:
    pool = await get_pool()
    case_number = await get_next_case_number(guild_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO cases (guild_id, case_number, user_id, user_tag, moderator_id,
               moderator_tag, action, reason, duration, expires_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *""",
            guild_id, case_number, user_id, user_tag, moderator_id,
            moderator_tag, action, reason, duration, expires_at
        )
        return dict(row)


async def close():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
