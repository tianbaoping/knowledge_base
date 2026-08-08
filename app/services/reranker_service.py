import asyncio
import threading
import os
from typing import List, Optional, Tuple
from loguru import logger
from app.config import settings

MODEL_LOAD_TIMEOUT = 30


class RerankerService:
    def __init__(self):
        self.model_name = getattr(settings, "RERANKER_MODEL", "BAAI/bge-reranker-base")
        self.local_path = getattr(settings, "RERANKER_LOCAL_PATH", "")
        self.model = None
        self._initialized = False
        self._init_error = None
        self._demo_mode = False
        self._device = self._resolve_device()

    @staticmethod
    def _resolve_device() -> str:
        """解析配置的推理设备，"auto" 时优先 CUDA，不可用则回退 CPU"""
        cfg = getattr(settings, "MODEL_DEVICE", "cpu")
        if cfg == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    logger.info("Reranker MODEL_DEVICE=auto，检测到 CUDA 可用，使用 cuda")
                    return "cuda"
            except Exception:
                pass
            logger.info("Reranker MODEL_DEVICE=auto，CUDA 不可用，使用 cpu")
            return "cpu"
        return cfg

    def _load_with_device_fallback(self, loader_fn, label: str):
        """
        用 loader_fn(device) 加载模型；若指定的 device 是 cuda 且失败，
        自动回退到 cpu 重试。返回 (model, used_device, error)。
        """
        device = self._device
        try:
            model = loader_fn(device)
            return model, device, None
        except Exception as e:
            err_msg = str(e)
            if device != "cpu" and ("meta tensor" in err_msg or "cuda" in err_msg.lower() or "device" in err_msg.lower()):
                logger.warning(f"{label} 在 {device} 加载失败({err_msg})，自动回退到 cpu 重试")
                try:
                    model = loader_fn("cpu")
                    self._device = "cpu"
                    logger.info(f"{label} 已回退到 cpu 加载成功")
                    return model, "cpu", None
                except Exception as e2:
                    return None, "cpu", e2
            return None, device, e

    async def init(self):
        logger.info(f"正在加载重排模型: {self.model_name} ...")

        if self.local_path and os.path.isdir(self.local_path):
            logger.info(f"检测到本地重排模型路径: {self.local_path}，优先从本地加载")
            try:
                model = await self._load_local_model(self.local_path)
                if model is None:
                    raise RuntimeError("本地模型加载返回None")
                self.model = model
                self._initialized = True
                self._init_error = None
                self._demo_mode = False
                logger.info(f"本地重排模型加载成功: {self.local_path}")
                return
            except Exception as e:
                logger.error(f"本地重排模型加载失败: {e}，将尝试在线下载")

        try:
            model = await self._load_model_with_timeout()
            if model is None:
                raise RuntimeError("模型加载返回None")
            self.model = model
            self._initialized = True
            self._init_error = None
            self._demo_mode = False
            logger.info(f"重排模型加载成功: {self.model_name}")
        except TimeoutError:
            self._init_error = f"重排模型加载超时（{MODEL_LOAD_TIMEOUT}秒）"
            self._initialized = False
            self.model = None
            logger.error(f"重排模型加载超时: {self.model_name}")
            self._enable_demo_mode("模型加载超时")
        except Exception as e:
            self._init_error = str(e)
            self._initialized = False
            self.model = None
            logger.error(f"重排模型加载失败: {e}")
            self._enable_demo_mode(str(e))

    async def _load_model_with_timeout(self):
        loop = asyncio.get_running_loop()
        result = {"model": None, "error": None}

        def load_in_thread():
            try:
                os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "10")
                os.environ.setdefault("HF_HUB_OFFLINE", "0")
                from sentence_transformers import CrossEncoder

                def _loader(dev):
                    return CrossEncoder(
                        self.model_name,
                        device=dev,
                        trust_remote_code=True,
                    )

                model, used_dev, err = self._load_with_device_fallback(_loader, "重排模型(在线)")
                if err:
                    raise err
                result["model"] = model
            except Exception as e:
                result["error"] = e

        thread = threading.Thread(target=load_in_thread, daemon=True)
        thread.start()

        def wait_for_thread():
            thread.join(timeout=MODEL_LOAD_TIMEOUT)
            return thread.is_alive()

        still_alive = await loop.run_in_executor(None, wait_for_thread)
        if still_alive:
            raise TimeoutError(f"模型加载超时（{MODEL_LOAD_TIMEOUT}秒）")
        if result["error"]:
            raise result["error"]
        return result["model"]

    async def _load_local_model(self, path: str):
        loop = asyncio.get_running_loop()
        result = {"model": None, "error": None}

        def load_from_path():
            try:
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                from sentence_transformers import CrossEncoder

                def _loader(dev):
                    return CrossEncoder(
                        path,
                        device=dev,
                        trust_remote_code=True,
                    )

                model, used_dev, err = self._load_with_device_fallback(_loader, "重排模型(本地)")
                if err:
                    raise err
                result["model"] = model
            except Exception as e:
                result["error"] = e

        thread = threading.Thread(target=load_from_path, daemon=True)
        thread.start()

        def wait_for_thread():
            thread.join(timeout=MODEL_LOAD_TIMEOUT)
            return thread.is_alive()

        still_alive = await loop.run_in_executor(None, wait_for_thread)
        if still_alive:
            raise TimeoutError(f"本地模型加载超时（{MODEL_LOAD_TIMEOUT}秒）")
        if result["error"]:
            raise result["error"]
        return result["model"]

    def _enable_demo_mode(self, reason: str):
        self._demo_mode = True
        self._initialized = True
        self._init_error = reason
        logger.warning(f"已启用重排演示模式，原因: {reason}")

    def rerank(self, query: str, documents: List[str], top_k: int = 5) -> List[Tuple[int, float]]:
        """
        对候选文档进行重排序。
        返回 [(index, score), ...] 按 score 降序排列，取 top_k 个。
        index 对应原始 documents 列表的索引。
        """
        if self._demo_mode:
            return self._mock_rerank(query, documents, top_k)

        if not self._initialized or self.model is None:
            raise RuntimeError(f"重排模型未初始化: {self._init_error or '模型加载中或失败'}")

        try:
            pairs = [[query, doc] for doc in documents]
            scores = self.model.predict(pairs, show_progress_bar=False)
            if not isinstance(scores, list):
                scores = scores.tolist()

            scored = [(i, float(s)) for i, s in enumerate(scores)]
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_k]
        except Exception as e:
            logger.error(f"重排失败: {e}")
            raise

    def _mock_rerank(self, query: str, documents: List[str], top_k: int) -> List[Tuple[int, float]]:
        """演示模式：基于关键词重叠度的简单评分"""
        query_chars = set(query)
        scored = []
        for i, doc in enumerate(documents):
            doc_chars = set(doc)
            overlap = len(query_chars & doc_chars)
            total = len(query_chars | doc_chars) if query_chars | doc_chars else 1
            score = overlap / total
            scored.append((i, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def get_model_info(self) -> dict:
        return {
            "model_name": self.model_name,
            "local_path": self.local_path,
            "initialized": self._initialized,
            "demo_mode": self._demo_mode,
            "init_error": self._init_error,
            "device": self._device,
        }


reranker_service = RerankerService()
