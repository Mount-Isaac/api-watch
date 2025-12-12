# async_db.py
import aiosqlite
import json
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
            await db.execute('''
            CREATE TABLE IF NOT EXISTS api_logs (
                id TEXT PRIMARY KEY,
                method TEXT,
                path TEXT,
                status_code TEXT,
                headers TEXT,
                query_params TEXT,
                request_data TEXT,
                response_data TEXT,
                duration_ms REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                service TEXT
            );
            ''')
            await db.commit()
        self._initialized = True

    async def insert_log(self, **data):
        """
        Insert a log record.
        Dict fields are serialized to JSON automatically.
        """
        fields = [
            'id', 'method', 'path', 'status_code', 'headers',
            'query_params', 'request_data', 'response_data',
            'duration_ms', 'timestamp', 'service'
        ]
        values = []
        for f in fields:
            value = data.get(f)
            # Serialize dicts to JSON
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            values.append(value)

        placeholders = ', '.join(['?' for _ in fields])
        sql = f'INSERT OR REPLACE INTO api_logs ({", ".join(fields)}) VALUES ({placeholders})'

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(sql, values)
            await db.commit()

    async def get_all_logs(self) -> List[Dict]:
        """Fetch all logs and deserialize JSON fields"""
        dict_fields = ['headers', 'query_params', 'request_data', 'response_data']
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM api_logs ORDER BY timestamp DESC') as cursor:
                rows = await cursor.fetchall()
                result = []
                for row in rows:
                    row_dict = dict(row)
                    for f in dict_fields:
                        if row_dict.get(f):
                            try:
                                row_dict[f] = json.loads(row_dict[f])
                            except json.JSONDecodeError:
                                pass  # keep as string if invalid JSON
                    result.append(row_dict)
                return result

    async def delete_all_logs(self):
        """Delete all records in api_logs"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM api_logs')
            await db.commit()
        return []
