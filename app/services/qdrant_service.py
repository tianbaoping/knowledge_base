import asyncio
import os
import signal
import subprocess
from qdrant_client import QdrantClient, models
from typing import List, Dict, Any, Optional, Callable
from loguru import logger
from app.config import settings


class QdrantService:
    def __init__(self):
        self.client: Optional[QdrantClient] = None
        self.embedding_dim = settings.EMBEDDING_DIM

    async def init(self):
        try:
            await self._connect()
        except Exception as e:
            error_msg = str(e)
            if "already accessed" in error_msg or "another instance" in error_msg:
                logger.warning(f"Qdrant存储目录被占用，尝试自动清理残留进程...")
                if await self._kill_stale_processes():
                    logger.info("残留进程已清理，等待锁释放后重试连接...")
                    await asyncio.sleep(1.5)
                    await self._connect()
                    return
                else:
                    logger.error("无法自动清理残留进程，请手动终止占用 data/qdrant 的进程")
            raise

    async def _connect(self):
        """创建 Qdrant 客户端并验证连接"""
        if settings.QDRANT_LOCATION:
            self.client = QdrantClient(
                path=settings.QDRANT_LOCATION,
            )
            logger.info(f"Qdrant本地模式启动成功: {settings.QDRANT_LOCATION}")
        else:
            self.client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                grpc_port=settings.QDRANT_GRPC_PORT,
            )
        collections = await self._run_sync(self.client.get_collections)
        logger.info(f"Qdrant连接成功，现有集合: {[c.name for c in collections.collections]}")

    def _resolve_qdrant_path(self) -> str:
        """获取 Qdrant 存储目录的绝对路径"""
        path = settings.QDRANT_LOCATION
        if not os.path.isabs(path):
            path = os.path.join(settings.BASE_DIR, path)
        return os.path.abspath(path)

    async def _kill_stale_processes(self) -> bool:
        """
        安全检测并终止占用 Qdrant 锁文件的残留进程。
        只针对 Qdrant 的 .lock 文件检测，且只终止本应用的 Python 进程。
        """
        qdrant_path = self._resolve_qdrant_path()
        if not os.path.exists(qdrant_path):
            return False

        lock_file = os.path.join(qdrant_path, ".lock")
        if not os.path.exists(lock_file):
            logger.info("Qdrant锁文件不存在，无需清理")
            return False

        current_pid = os.getpid()
        pids = self._find_pids_holding_file(lock_file)
        if pids is None:
            # fuser/lsof 不可用，尝试直接删除锁文件
            return self._remove_lock_file(qdrant_path)

        # 安全过滤：排除自身、系统进程(PID<=1)，且只保留本应用的 Python 进程
        safe_pids = []
        for pid in pids:
            if pid <= 1 or pid == current_pid:
                continue
            cmdline = self._get_pid_cmdline(pid)
            if cmdline and ("python" in cmdline or "uvicorn" in cmdline) and "app.main" in cmdline:
                safe_pids.append(pid)
            else:
                logger.debug(f"跳过非本应用进程 PID={pid}: {cmdline[:80]}")

        if not safe_pids:
            logger.info("未发现本应用的残留进程，尝试删除锁文件")
            return self._remove_lock_file(qdrant_path)

        logger.warning(f"发现本应用的残留进程: {safe_pids}")
        killed = False
        for pid in safe_pids:
            killed |= self._terminate_pid(pid, signal.SIGTERM)

        if killed:
            await asyncio.sleep(1)
            for pid in safe_pids:
                self._terminate_pid(pid, signal.SIGKILL)
            await asyncio.sleep(0.5)

        return killed

    def _find_pids_holding_file(self, file_path: str) -> Optional[List[int]]:
        """
        查找打开了指定文件的进程 PID 列表。
        注意：绝不使用 fuser -m（会匹配整个文件系统的所有进程）。
        只用 fuser <file>（精确匹配单个文件）或 lsof <file>。
        命令不可用时返回 None。
        """
        # 方式1: fuser <file> (不带 -m，只匹配该文件本身)
        try:
            result = subprocess.run(
                ["fuser", file_path],
                capture_output=True, text=True, timeout=5,
            )
            raw = (result.stdout + result.stderr).strip()
            pids = []
            for token in raw.split():
                token = token.strip("efrcm ")
                try:
                    pids.append(int(token))
                except ValueError:
                    continue
            if pids:
                return pids
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"fuser 查询失败: {e}")

        # 方式2: lsof <file>
        try:
            result = subprocess.run(
                ["lsof", "-t", file_path],
                capture_output=True, text=True, timeout=5,
            )
            pids = []
            for token in result.stdout.strip().split():
                try:
                    pids.append(int(token))
                except ValueError:
                    continue
            return pids
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.debug(f"lsof 查询失败: {e}")
            return []

    def _get_pid_cmdline(self, pid: int) -> str:
        """读取 /proc/PID/cmdline 获取进程命令行"""
        try:
            with open(f"/proc/{pid}/cmdline", "r") as f:
                return f.read().replace("\x00", " ").strip()
        except (FileNotFoundError, PermissionError, OSError):
            return ""

    def _terminate_pid(self, pid: int, sig: int) -> bool:
        """向指定 PID 发送信号，返回是否成功"""
        try:
            os.kill(pid, sig)
            sig_name = "SIGTERM" if sig == signal.SIGTERM else "SIGKILL"
            logger.info(f"已发送 {sig_name} 到进程 {pid}")
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            logger.warning(f"无权限终止进程 {pid}")
            return False

    def _remove_lock_file(self, path: str) -> bool:
        """尝试删除 Qdrant 本地存储的残留锁文件"""
        lock_file = os.path.join(path, ".lock")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                logger.info(f"已删除残留锁文件: {lock_file}")
                return True
            except Exception as e:
                logger.warning(f"删除锁文件失败: {e}")
        return False

    def get_client(self) -> QdrantClient:
        if not self.client:
            raise RuntimeError("Qdrant客户端未初始化")
        return self.client

    async def _run_sync(self, func: Callable, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def create_collection(self, collection_name: str, description: str = ""):
        client = self.get_client()
        try:
            collections = await self._run_sync(client.get_collections)
            existing = [c.name for c in collections.collections]
            if collection_name in existing:
                info = await self._run_sync(client.get_collection, collection_name)
                existing_dim = (
                    getattr(info.config.params.vectors, 'size', None)
                    if hasattr(info, 'config') and hasattr(info.config, 'params')
                    else None
                )
                if existing_dim and existing_dim != self.embedding_dim:
                    logger.warning(
                        f"集合 {collection_name} 维度({existing_dim})与当前模型维度({self.embedding_dim})不匹配，自动重建"
                    )
                    await self._run_sync(client.delete_collection, collection_name=collection_name)
                else:
                    logger.info(f"集合 {collection_name} 已存在, 维度: {existing_dim or self.embedding_dim}")
                    return True
            await self._run_sync(
                client.create_collection,
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=self.embedding_dim,
                    distance=models.Distance.COSINE,
                ),
                optimizers_config=models.OptimizersConfigDiff(
                    indexing_threshold=0,
                ),
            )
            logger.info(f"创建集合 {collection_name} 成功")
            return True
        except Exception as e:
            logger.error(f"创建集合失败 {collection_name}: {e}")
            return False

    async def delete_collection(self, collection_name: str):
        client = self.get_client()
        try:
            await self._run_sync(client.delete_collection, collection_name=collection_name)
            logger.info(f"删除集合 {collection_name} 成功")
            return True
        except Exception as e:
            logger.error(f"删除集合失败 {e}")
            return False

    async def list_collections(self) -> List[Dict[str, Any]]:
        client = self.get_client()
        try:
            collections = await self._run_sync(client.get_collections)
            result = []
            for col in collections.collections:
                info = await self._run_sync(client.get_collection, col.name)
                result.append({
                    "name": col.name,
                    "vectors_count": getattr(info, "vectors_count", 0),
                    "points_count": getattr(info, "points_count", 0),
                    "status": str(getattr(info, "status", "unknown")),
                })
            return result
        except Exception as e:
            logger.error(f"获取集合列表失败: {e}")
            return []

    async def insert_points(
        self,
        collection_name: str,
        points: List[Dict[str, Any]],
    ) -> bool:
        client = self.get_client()
        try:
            if not points:
                logger.warning(f"插入点列表为空，跳过: {collection_name}")
                return True

            actual_dim = len(points[0]["vector"])
            if actual_dim != self.embedding_dim:
                logger.error(
                    f"向量维度不匹配: 实际={actual_dim}, 集合配置={self.embedding_dim}, 集合={collection_name}"
                )
                return False

            qdrant_points = []
            for p in points:
                qdrant_points.append(
                    models.PointStruct(
                        id=p["id"],
                        vector=p["vector"],
                        payload=p.get("payload", {}),
                    )
                )
            await self._run_sync(
                client.upsert,
                collection_name=collection_name,
                points=qdrant_points,
                wait=True,
            )
            logger.info(f"向集合 {collection_name} 插入 {len(qdrant_points)} 条向量")
            return True
        except Exception as e:
            logger.error(f"插入向量失败: {e}")
            return False

    async def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 5,
        score_threshold: float = 0.3,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        client = self.get_client()
        try:
            query_filter = None
            if filters:
                must_conditions = []
                for key, value in filters.items():
                    must_conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=value),
                        )
                    )
                if must_conditions:
                    query_filter = models.Filter(
                        must=must_conditions,
                    )

            is_filter_only = all(v == 0.0 for v in query_vector)
            effective_threshold = 0.0 if is_filter_only else score_threshold

            results = await self._run_sync(
                client.search,
                collection_name=collection_name,
                query_vector=query_vector,
                limit=top_k,
                score_threshold=effective_threshold,
                query_filter=query_filter,
            )
            return [
                {
                    "id": r.id,
                    "score": r.score,
                    "payload": r.payload,
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []

    async def delete_points_by_file(self, collection_name: str, file_name: str) -> bool:
        client = self.get_client()
        try:
            await self._run_sync(
                client.delete,
                collection_name=collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="file_name",
                                match=models.MatchValue(value=file_name),
                            ),
                        ],
                    ),
                ),
                wait=True,
            )
            logger.info(f"删除文件 {file_name} 的所有向量")
            return True
        except Exception as e:
            logger.error(f"删除向量失败: {e}")
            return False

    async def update_point(self, collection_name: str, point_id: str,
                           vector: List[float], payload: Dict[str, Any]) -> bool:
        """更新单个向量点的文本和向量"""
        client = self.get_client()
        try:
            point = models.PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )
            await self._run_sync(
                client.upsert,
                collection_name=collection_name,
                points=[point],
                wait=True,
            )
            logger.info(f"更新切片 {point_id} 成功")
            return True
        except Exception as e:
            logger.error(f"更新切片失败: {e}")
            return False

    async def delete_point(self, collection_name: str, point_id: str) -> bool:
        """删除单个向量点"""
        client = self.get_client()
        try:
            await self._run_sync(
                client.delete,
                collection_name=collection_name,
                points_selector=models.PointIdsList(points=[point_id]),
                wait=True,
            )
            logger.info(f"删除切片 {point_id} 成功")
            return True
        except Exception as e:
            logger.error(f"删除切片失败: {e}")
            return False

    async def get_point(self, collection_name: str, point_id: str) -> Optional[Dict[str, Any]]:
        """获取单个向量点的详细信息"""
        client = self.get_client()
        try:
            results = await self._run_sync(
                client.retrieve,
                collection_name=collection_name,
                ids=[point_id],
                with_payload=True,
                with_vectors=False,
            )
            if results:
                r = results[0]
                return {
                    "id": str(r.id),
                    "payload": r.payload or {},
                }
            return None
        except Exception as e:
            logger.error(f"获取切片失败: {e}")
            return None

    async def get_collection_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
        client = self.get_client()
        try:
            info = await self._run_sync(client.get_collection, collection_name)
            return {
                "name": collection_name,
                "vectors_count": getattr(info, "vectors_count", 0),
                "points_count": getattr(info, "points_count", 0),
                "status": str(getattr(info, "status", "unknown")),
            }
        except Exception as e:
            logger.error(f"获取集合信息失败: {e}")
            return None

    async def health_check(self) -> Dict[str, Any]:
        try:
            client = self.get_client()
            collections = await self._run_sync(client.get_collections)
            return {
                "status": "connected",
                "collections_count": len(collections.collections),
            }
        except Exception as e:
            return {"status": "disconnected", "error": str(e)}


qdrant_service = QdrantService()