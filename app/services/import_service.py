import os
import shutil
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger
from app.config import settings
from app.database.sqlite_db import db_manager
from app.services.parser_service import document_parser
from app.services.embedding_service import embedding_service
from app.services.qdrant_service import qdrant_service


class ImportService:
    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        self.supported_formats = settings.SUPPORTED_FORMATS

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def cleanup_stale_records(self):
        """启动时清理上次异常中断残留的 processing 状态记录"""
        try:
            await db_manager.execute(
                "UPDATE files SET import_status = 'failed' WHERE import_status = 'processing'"
            )
            logger.info("已清理残留的 processing 状态文件记录")
        except Exception as e:
            logger.warning(f"清理残留记录失败: {e}")

    def _sync_encode(self, texts: List[str]) -> List[List[float]]:
        return embedding_service.encode(texts)

    async def create_knowledge_base(self, name: str, description: str = "") -> Dict[str, Any]:
        existing = await db_manager.query_one(
            "SELECT * FROM knowledge_bases WHERE name = ?", (name,)
        )
        if existing:
            return {"success": False, "message": f"知识库 '{name}' 已存在"}

        now = self._now()
        await db_manager.execute(
            "INSERT INTO knowledge_bases (name, description, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, description, now, now),
        )
        await qdrant_service.create_collection(name, description)
        logger.info(f"创建知识库: {name}")
        return {"success": True, "message": f"知识库 '{name}' 创建成功"}

    async def list_knowledge_bases(self) -> List[Dict[str, Any]]:
        kbs = await db_manager.query(
            "SELECT * FROM knowledge_bases ORDER BY created_at DESC"
        )
        result = []
        for kb in kbs:
            doc_count = await db_manager.query_one(
                "SELECT COUNT(*) as cnt FROM files WHERE kb_name = ? AND import_status = 'success'",
                (kb["name"],),
            )
            vectors = await db_manager.query_one(
                "SELECT COALESCE(SUM(vector_count), 0) as cnt FROM files WHERE kb_name = ? AND import_status = 'success'",
                (kb["name"],),
            )
            result.append({
                **kb,
                "doc_count": doc_count["cnt"] if doc_count else 0,
                "vector_count": vectors["cnt"] if vectors else 0,
            })
        return result

    async def get_knowledge_base_detail(self, kb_name: str) -> Optional[Dict[str, Any]]:
        kb = await db_manager.query_one(
            "SELECT * FROM knowledge_bases WHERE name = ?", (kb_name,)
        )
        if not kb:
            return None
        files = await db_manager.query(
            "SELECT * FROM files WHERE kb_name = ? ORDER BY uploaded_at DESC", (kb_name,)
        )
        return {
            "info": kb,
            "files": files,
        }

    async def delete_knowledge_base(self, kb_name: str) -> Dict[str, Any]:
        kb = await db_manager.query_one(
            "SELECT * FROM knowledge_bases WHERE name = ?", (kb_name,)
        )
        if not kb:
            return {"success": False, "message": "知识库不存在"}

        files = await db_manager.query(
            "SELECT file_path FROM files WHERE kb_name = ?", (kb_name,)
        )
        for f in files:
            try:
                if os.path.exists(f["file_path"]):
                    os.remove(f["file_path"])
            except Exception:
                pass

        await db_manager.execute("DELETE FROM files WHERE kb_name = ?", (kb_name,))
        await db_manager.execute("DELETE FROM knowledge_bases WHERE name = ?", (kb_name,))
        await qdrant_service.delete_collection(kb_name)
        logger.info(f"删除知识库: {kb_name}")
        return {"success": True, "message": "知识库删除成功"}

    async def import_file(
        self,
        kb_name: str,
        file_path: str,
        file_name: Optional[str] = None,
        task_id: Optional[int] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        chunk_separator: Optional[str] = None,
    ) -> Dict[str, Any]:
        file_name = file_name or os.path.basename(file_path)
        result = {
            "file_name": file_name,
            "status": "failed",
            "error_reason": "",
            "file_id": None,
            "chunk_count": 0,
        }

        try:
            is_valid, msg = document_parser.validate_file(file_path)
            if not is_valid:
                result["error_reason"] = msg
                await self._record_task_file(task_id, file_name, "skipped", msg)
                logger.warning(f"文件校验失败 {file_name}: {msg}")
                return result

            file_md5 = document_parser.compute_md5(file_path)
            existing_dedup = await db_manager.query_one(
                "SELECT * FROM dedup_records WHERE file_md5 = ? AND kb_name = ?",
                (file_md5, kb_name),
            )
            if existing_dedup:
                result["status"] = "skipped"
                result["error_reason"] = "文件重复，已跳过"
                await self._record_task_file(task_id, file_name, "skipped", "文件重复")
                return result

            ext = document_parser._get_extension(file_path)
            file_size = os.path.getsize(file_path)
            now = self._now()

            kb_dir = os.path.join(self.upload_dir, kb_name)
            os.makedirs(kb_dir, exist_ok=True)
            dest_path = os.path.join(kb_dir, f"{file_md5}_{file_name}")
            shutil.copy2(file_path, dest_path)

            await db_manager.execute(
                """INSERT INTO files 
                   (kb_name, file_name, file_path, file_size, file_format, 
                    chunk_count, vector_count, import_status, md5_hash, uploaded_at)
                   VALUES (?, ?, ?, ?, ?, 0, 0, 'processing', ?, ?)""",
                (kb_name, file_name, dest_path, file_size, ext, file_md5, now),
            )
            file_record = await db_manager.query_one(
                "SELECT id FROM files WHERE md5_hash = ? AND kb_name = ?", (file_md5, kb_name)
            )
            file_id = file_record["id"] if file_record else None
            result["file_id"] = file_id

            parsed_data, parse_msg = document_parser.parse(dest_path)
            if parsed_data is None:
                result["error_reason"] = parse_msg
                result["status"] = "failed"
                await db_manager.execute(
                    "UPDATE files SET import_status = 'failed' WHERE id = ?", (file_id,)
                )
                await self._record_task_file(task_id, file_name, "failed", parse_msg)
                return result

            chunks = document_parser.chunk_text(parsed_data, file_id,
                                                   chunk_size=chunk_size,
                                                   chunk_overlap=chunk_overlap,
                                                   chunk_separator=chunk_separator)
            if not chunks:
                result["status"] = "skipped"
                result["error_reason"] = "文件无有效内容"
                await db_manager.execute(
                    "UPDATE files SET import_status = 'skipped' WHERE id = ?", (file_id,)
                )
                await self._record_task_file(task_id, file_name, "skipped", "文件无有效内容")
                return result

            texts = [c["text"] for c in chunks]
            loop = asyncio.get_running_loop()
            embeddings = await loop.run_in_executor(None, self._sync_encode, texts)

            if embeddings and len(embeddings[0]) != settings.EMBEDDING_DIM:
                actual_dim = len(embeddings[0])
                logger.error(
                    f"嵌入维度({actual_dim})与配置维度({settings.EMBEDDING_DIM})不匹配，跳过文件 {file_name}"
                )
                result["status"] = "failed"
                result["error_reason"] = f"向量维度不匹配: 模型输出{actual_dim}维, 配置{settings.EMBEDDING_DIM}维"
                await db_manager.execute(
                    "UPDATE files SET import_status = 'failed' WHERE id = ?", (file_id,)
                )
                await self._record_task_file(task_id, file_name, "failed", result["error_reason"])
                return result

            points = []
            for i, chunk in enumerate(chunks):
                chunk["vector"] = embeddings[i]
                payload = {
                    "chunk_id": chunk["chunk_id"],
                    "file_name": file_name,
                    "file_id": file_id,
                    "kb_name": kb_name,
                    "index": chunk["index"],
                    "text": chunk["text"],
                    "is_table": chunk.get("is_table", False),
                    "is_chart": chunk.get("is_chart", False),
                    "uploaded_at": now,
                }
                points.append({
                    "id": chunk["chunk_id"],
                    "vector": embeddings[i],
                    "payload": payload,
                })

            success = await qdrant_service.insert_points(kb_name, points)
            if success:
                await db_manager.execute(
                    """UPDATE files 
                       SET chunk_count = ?, vector_count = ?, import_status = 'success' 
                       WHERE id = ?""",
                    (len(chunks), len(chunks), file_id),
                )
                await db_manager.execute(
                    """INSERT OR IGNORE INTO dedup_records (file_md5, file_name, kb_name, file_size, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (file_md5, file_name, kb_name, file_size, now),
                )
                result["status"] = "success"
                result["chunk_count"] = len(chunks)
                await self._record_task_file(task_id, file_name, "success", "")
                logger.info(f"文件导入成功 {file_name}: {len(chunks)}个切片")
            else:
                await db_manager.execute(
                    "UPDATE files SET import_status = 'failed' WHERE id = ?", (file_id,)
                )
                result["status"] = "failed"
                result["error_reason"] = "向量入库失败"
                await self._record_task_file(task_id, file_name, "failed", "向量入库失败")

        except Exception as e:
            logger.error(f"文件导入异常 {file_name}: {e}")
            result["status"] = "failed"
            result["error_reason"] = str(e)
            if task_id:
                await self._record_task_file(task_id, file_name, "failed", str(e))

        return result

    async def batch_import(
        self,
        kb_name: str,
        file_paths: List[str],
        task_type: str = "batch",
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        chunk_separator: Optional[str] = None,
    ) -> Dict[str, Any]:
        task_id = await db_manager.execute(
            """INSERT INTO import_tasks 
               (kb_name, task_type, total_files, status, created_at)
               VALUES (?, ?, ?, 'running', ?)""",
            (kb_name, task_type, len(file_paths), self._now()),
        )

        results = []
        success_count = 0
        fail_count = 0
        skip_count = 0

        for file_path in file_paths:
            result = await self.import_file(kb_name, file_path, task_id=task_id,
                                            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                                            chunk_separator=chunk_separator)
            results.append(result)
            if result["status"] == "success":
                success_count += 1
            elif result["status"] == "skipped":
                skip_count += 1
            else:
                fail_count += 1

        now = self._now()
        await db_manager.execute(
            """UPDATE import_tasks 
               SET success_count = ?, fail_count = ?, skip_count = ?, 
                   status = 'completed', finished_at = ?
               WHERE id = ?""",
            (success_count, fail_count, skip_count, now, task_id),
        )

        return {
            "task_id": task_id,
            "total": len(file_paths),
            "success": success_count,
            "failed": fail_count,
            "skipped": skip_count,
            "results": results,
        }

    async def _record_task_file(
        self, task_id: Optional[int], file_name: str, status: str, error_reason: str
    ):
        if not task_id:
            return
        now = self._now()
        await db_manager.execute(
            """INSERT INTO import_task_files 
               (task_id, file_name, status, error_reason, processed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (task_id, file_name, status, error_reason, now),
        )

    async def get_import_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        task = await db_manager.query_one(
            "SELECT * FROM import_tasks WHERE id = ?", (task_id,)
        )
        if not task:
            return None
        files = await db_manager.query(
            "SELECT * FROM import_task_files WHERE task_id = ? ORDER BY id", (task_id,)
        )
        return {"task": task, "files": files}

    async def list_import_tasks(self, kb_name: Optional[str] = None) -> List[Dict[str, Any]]:
        if kb_name:
            return await db_manager.query(
                "SELECT * FROM import_tasks WHERE kb_name = ? ORDER BY created_at DESC",
                (kb_name,),
            )
        return await db_manager.query(
            "SELECT * FROM import_tasks ORDER BY created_at DESC"
        )

    async def list_files(self, kb_name: str) -> List[Dict[str, Any]]:
        return await db_manager.query(
            "SELECT * FROM files WHERE kb_name = ? ORDER BY uploaded_at DESC", (kb_name,)
        )

    async def delete_file(self, kb_name: str, file_id: int) -> Dict[str, Any]:
        file_record = await db_manager.query_one(
            "SELECT * FROM files WHERE id = ? AND kb_name = ?", (file_id, kb_name)
        )
        if not file_record:
            return {"success": False, "message": "文件不存在"}

        await qdrant_service.delete_points_by_file(kb_name, file_record["file_name"])
        try:
            if os.path.exists(file_record["file_path"]):
                os.remove(file_record["file_path"])
        except Exception:
            pass

        await db_manager.execute("DELETE FROM files WHERE id = ?", (file_id,))
        await db_manager.execute(
            "DELETE FROM dedup_records WHERE file_md5 = ? AND kb_name = ?",
            (file_record["md5_hash"], kb_name),
        )
        return {"success": True, "message": "文件删除成功"}

    async def get_file_chunks(self, kb_name: str, file_id: int) -> Dict[str, Any]:
        file_record = await db_manager.query_one(
            "SELECT * FROM files WHERE id = ? AND kb_name = ?", (file_id, kb_name)
        )
        if not file_record:
            return {}

        chunks = await qdrant_service.search(
            collection_name=kb_name,
            query_vector=[0.0] * settings.EMBEDDING_DIM,
            top_k=1000,
            filters={"file_id": file_id},
        )
        return {
            "file": file_record,
            "chunks": chunks,
        }

    async def update_chunk(self, kb_name: str, chunk_id: str, new_text: str) -> Dict[str, Any]:
        """编辑切片内容：重新向量化并更新 Qdrant 中的点和 payload"""
        point = await qdrant_service.get_point(kb_name, chunk_id)
        if not point:
            return {"success": False, "message": "切片不存在"}

        payload = point.get("payload", {})
        old_text = payload.get("text", "")

        loop = asyncio.get_running_loop()
        new_vector = await loop.run_in_executor(None, embedding_service.encode_single, new_text)

        if len(new_vector) != settings.EMBEDDING_DIM:
            return {"success": False, "message": f"向量维度不匹配: {len(new_vector)} vs {settings.EMBEDDING_DIM}"}

        payload["text"] = new_text
        payload["edited_at"] = self._now()

        success = await qdrant_service.update_point(kb_name, chunk_id, new_vector, payload)
        if success:
            logger.info(f"切片编辑成功: {chunk_id}, 旧文本{len(old_text)}字 -> 新文本{len(new_text)}字")
            return {"success": True, "message": "切片编辑成功", "chunk_id": chunk_id}
        else:
            return {"success": False, "message": "切片更新失败"}

    async def delete_chunk(self, kb_name: str, chunk_id: str) -> Dict[str, Any]:
        """删除单个切片：从 Qdrant 删除点，并更新文件的 chunk_count"""
        point = await qdrant_service.get_point(kb_name, chunk_id)
        if not point:
            return {"success": False, "message": "切片不存在"}

        payload = point.get("payload", {})
        file_id = payload.get("file_id")

        success = await qdrant_service.delete_point(kb_name, chunk_id)
        if not success:
            return {"success": False, "message": "切片删除失败"}

        if file_id:
            await db_manager.execute(
                """UPDATE files SET chunk_count = MAX(0, chunk_count - 1),
                   vector_count = MAX(0, vector_count - 1) WHERE id = ?""",
                (file_id,),
            )

        logger.info(f"切片删除成功: {chunk_id}, file_id={file_id}")
        return {"success": True, "message": "切片删除成功"}


import_service = ImportService()