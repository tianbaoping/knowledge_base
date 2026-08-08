import aiosqlite
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger
from app.config import settings


class SQLiteManager:
    def __init__(self):
        self.db_path = settings.SQLITE_DB_PATH
        self._conn: Optional[aiosqlite.Connection] = None

    async def init(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._create_tables()
        logger.info(f"SQLite数据库初始化完成: {self.db_path}")

    async def _create_tables(self):
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge_bases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kb_name TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                file_format TEXT DEFAULT '',
                chunk_count INTEGER DEFAULT 0,
                vector_count INTEGER DEFAULT 0,
                import_status TEXT DEFAULT 'pending',
                md5_hash TEXT DEFAULT '',
                uploaded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS import_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kb_name TEXT NOT NULL,
                task_type TEXT DEFAULT 'single',
                total_files INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                skip_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                finished_at TEXT,
                error_message TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS import_task_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                file_format TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                error_reason TEXT DEFAULT '',
                processed_at TEXT,
                FOREIGN KEY (task_id) REFERENCES import_tasks(id)
            );

            CREATE TABLE IF NOT EXISTS dedup_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_md5 TEXT NOT NULL,
                file_name TEXT NOT NULL,
                kb_name TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(file_md5, kb_name)
            );

            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT NOT NULL,
                module TEXT DEFAULT '',
                file_name TEXT DEFAULT '',
                content TEXT NOT NULL,
                stack_trace TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT DEFAULT 'INFO',
                module TEXT DEFAULT '',
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        await self._conn.commit()
        await self._migrate_dedup_records()

    async def _migrate_dedup_records(self):
        """迁移 dedup_records 表：将 UNIQUE(file_md5) 改为 UNIQUE(file_md5, kb_name)"""
        async with self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='dedup_records'"
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return
            create_sql = row[0]
            if "file_md5 TEXT UNIQUE" not in create_sql:
                return

        logger.info("迁移 dedup_records 表: UNIQUE(file_md5) -> UNIQUE(file_md5, kb_name)")
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS dedup_records_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_md5 TEXT NOT NULL,
                file_name TEXT NOT NULL,
                kb_name TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(file_md5, kb_name)
            );
            INSERT OR IGNORE INTO dedup_records_new (file_md5, file_name, kb_name, file_size, created_at)
            SELECT file_md5, file_name, kb_name, file_size, created_at FROM dedup_records;
            DROP TABLE dedup_records;
            ALTER TABLE dedup_records_new RENAME TO dedup_records;
        """)
        await self._conn.commit()
        logger.info("dedup_records 表迁移完成")

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        return dict(row) if row else {}

    def _rows_to_list(self, rows: List[aiosqlite.Row]) -> List[Dict[str, Any]]:
        return [dict(row) for row in rows]

    async def execute(self, sql: str, params: tuple = ()) -> int:
        async with self._conn.execute(sql, params) as cursor:
            lastrowid = cursor.lastrowid
        await self._conn.commit()
        return lastrowid

    async def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        async with self._conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        return self._rows_to_list(rows)

    async def query_one(self, sql: str, params: tuple = ()) -> Dict[str, Any]:
        async with self._conn.execute(sql, params) as cursor:
            row = await cursor.fetchone()
        return self._row_to_dict(row)

    async def commit(self):
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()


db_manager = SQLiteManager()


async def get_db() -> SQLiteManager:
    return db_manager
