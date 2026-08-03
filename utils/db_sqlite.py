# async_db.py
import aiosqlite
import time
from typing import List, Dict, Optional
from pathlib import Path

class AsyncDB:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default path: ../utils/data/apiwatch.db
            db_path = Path(__file__).parent.parent / 'data' / 'apiwatch.db'
        self.db_path = str(db_path)
        self._initialized = False

    async def init(self):
        """Initialize the database"""
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            # WAL lets the dashboard read while the collector writes,
            # default journal mode can block reads during a write
            await db.execute('PRAGMA journal_mode=WAL')

            # container logs only now, no more request/response capture
            await db.execute('''
            CREATE TABLE IF NOT EXISTS container_logs (
                id TEXT PRIMARY KEY,
                container_id TEXT,
                container_name TEXT,
                service TEXT,
                level TEXT,
                logger TEXT,
                message TEXT,
                raw TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            ''')

            # checkpoint state, one row per container, this is what
            # survives a restart so we know where to resume streaming
            # from instead of replaying from zero or losing the gap
            await db.execute('''
            CREATE TABLE IF NOT EXISTS container_checkpoints (
                container_id TEXT PRIMARY KEY,
                container_name TEXT,
                last_seen_ts INTEGER NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            ''')

            # sessions, this is what makes auth real: every protected
            # route checks a token against this table instead of trusting
            # whatever the browser's localStorage claims
            await db.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at INTEGER NOT NULL
            );
            ''')

            # single-row config for alerting, slack and gmail are
            # independent toggles now (both can fire on the same log),
            # credentials themselves stay in env vars, never stored here
            await db.execute('''
            CREATE TABLE IF NOT EXISTS alert_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                slack_enabled INTEGER DEFAULT 0,
                gmail_enabled INTEGER DEFAULT 0,
                min_level TEXT DEFAULT 'ERROR'
            );
            ''')
            # migration for dbs created before multi-channel support,
            # ADD COLUMN fails harmlessly if the column already exists
            for stmt in (
                "ALTER TABLE alert_settings ADD COLUMN slack_enabled INTEGER DEFAULT 0",
                "ALTER TABLE alert_settings ADD COLUMN gmail_enabled INTEGER DEFAULT 0",
            ):
                try:
                    await db.execute(stmt)
                except Exception:
                    pass

            await db.execute(
                'CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON container_logs(timestamp)'
            )
            await db.execute(
                'CREATE INDEX IF NOT EXISTS idx_logs_service ON container_logs(service)'
            )
            await db.execute(
                'CREATE INDEX IF NOT EXISTS idx_logs_container_name ON container_logs(container_name)'
            )
            await db.execute(
                'CREATE INDEX IF NOT EXISTS idx_logs_level ON container_logs(level)'
            )

            await db.commit()
        self._initialized = True

    async def insert_log(self, **data):
        """Insert a single log record, returns the new total row count."""
        fields = [
            'id', 'container_id', 'container_name', 'service',
            'level', 'logger', 'message', 'raw', 'timestamp'
        ]
        values = [data.get(f) for f in fields]

        placeholders = ', '.join(['?' for _ in fields])
        sql = f'INSERT OR REPLACE INTO container_logs ({", ".join(fields)}) VALUES ({placeholders})'

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(sql, values)
            await db.commit()

            cur = await db.execute("SELECT COUNT(*) FROM container_logs")
            row = await cur.fetchone()

        return row[0]

    async def insert_logs_batch(self, records: List[dict]):
        """
        Insert many log records in a single transaction. Use this from
        the collector instead of calling insert_log per line, one fsync
        per line is what actually bottlenecks SQLite at even modest
        log volume.
        """
        if not records:
            return

        fields = [
            'id', 'container_id', 'container_name', 'service',
            'level', 'logger', 'message', 'raw', 'timestamp'
        ]
        rows = [[data.get(f) for f in fields] for data in records]

        placeholders = ', '.join(['?' for _ in fields])
        sql = f'INSERT OR REPLACE INTO container_logs ({", ".join(fields)}) VALUES ({placeholders})'

        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(sql, rows)
            await db.commit()

    async def get_all_logs(self) -> List[Dict]:
        """Fetch all logs"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM container_logs ORDER BY timestamp DESC') as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def delete_all_logs(self):
        """Delete all records in container_logs"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM container_logs')
            await db.commit()
        return []

    async def delete_logs_older_than(self, cutoff_timestamp: str):
        """
        Delete log rows older than cutoff_timestamp (ISO string, same
        format SQLite's CURRENT_TIMESTAMP produces). Call this on a
        timer, once an hour is plenty, to enforce retention.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                'DELETE FROM container_logs WHERE timestamp < ?', (cutoff_timestamp,)
            )
            await db.commit()
            return cur.rowcount

    async def get_logs_paginated(self, page=1, limit=20, search: Optional[str] = None):
        offset = (page - 1) * limit

        where_clause = ""
        params: List = []
        if search:
            where_clause = "WHERE message LIKE ? OR raw LIKE ?"
            term = f"%{search}%"
            params = [term, term]

        query = f"""
            SELECT
                *,
                COUNT(*) OVER() AS total_count
            FROM container_logs
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        params += [limit, offset]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

        results = []
        total_logs = 0

        for row in rows:
            item = dict(row)
            total_logs = item.pop("total_count", total_logs)
            results.append(item)

        return {
            "total": total_logs,
            "page": page,
            "limit": limit,
            "results": results
        }

    async def get_distinct_containers(self) -> List[str]:
        """
        Every container name that has ever logged something, including
        containers that have since stopped or been removed. Their old
        logs still reference the name, so it stays filterable.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                'SELECT DISTINCT container_name FROM container_logs '
                'WHERE container_name IS NOT NULL ORDER BY container_name'
            )
            rows = await cur.fetchall()
            return [r[0] for r in rows]

    async def get_container_stats(self) -> List[Dict]:
        """
        Per-container summary: how much it's logged, how much of that
        was errors, and when it was first/last seen. Powers the
        containers panel, one row per container regardless of whether
        it's still running.
        """
        query = """
            SELECT
                container_name,
                COUNT(*) AS log_count,
                SUM(CASE WHEN level IN ('ERROR', 'CRITICAL') THEN 1 ELSE 0 END) AS error_count,
                MIN(timestamp) AS first_seen,
                MAX(timestamp) AS last_seen
            FROM container_logs
            WHERE container_name IS NOT NULL
            GROUP BY container_name
            ORDER BY last_seen DESC
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(query)
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def get_level_counts(self) -> Dict[str, int]:
        """Total count per level, across all logs, for the breakdown chart."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                'SELECT level, COUNT(*) FROM container_logs GROUP BY level'
            )
            rows = await cur.fetchall()
            return {row[0] or 'UNKNOWN': row[1] for row in rows}

    # ---- alert settings ----

    async def get_alert_settings(self) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute('SELECT * FROM alert_settings WHERE id = 1')
            row = await cur.fetchone()
            return dict(row) if row else None

    async def save_alert_settings(self, slack_enabled: bool, gmail_enabled: bool, min_level: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO alert_settings (id, slack_enabled, gmail_enabled, min_level)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    slack_enabled = excluded.slack_enabled,
                    gmail_enabled = excluded.gmail_enabled,
                    min_level = excluded.min_level
            ''', (int(slack_enabled), int(gmail_enabled), min_level))
            await db.commit()

    # ---- sessions (auth) ----

    async def create_session(self, token: str, expires_at: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'INSERT INTO sessions (token, expires_at) VALUES (?, ?)',
                (token, expires_at)
            )
            await db.commit()

    async def session_valid(self, token: Optional[str]) -> bool:
        if not token:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                'SELECT expires_at FROM sessions WHERE token = ?', (token,)
            )
            row = await cur.fetchone()
            if not row:
                return False
            return row[0] > int(time.time())

    async def delete_session(self, token: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM sessions WHERE token = ?', (token,))
            await db.commit()

    async def cleanup_expired_sessions(self):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                'DELETE FROM sessions WHERE expires_at < ?', (int(time.time()),)
            )
            await db.commit()
            return cur.rowcount

    # ---- checkpoint state (for restart-safe streaming) ----

    async def get_checkpoint(self, container_id: str) -> Optional[int]:
        """Return last_seen_ts for a container, or None if never seen."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                'SELECT last_seen_ts FROM container_checkpoints WHERE container_id = ?',
                (container_id,)
            )
            row = await cur.fetchone()
            return row[0] if row else None

    async def get_all_checkpoints(self) -> Dict[str, int]:
        """Return {container_id: last_seen_ts} for every known container."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                'SELECT container_id, last_seen_ts FROM container_checkpoints'
            )
            rows = await cur.fetchall()
            return {row[0]: row[1] for row in rows}

    async def set_checkpoint(self, container_id: str, container_name: str, ts: Optional[int] = None):
        """
        Upsert the checkpoint for a container. Call this periodically
        while streaming (not on every line), a checkpoint written every
        few seconds is enough, and re-reading a few lines on restart is
        fine since ingestion dedupes by log id anyway (INSERT OR REPLACE).
        """
        ts = ts if ts is not None else int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO container_checkpoints (container_id, container_name, last_seen_ts, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(container_id) DO UPDATE SET
                    container_name = excluded.container_name,
                    last_seen_ts = excluded.last_seen_ts,
                    updated_at = CURRENT_TIMESTAMP
            ''', (container_id, container_name, ts))
            await db.commit()

    async def remove_checkpoints_except(self, live_container_ids: List[str]):
        """
        Prune checkpoints for containers that no longer exist, so the
        table doesn't grow forever with dead container ids. This is
        separate from container_logs, old log rows are kept regardless.
        """
        if not live_container_ids:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('DELETE FROM container_checkpoints')
                await db.commit()
            return

        placeholders = ', '.join('?' for _ in live_container_ids)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f'DELETE FROM container_checkpoints WHERE container_id NOT IN ({placeholders})',
                live_container_ids
            )
            await db.commit()