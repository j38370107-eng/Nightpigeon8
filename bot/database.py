import aiosqlite
import asyncio
from pathlib import Path
from datetime import datetime

DB_PATH = Path("bot/data/bot.db")


class Database:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.db: aiosqlite.Connection = None

    async def init(self):
        self.db = await aiosqlite.connect(DB_PATH)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()
        await self.db.commit()

    async def _create_tables(self):
        await self.db.executescript("""
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                case_number INTEGER NOT NULL,
                action TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                user_tag TEXT NOT NULL,
                mod_id INTEGER NOT NULL,
                mod_tag TEXT NOT NULL,
                reason TEXT,
                duration INTEGER,
                created_at TEXT NOT NULL,
                active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                mod_id INTEGER NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                expires_at TEXT,
                active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS automod_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                trigger TEXT NOT NULL,
                action TEXT NOT NULL,
                message_content TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cases_guild ON cases(guild_id);
            CREATE INDEX IF NOT EXISTS idx_cases_user ON cases(guild_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_warnings_user ON warnings(guild_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_mutes_active ON mutes(guild_id, user_id, active);
        """)

    async def add_case(self, guild_id: int, action: str, user_id: int, user_tag: str,
                       mod_id: int, mod_tag: str, reason: str = None, duration: int = None) -> int:
        async with self.db.execute(
            "SELECT COALESCE(MAX(case_number), 0) + 1 FROM cases WHERE guild_id = ?",
            (guild_id,)
        ) as cur:
            row = await cur.fetchone()
            case_number = row[0]

        await self.db.execute(
            """INSERT INTO cases (guild_id, case_number, action, user_id, user_tag,
               mod_id, mod_tag, reason, duration, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (guild_id, case_number, action, user_id, user_tag,
             mod_id, mod_tag, reason, duration, datetime.utcnow().isoformat())
        )
        await self.db.commit()
        return case_number

    async def get_case(self, guild_id: int, case_number: int) -> aiosqlite.Row | None:
        async with self.db.execute(
            "SELECT * FROM cases WHERE guild_id = ? AND case_number = ?",
            (guild_id, case_number)
        ) as cur:
            return await cur.fetchone()

    async def get_user_cases(self, guild_id: int, user_id: int) -> list:
        async with self.db.execute(
            "SELECT * FROM cases WHERE guild_id = ? AND user_id = ? ORDER BY case_number DESC",
            (guild_id, user_id)
        ) as cur:
            return await cur.fetchall()

    async def get_recent_cases(self, guild_id: int, limit: int = 10) -> list:
        async with self.db.execute(
            "SELECT * FROM cases WHERE guild_id = ? ORDER BY case_number DESC LIMIT ?",
            (guild_id, limit)
        ) as cur:
            return await cur.fetchall()

    async def update_case_reason(self, guild_id: int, case_number: int, reason: str):
        await self.db.execute(
            "UPDATE cases SET reason = ? WHERE guild_id = ? AND case_number = ?",
            (reason, guild_id, case_number)
        )
        await self.db.commit()

    async def add_warning(self, guild_id: int, user_id: int, mod_id: int, reason: str = None) -> int:
        await self.db.execute(
            "INSERT INTO warnings (guild_id, user_id, mod_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, mod_id, reason, datetime.utcnow().isoformat())
        )
        await self.db.commit()
        async with self.db.execute(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            return row[0]

    async def get_warnings(self, guild_id: int, user_id: int) -> list:
        async with self.db.execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            (guild_id, user_id)
        ) as cur:
            return await cur.fetchall()

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            count = row[0]
        await self.db.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        await self.db.commit()
        return count

    async def add_mute(self, guild_id: int, user_id: int, expires_at: datetime = None):
        await self.db.execute(
            "UPDATE mutes SET active = 0 WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        await self.db.execute(
            "INSERT INTO mutes (guild_id, user_id, expires_at, active) VALUES (?, ?, ?, 1)",
            (guild_id, user_id, expires_at.isoformat() if expires_at else None)
        )
        await self.db.commit()

    async def remove_mute(self, guild_id: int, user_id: int):
        await self.db.execute(
            "UPDATE mutes SET active = 0 WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        await self.db.commit()

    async def get_active_mute(self, guild_id: int, user_id: int) -> aiosqlite.Row | None:
        async with self.db.execute(
            "SELECT * FROM mutes WHERE guild_id = ? AND user_id = ? AND active = 1",
            (guild_id, user_id)
        ) as cur:
            return await cur.fetchone()

    async def get_expired_mutes(self) -> list:
        now = datetime.utcnow().isoformat()
        async with self.db.execute(
            "SELECT * FROM mutes WHERE active = 1 AND expires_at IS NOT NULL AND expires_at <= ?",
            (now,)
        ) as cur:
            return await cur.fetchall()

    async def log_automod(self, guild_id: int, user_id: int, trigger: str,
                           action: str, message_content: str = None):
        await self.db.execute(
            """INSERT INTO automod_log (guild_id, user_id, trigger, action, message_content, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (guild_id, user_id, trigger, action, message_content, datetime.utcnow().isoformat())
        )
        await self.db.commit()
