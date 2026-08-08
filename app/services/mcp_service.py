import json
import time
import asyncio
from typing import List, Dict, Any, Optional
from loguru import logger
from app.config import settings
from app.services.embedding_service import embedding_service
from app.services.qdrant_service import qdrant_service
from app.services.import_service import import_service
from app.services.monitor_service import monitor_service
from app.services.reranker_service import reranker_service
from app.database.sqlite_db import db_manager


class MCPService:
    def __init__(self):
        self.api_key = settings.MCP_API_KEY
        self.start_time = time.time()

    def verify_api_key(self, api_key: Optional[str]) -> bool:
        if not api_key:
            return False
        return api_key == self.api_key

    def _sync_encode_single(self, query: str) -> List[float]:
        return embedding_service.encode_single(query)

    async def search(
        self,
        query: str,
        kb_name: Optional[str] = None,
        top_k: int = 5,
        score_threshold: float = 0.3,
        use_reranker: Optional[bool] = None,
        reranker_recall_top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        import time
        t_start = time.time()
        try:
            model_info = embedding_service.get_model_info()
            reranker_info = reranker_service.get_model_info()

            if use_reranker is None:
                use_reranker = settings.RERANKER_ENABLED

            # 解析召回数量: 传入值 > 配置默认值 > top_k
            if use_reranker:
                recall_top_k = reranker_recall_top_k or settings.RERANKER_RECALL_TOP_K
                if recall_top_k < top_k:
                    recall_top_k = top_k
            else:
                recall_top_k = top_k

            loop = asyncio.get_running_loop()
            t_embed_start = time.time()
            query_vector = await loop.run_in_executor(
                None, self._sync_encode_single, query
            )
            t_embed = round((time.time() - t_embed_start) * 1000, 1)

            if kb_name:
                collections = [kb_name]
            else:
                colls = await qdrant_service.list_collections()
                collections = [c["name"] for c in colls]

            # Phase 1: Vector recall (recall_top_k already resolved above)
            t_search_start = time.time()
            all_results = []
            for collection in collections:
                results = await qdrant_service.search(
                    collection_name=collection,
                    query_vector=query_vector,
                    top_k=recall_top_k,
                    score_threshold=score_threshold,
                )
                for r in results:
                    r["collection"] = collection
                    all_results.append(r)

            all_results.sort(key=lambda x: x["score"], reverse=True)
            all_results = all_results[:recall_top_k]
            t_search = round((time.time() - t_search_start) * 1000, 1)

            # Phase 2: Reranker refinement
            t_rerank = 0.0
            if use_reranker and len(all_results) > 1:
                t_rerank_start = time.time()
                documents = [r.get("payload", {}).get("text", "") for r in all_results]
                try:
                    rerank_results = await loop.run_in_executor(
                        None, reranker_service.rerank, query, documents, top_k
                    )
                    reranked = []
                    for idx, score in rerank_results:
                        if idx < len(all_results):
                            item = all_results[idx]
                            item["rerank_score"] = score
                            item["score"] = score
                            reranked.append(item)
                    all_results = reranked
                    t_rerank = round((time.time() - t_rerank_start) * 1000, 1)
                    logger.info(f"Reranker 重排完成: {len(documents)} -> {len(all_results)} 条, 耗时 {t_rerank}ms")
                except Exception as e:
                    logger.warning(f"Reranker 重排失败，使用原始向量排序: {e}")
                    all_results = all_results[:top_k]
                    t_rerank = round((time.time() - t_rerank_start) * 1000, 1)
            else:
                all_results = all_results[:top_k]

            t_total = round((time.time() - t_start) * 1000, 1)

            scores = [r.get("score", 0) for r in all_results]
            retrieval_info = {
                "method": "向量语义检索" if not model_info.get("demo_mode") else "演示模式(Mock)",
                "model_name": model_info.get("model_name", "unknown"),
                "model_local_path": model_info.get("local_path", ""),
                "vector_dim": model_info.get("embedding_dim", settings.EMBEDDING_DIM),
                "demo_mode": model_info.get("demo_mode", False),
                "distance_metric": "余弦相似度 (Cosine)",
                "collections_searched": collections,
                "collections_count": len(collections),
                "vector_db": "Qdrant (本地模式)",
                "query_vector_preview": [round(v, 4) for v in query_vector[:8]],
                "query_vector_full_dim": len(query_vector),
                "top_k": top_k,
                "recall_top_k": recall_top_k,
                "score_threshold": score_threshold,
                "use_reranker": use_reranker,
                "reranker_model": reranker_info.get("model_name", ""),
                "reranker_demo_mode": reranker_info.get("demo_mode", False),
                "max_score": max(scores) if scores else 0,
                "min_score": min(scores) if scores else 0,
                "avg_score": round(sum(scores) / len(scores), 4) if scores else 0,
                "embed_time_ms": t_embed,
                "search_time_ms": t_search,
                "rerank_time_ms": t_rerank,
                "total_time_ms": t_total,
            }

            return {
                "query": query,
                "results": all_results,
                "total": len(all_results),
                "retrieval_info": retrieval_info,
            }
        except Exception as e:
            logger.error(f"MCP搜索失败: {e}")
            return {"query": query, "results": [], "total": 0, "error": str(e)}

    async def list_knowledge_bases(self) -> List[Dict[str, Any]]:
        colls = await qdrant_service.list_collections()
        result = []
        for c in colls:
            kb_info = await db_manager.query_one(
                "SELECT * FROM knowledge_bases WHERE name = ?", (c["name"],)
            )
            result.append({
                "name": c["name"],
                "description": kb_info.get("description", "") if kb_info else "",
                "vectors_count": c.get("vectors_count", 0),
                "points_count": c.get("points_count", 0),
                "status": c.get("status", "unknown"),
            })
        return result

    async def get_document_detail(self, kb_name: str, chunk_id: str) -> Optional[Dict[str, Any]]:
        results = await qdrant_service.search(
            collection_name=kb_name,
            query_vector=[0.0] * settings.EMBEDDING_DIM,
            top_k=100,
            filters={"chunk_id": chunk_id},
        )
        if results:
            return results[0]

        if chunk_id.startswith("file_"):
            try:
                file_id = int(chunk_id.replace("file_", ""))
                results = await qdrant_service.search(
                    collection_name=kb_name,
                    query_vector=[0.0] * settings.EMBEDDING_DIM,
                    top_k=1000,
                    filters={"file_id": file_id},
                )
                if results:
                    return {
                        "chunks": results,
                        "total": len(results),
                    }
            except ValueError:
                pass

        return None

    async def get_file_content(self, kb_name: str, file_id: int) -> Optional[Dict[str, Any]]:
        file_record = await db_manager.query_one(
            "SELECT * FROM files WHERE id = ? AND kb_name = ?", (file_id, kb_name)
        )
        if not file_record:
            return None
        return {
            "file": file_record,
            "content": "",
        }

    # ==================== 知识库管理工具 ====================

    async def create_knowledge_base(self, name: str, description: str = "") -> Dict[str, Any]:
        return await import_service.create_knowledge_base(name, description)

    async def get_knowledge_base_detail(self, kb_name: str) -> Optional[Dict[str, Any]]:
        return await import_service.get_knowledge_base_detail(kb_name)

    async def delete_knowledge_base(self, kb_name: str) -> Dict[str, Any]:
        return await import_service.delete_knowledge_base(kb_name)

    # ==================== 文件管理工具 ====================

    async def list_files(self, kb_name: str) -> List[Dict[str, Any]]:
        return await import_service.list_files(kb_name)

    async def delete_file(self, kb_name: str, file_id: int) -> Dict[str, Any]:
        return await import_service.delete_file(kb_name, file_id)

    async def get_file_chunks(self, kb_name: str, file_id: int) -> Dict[str, Any]:
        return await import_service.get_file_chunks(kb_name, file_id)

    # ==================== 切片管理工具 ====================

    async def update_chunk(self, kb_name: str, chunk_id: str, text: str) -> Dict[str, Any]:
        """编辑切片内容：重新向量化并更新 Qdrant 中的点和 payload"""
        return await import_service.update_chunk(kb_name, chunk_id, text)

    async def delete_chunk(self, kb_name: str, chunk_id: str) -> Dict[str, Any]:
        """删除单个切片：从 Qdrant 删除点并更新文件 chunk_count"""
        return await import_service.delete_chunk(kb_name, chunk_id)

    # ==================== 文件导入工具 ====================

    async def import_single_file(
        self,
        kb_name: str,
        file_path: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Dict[str, Any]:
        import os
        if not os.path.exists(file_path):
            return {"success": False, "message": f"文件不存在: {file_path}"}
        result = await import_service.import_file(
            kb_name=kb_name,
            file_path=file_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        return {
            "success": result.get("status") == "success",
            "status": result.get("status"),
            "file_name": result.get("file_name"),
            "file_id": result.get("file_id"),
            "chunk_count": result.get("chunk_count"),
            "error_reason": result.get("error_reason", ""),
        }

    async def import_batch_files(
        self,
        kb_name: str,
        file_paths: List[str],
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Dict[str, Any]:
        import os
        valid_paths = [p for p in file_paths if os.path.exists(p)]
        if not valid_paths:
            return {"success": False, "message": "没有可导入的有效文件路径"}
        return await import_service.batch_import(
            kb_name=kb_name,
            file_paths=valid_paths,
            task_type="batch",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    async def import_zip_file(
        self,
        kb_name: str,
        zip_path: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Dict[str, Any]:
        import os
        import zipfile
        import shutil
        if not os.path.exists(zip_path):
            return {"success": False, "message": f"ZIP 文件不存在: {zip_path}"}
        ext = os.path.splitext(zip_path)[1].lower().lstrip(".")
        if ext != "zip":
            return {"success": False, "message": f"仅支持 .zip 文件，当前: {ext}"}
        temp_dir = os.path.join(settings.UPLOAD_DIR, f"mcp_zip_{uuid.uuid4().hex[:12]}")
        os.makedirs(temp_dir, exist_ok=True)
        try:
            extracted_files = []
            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in zf.namelist():
                    full_path = os.path.abspath(os.path.join(temp_dir, name))
                    if not full_path.startswith(os.path.abspath(temp_dir) + os.sep):
                        logger.warning(f"跳过可疑路径: {name}")
                        continue
                    zf.extract(name, temp_dir)
                    if os.path.isfile(full_path):
                        file_ext = os.path.splitext(name)[1].lower().lstrip(".")
                        if file_ext in settings.SUPPORTED_FORMATS:
                            extracted_files.append(full_path)
            if not extracted_files:
                return {"success": False, "message": "压缩包中没有可导入的文件"}
            return await import_service.batch_import(
                kb_name=kb_name,
                file_paths=extracted_files,
                task_type="zip",
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    # ==================== 导入任务工具 ====================

    async def list_import_tasks(self, kb_name: Optional[str] = None) -> List[Dict[str, Any]]:
        return await import_service.list_import_tasks(kb_name)

    async def get_import_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        return await import_service.get_import_task(task_id)

    # ==================== 系统监控工具 ====================

    async def get_system_status(self) -> Dict[str, Any]:
        return await monitor_service.get_system_status()

    async def get_resource_info(self) -> Dict[str, Any]:
        return await monitor_service.get_resource_info()

    async def health_check(self) -> Dict[str, Any]:
        qdrant_status = await qdrant_service.health_check()
        uptime = int(time.time() - self.start_time)
        return {
            "status": "healthy",
            "service": "knowledge-base-mcp",
            "version": settings.APP_VERSION,
            "uptime_seconds": uptime,
            "qdrant": qdrant_status,
            "embedding_model": embedding_service.get_model_info(),
            "reranker_model": reranker_service.get_model_info(),
        }

    async def get_mcp_tools(self) -> List[Dict[str, Any]]:
        return [
            # ---- 检索类 ----
            {
                "name": "knowledge_search",
                "description": "搜索私有知识库，返回与问题最相关的文本片段。支持指定知识库或跨库检索。支持 Reranker 重排序优化。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "用户的搜索问题",
                        },
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称，为空则搜索所有知识库",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "最终返回结果数量，默认5，最大50",
                            "default": 5,
                        },
                        "score_threshold": {
                            "type": "number",
                            "description": "相似度阈值(0-1)，默认0.3，低于此值的结果不返回",
                            "default": 0.3,
                        },
                        "use_reranker": {
                            "type": "boolean",
                            "description": "是否使用 Reranker 重排序（默认true）。开启后先召回指定数量再精排返回top_k条",
                            "default": True,
                        },
                        "reranker_recall_top_k": {
                            "type": "integer",
                            "description": "Reranker第一阶段向量召回数量，默认10，需>=top_k，最大200",
                            "default": None,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_document_detail",
                "description": "根据切片ID查询对应的原文内容，用于检索结果溯源",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称",
                        },
                        "chunk_id": {
                            "type": "string",
                            "description": "切片ID (从 search 结果中获取)",
                        },
                    },
                    "required": ["kb_name", "chunk_id"],
                },
            },
            # ---- 知识库管理类 ----
            {
                "name": "list_knowledge_bases",
                "description": "查询所有可用的知识库集合信息，包括向量数量、状态等",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "create_knowledge_base",
                "description": "创建一个新的知识库",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "知识库名称 (1-100字符)",
                        },
                        "description": {
                            "type": "string",
                            "description": "知识库描述 (可选)",
                            "default": "",
                        },
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "get_knowledge_base_detail",
                "description": "获取知识库详情，包括知识库信息和所有文件列表",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称",
                        },
                    },
                    "required": ["kb_name"],
                },
            },
            {
                "name": "delete_knowledge_base",
                "description": "删除知识库及其所有文件和向量数据 (不可恢复)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称",
                        },
                    },
                    "required": ["kb_name"],
                },
            },
            # ---- 文件管理类 ----
            {
                "name": "list_files",
                "description": "列出知识库中的所有文件记录",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称",
                        },
                    },
                    "required": ["kb_name"],
                },
            },
            {
                "name": "delete_file",
                "description": "删除知识库中的指定文件及其所有向量",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称",
                        },
                        "file_id": {
                            "type": "integer",
                            "description": "文件ID",
                        },
                    },
                    "required": ["kb_name", "file_id"],
                },
            },
            {
                "name": "get_file_chunks",
                "description": "获取指定文件的所有切片内容，用于查看文件被切分后的具体内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称",
                        },
                        "file_id": {
                            "type": "integer",
                            "description": "文件ID",
                        },
                    },
                    "required": ["kb_name", "file_id"],
                },
            },
            # ---- 切片管理类 ----
            {
                "name": "update_chunk",
                "description": "编辑指定切片的文本内容，系统会自动重新向量化并更新向量数据库",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称",
                        },
                        "chunk_id": {
                            "type": "string",
                            "description": "切片ID (从 get_file_chunks 或 search 结果中获取)",
                        },
                        "text": {
                            "type": "string",
                            "description": "修改后的切片文本内容",
                        },
                    },
                    "required": ["kb_name", "chunk_id", "text"],
                },
            },
            {
                "name": "delete_chunk",
                "description": "删除指定的切片，从向量数据库中永久移除该切片 (不可恢复)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称",
                        },
                        "chunk_id": {
                            "type": "string",
                            "description": "切片ID (从 get_file_chunks 或 search 结果中获取)",
                        },
                    },
                    "required": ["kb_name", "chunk_id"],
                },
            },
            # ---- 文件导入类 ----
            {
                "name": "import_single_file",
                "description": "从服务器本地文件路径导入单个文件到知识库。支持格式: pdf/docx/txt/md。注意: file_path 必须是服务器上的绝对路径",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "服务器上的文件绝对路径，如 /data/docs/handbook.pdf",
                        },
                        "chunk_size": {
                            "type": "integer",
                            "description": "切片长度(字符数)，默认500",
                            "default": 500,
                        },
                        "chunk_overlap": {
                            "type": "integer",
                            "description": "切片重叠长度(字符数)，默认50",
                            "default": 50,
                        },
                    },
                    "required": ["kb_name", "file_path"],
                },
            },
            {
                "name": "import_batch_files",
                "description": "从服务器本地批量导入多个文件到知识库。传入文件路径列表，逐个处理并返回批量统计",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称",
                        },
                        "file_paths": {
                            "type": "array",
                            "description": "服务器上的文件绝对路径列表，如 [\"/data/d1.pdf\", \"/data/d2.pdf\"]",
                            "items": { "type": "string" },
                        },
                        "chunk_size": {
                            "type": "integer",
                            "description": "切片长度(字符数)，默认500",
                            "default": 500,
                        },
                        "chunk_overlap": {
                            "type": "integer",
                            "description": "切片重叠长度(字符数)，默认50",
                            "default": 50,
                        },
                    },
                    "required": ["kb_name", "file_paths"],
                },
            },
            {
                "name": "import_zip_file",
                "description": "从服务器本地 ZIP 压缩包批量导入文件到知识库。自动解压并导入所有支持格式的文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称",
                        },
                        "zip_path": {
                            "type": "string",
                            "description": "服务器上的 ZIP 文件绝对路径，如 /data/batch_docs.zip",
                        },
                        "chunk_size": {
                            "type": "integer",
                            "description": "切片长度(字符数)，默认500",
                            "default": 500,
                        },
                        "chunk_overlap": {
                            "type": "integer",
                            "description": "切片重叠长度(字符数)，默认50",
                            "default": 50,
                        },
                    },
                    "required": ["kb_name", "zip_path"],
                },
            },
            # ---- 导入任务类 ----
            {
                "name": "list_import_tasks",
                "description": "查询导入任务列表，可按知识库筛选",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kb_name": {
                            "type": "string",
                            "description": "知识库名称 (可选，为空则返回所有)",
                        },
                    },
                },
            },
            {
                "name": "get_import_task",
                "description": "查询导入任务详情，包括任务状态和每个文件的处理结果",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                            "description": "任务ID",
                        },
                    },
                    "required": ["task_id"],
                },
            },
            # ---- 系统监控类 ----
            {
                "name": "service_health_check",
                "description": "检测知识库服务是否正常运行，包括 Qdrant 状态和嵌入模型状态",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "get_system_status",
                "description": "获取系统状态概览，包括知识库数、文件数、向量数、今日导入数等",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "get_resource_info",
                "description": "获取系统资源使用情况，包括磁盘、内存、向量存储大小等",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]


mcp_service = MCPService()