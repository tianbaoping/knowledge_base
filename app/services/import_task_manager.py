"""
导入任务管理器

管理文件导入任务的生命周期，支持:
- 任务创建和状态追踪
- 进度更新
- WebSocket 实时推送
- 任务历史查询
"""
import asyncio
import json
import time
import uuid
from typing import Dict, Any, List, Optional, Set
from loguru import logger
from fastapi import WebSocket


class ImportTask:
    """导入任务"""

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    def __init__(self, task_id: str, kb_name: str):
        self.task_id = task_id
        self.kb_name = kb_name
        self.status = self.STATUS_PENDING
        self.created_at = time.time()
        self.started_at = None
        self.completed_at = None
        self.error = None
        self.files: List[Dict[str, Any]] = []  # 每个文件的进度
        self.total_files = 0
        self.processed_files = 0

    def update_file_progress(self, file_name: str, stage: str, progress: float,
                              message: str = "", needs_ocr: bool = False,
                              error: str = None):
        """更新单个文件的进度"""
        # 查找或创建文件记录
        file_record = None
        for f in self.files:
            if f["file_name"] == file_name:
                file_record = f
                break

        if file_record is None:
            file_record = {
                "file_name": file_name,
                "stage": stage,
                "progress": progress,
                "message": message,
                "needs_ocr": needs_ocr,
                "error": error,
                "completed": False,
            }
            self.files.append(file_record)

        file_record["stage"] = stage
        file_record["progress"] = progress
        file_record["message"] = message
        file_record["needs_ocr"] = needs_ocr
        if error:
            file_record["error"] = error
        if stage == "complete" or stage == "error":
            file_record["completed"] = True
            self.processed_files += 1

        # 更新任务状态
        all_completed = all(f.get("completed", False) for f in self.files)
        if all_completed and self.files:
            has_errors = any(f.get("error") for f in self.files)
            self.status = self.STATUS_FAILED if has_errors else self.STATUS_COMPLETED
            self.completed_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        elapsed = 0
        if self.started_at:
            end = self.completed_at or time.time()
            elapsed = round(end - self.started_at, 2)

        return {
            "task_id": self.task_id,
            "kb_name": self.kb_name,
            "status": self.status,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "progress": round(
                self.processed_files / self.total_files * 100
                if self.total_files > 0 else 0, 1
            ),
            "elapsed_seconds": elapsed,
            "error": self.error,
            "files": self.files,
        }


class ImportTaskManager:
    """导入任务管理器"""

    def __init__(self):
        self._tasks: Dict[str, ImportTask] = {}
        self._websockets: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._max_history = 100  # 最多保存100个历史任务

    async def create_task(self, kb_name: str) -> ImportTask:
        """创建新的导入任务"""
        task_id = str(uuid.uuid4())[:8]
        task = ImportTask(task_id, kb_name)
        task.status = ImportTask.STATUS_PROCESSING
        task.started_at = time.time()

        async with self._lock:
            self._tasks[task_id] = task

        # 清理过期任务
        self._cleanup_old_tasks()

        # 推送任务创建事件
        await self._broadcast({
            "type": "task_created",
            "task_id": task_id,
            "data": task.to_dict(),
        })

        logger.info(f"导入任务已创建: {task_id}, 知识库: {kb_name}")
        return task

    async def update_progress(self, task_id: str, file_name: str,
                               stage: str, progress: float, message: str = "",
                               needs_ocr: bool = False, error: str = None):
        """更新任务进度"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.update_file_progress(file_name, stage, progress, message,
                                      needs_ocr, error)
            task_data = task.to_dict()

        # 推送进度更新
        await self._broadcast({
            "type": "progress_update",
            "task_id": task_id,
            "data": task_data,
        })

    async def complete_task(self, task_id: str, error: str = None):
        """标记任务完成"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return

            if error:
                task.status = ImportTask.STATUS_FAILED
                task.error = error
            else:
                task.status = ImportTask.STATUS_COMPLETED

            task.completed_at = time.time()
            task_data = task.to_dict()

        # 推送完成事件
        await self._broadcast({
            "type": "task_completed" if not error else "task_failed",
            "task_id": task_id,
            "data": task_data,
        })

        logger.info(f"导入任务完成: {task_id}, 状态: {task.status}")

    async def add_file(self, task_id: str, file_name: str):
        """添加文件到任务"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.total_files += 1
            task.files.append({
                "file_name": file_name,
                "stage": "init",
                "progress": 0,
                "message": "等待处理...",
                "needs_ocr": False,
                "error": None,
                "completed": False,
            })
            task_data = task.to_dict()

        await self._broadcast({
            "type": "progress_update",
            "task_id": task_id,
            "data": task_data,
        })

    def get_task(self, task_id: str) -> Optional[ImportTask]:
        """获取任务"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务"""
        return [task.to_dict() for task in self._tasks.values()]

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """获取活跃任务（进行中）"""
        return [
            task.to_dict() for task in self._tasks.values()
            if task.status == ImportTask.STATUS_PROCESSING
        ]

    async def register_websocket(self, websocket: WebSocket):
        """注册 WebSocket 连接"""
        await websocket.accept()
        self._websockets.add(websocket)
        logger.info(f"WebSocket 客户端已连接，当前连接数: {len(self._websockets)}")

        # 发送当前所有任务状态
        await websocket.send_json({
            "type": "init",
            "tasks": self.get_all_tasks(),
        })

    async def unregister_websocket(self, websocket: WebSocket):
        """注销 WebSocket 连接"""
        self._websockets.discard(websocket)
        logger.info(f"WebSocket 客户端已断开，当前连接数: {len(self._websockets)}")

    async def _broadcast(self, message: Dict[str, Any]):
        """广播消息到所有 WebSocket 客户端"""
        if not self._websockets:
            return

        disconnected = set()
        for ws in self._websockets:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)

        # 清理断开的连接
        for ws in disconnected:
            self._websockets.discard(ws)

    def _cleanup_old_tasks(self):
        """清理旧任务"""
        if len(self._tasks) > self._max_history:
            # 按创建时间排序，删除最旧的
            sorted_tasks = sorted(
                self._tasks.items(),
                key=lambda x: x[1].created_at
            )
            to_remove = sorted_tasks[:len(self._tasks) - self._max_history]
            for task_id, _ in to_remove:
                del self._tasks[task_id]


import_task_manager = ImportTaskManager()
