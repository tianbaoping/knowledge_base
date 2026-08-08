import os
import time
import shutil
from typing import Dict, Any, List
from datetime import datetime, timedelta
from loguru import logger
from app.config import settings
from app.database.sqlite_db import db_manager
from app.services.qdrant_service import qdrant_service


class MonitorService:
    def __init__(self):
        self.start_time = time.time()

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def get_system_status(self) -> Dict[str, Any]:
        try:
            qdrant_health = await qdrant_service.health_check()
        except Exception:
            qdrant_health = {"status": "disconnected"}
        try:
            qdrant_collections = await qdrant_service.list_collections()
        except Exception:
            qdrant_collections = []

        kbs = await db_manager.query("SELECT * FROM knowledge_bases")
        files = await db_manager.query("SELECT * FROM files WHERE import_status = 'success'")
        total_vectors = sum(c.get("vectors_count") or 0 for c in qdrant_collections)

        today = datetime.now().strftime("%Y-%m-%d")
        today_imports = await db_manager.query_one(
            "SELECT COUNT(*) as cnt FROM files WHERE DATE(uploaded_at) = ?", (today,)
        )

        return {
            "app_status": "running",
            "app_version": settings.APP_VERSION,
            "qdrant_status": qdrant_health.get("status", "unknown"),
            "qdrant_collections": [c["name"] for c in qdrant_collections],
            "uptime_seconds": int(time.time() - self.start_time),
            "total_kbs": len(kbs),
            "total_files": len(files),
            "total_vectors": total_vectors,
            "today_imports": today_imports["cnt"] if today_imports else 0,
        }

    async def get_resource_info(self) -> Dict[str, Any]:
        disk_usage = self._get_disk_usage()
        memory_usage = self._get_memory_usage()
        try:
            qdrant_collections = await qdrant_service.list_collections()
        except Exception:
            qdrant_collections = []
        vector_size = sum((c.get("vectors_count") or 0) * settings.EMBEDDING_DIM * 4 for c in qdrant_collections)

        return {
            "disk_usage_percent": disk_usage["percent"],
            "disk_total_gb": disk_usage["total_gb"],
            "disk_used_gb": disk_usage["used_gb"],
            "memory_usage_percent": memory_usage,
            "vector_storage_size": vector_size,
            "vector_storage_mb": round(vector_size / 1024 / 1024, 2),
        }

    def _get_disk_usage(self) -> Dict[str, Any]:
        try:
            usage = shutil.disk_usage(self._get_drive_root())
            return {
                "total_gb": round(usage.total / 1024 / 1024 / 1024, 2),
                "used_gb": round(usage.used / 1024 / 1024 / 1024, 2),
                "percent": round(usage.used / usage.total * 100, 2),
            }
        except Exception:
            return {"total_gb": 0, "used_gb": 0, "percent": 0}

    def _get_drive_root(self) -> str:
        import platform
        if platform.system() == "Windows":
            drive = os.path.splitdrive(os.path.abspath(settings.BASE_DIR))[0]
            return drive + "\\" if drive else "C:\\"
        return "/"

    def _get_memory_usage(self) -> float:
        try:
            import psutil
            mem = psutil.virtual_memory()
            return round(mem.percent, 2)
        except ImportError:
            return 0.0
        except Exception:
            return 0.0

    async def get_error_logs(
        self,
        error_type: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        if error_type:
            return await db_manager.query(
                "SELECT * FROM error_logs WHERE error_type = ? ORDER BY created_at DESC LIMIT ?",
                (error_type, limit),
            )
        return await db_manager.query(
            "SELECT * FROM error_logs ORDER BY created_at DESC LIMIT ?", (limit,)
        )

    async def log_error(
        self,
        error_type: str,
        module: str,
        file_name: str,
        content: str,
        stack_trace: str = "",
    ):
        await db_manager.execute(
            """INSERT INTO error_logs 
               (error_type, module, file_name, content, stack_trace, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (error_type, module, file_name, content, stack_trace, self._now()),
        )

    async def get_system_logs(
        self, level: str = "", limit: int = 50
    ) -> List[Dict[str, Any]]:
        if level:
            return await db_manager.query(
                "SELECT * FROM system_logs WHERE level = ? ORDER BY created_at DESC LIMIT ?",
                (level, limit),
            )
        return await db_manager.query(
            "SELECT * FROM system_logs ORDER BY created_at DESC LIMIT ?", (limit,)
        )

    async def log_system(self, level: str, module: str, message: str):
        await db_manager.execute(
            """INSERT INTO system_logs (level, module, message, created_at)
               VALUES (?, ?, ?, ?)""",
            (level, module, message, self._now()),
        )


monitor_service = MonitorService()