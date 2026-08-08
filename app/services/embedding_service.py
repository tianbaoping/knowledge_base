import asyncio
import threading
import os
import shutil
from typing import List, Optional
from loguru import logger
from app.config import settings

MODEL_LOAD_TIMEOUT = 30


class EmbeddingService:
    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL
        self.local_path = settings.MODEL_LOCAL_PATH
        self.model = None
        self._initialized = False
        self._init_error = None
        self._demo_mode = False
        self._actual_dim = settings.EMBEDDING_DIM
        self._device = self._resolve_device()

    @staticmethod
    def _resolve_device() -> str:
        """解析配置的推理设备，"auto" 时优先 CUDA，不可用则回退 CPU"""
        cfg = getattr(settings, "MODEL_DEVICE", "cpu")
        if cfg == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    logger.info("MODEL_DEVICE=auto，检测到 CUDA 可用，使用 cuda")
                    return "cuda"
            except Exception:
                pass
            logger.info("MODEL_DEVICE=auto，CUDA 不可用，使用 cpu")
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

    def _sync_dimension(self, dim: int):
        """模型加载后，检测实际维度并同步到全局配置"""
        self._actual_dim = dim
        if dim != settings.EMBEDDING_DIM:
            logger.warning(
                f"配置中的 EMBEDDING_DIM={settings.EMBEDDING_DIM} 与模型实际维度 {dim} 不一致，已自动修正为 {dim}"
            )
            settings.EMBEDDING_DIM = dim
            from app.services.qdrant_service import qdrant_service
            qdrant_service.embedding_dim = dim

    async def init(self):
        logger.info(f"正在加载嵌入模型: {self.model_name} ...")

        if self.local_path and os.path.isdir(self.local_path):
            logger.info(f"检测到本地模型路径: {self.local_path}，优先从本地加载")
            try:
                model = await self._load_local_model(self.local_path)
                if model is None:
                    raise RuntimeError("本地模型加载返回None")

                test_embedding = model.encode(["test"], normalize_embeddings=True)
                if test_embedding is None or len(test_embedding) == 0:
                    raise RuntimeError("本地模型编码验证失败")

                self.model = model
                self._initialized = True
                self._init_error = None
                self._demo_mode = False
                dim = len(test_embedding[0])
                self._sync_dimension(dim)
                logger.info(f"本地嵌入模型加载成功: {self.local_path}, 维度: {dim}")
                return
            except Exception as e:
                logger.error(f"本地模型加载失败: {e}，将尝试在线下载")

        network_ok = await self._check_network()
        if not network_ok:
            logger.warning("无法连接到HuggingFace，直接切换到演示模式")
            self._enable_demo_mode("网络不可用，无法下载模型")
            return

        try:
            model = await self._load_model_with_timeout()
            if model is None:
                raise RuntimeError("模型加载返回None")

            test_embedding = model.encode(["test"], normalize_embeddings=True)
            if test_embedding is None or len(test_embedding) == 0:
                raise RuntimeError("模型编码验证失败")

            self.model = model
            self._initialized = True
            self._init_error = None
            self._demo_mode = False
            dim = len(test_embedding[0])
            self._sync_dimension(dim)
            logger.info(f"嵌入模型加载成功: {self.model_name}, 维度: {dim}")
        except TimeoutError:
            self._init_error = f"模型加载超时（{MODEL_LOAD_TIMEOUT}秒）"
            self._initialized = False
            self.model = None
            logger.error(f"嵌入模型加载超时（{MODEL_LOAD_TIMEOUT}秒）: {self.model_name}")
            self._enable_demo_mode("模型加载超时")
        except Exception as e:
            self._init_error = str(e)
            self._initialized = False
            self.model = None
            logger.error(f"嵌入模型加载失败: {e}")
            self._enable_demo_mode(str(e))

    async def _check_network(self) -> bool:
        import socket
        import urllib.request

        def _do_check():
            try:
                urllib.request.urlopen("https://huggingface.co", timeout=5)
                return True
            except Exception:
                pass
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3)
                s.connect(("huggingface.co", 443))
                s.close()
                return True
            except Exception:
                return False

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do_check)

    async def _load_model_with_timeout(self):
        loop = asyncio.get_running_loop()
        result = {"model": None, "error": None}

        def load_in_thread():
            try:
                os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "10")
                os.environ.setdefault("HF_HUB_OFFLINE", "0")
                from sentence_transformers import SentenceTransformer

                def _loader(dev):
                    return SentenceTransformer(
                        self.model_name,
                        device=dev,
                        trust_remote_code=True,
                    )

                model, used_dev, err = self._load_with_device_fallback(_loader, "嵌入模型(在线)")
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
                from sentence_transformers import SentenceTransformer

                def _loader(dev):
                    return SentenceTransformer(
                        path,
                        device=dev,
                        trust_remote_code=True,
                    )

                model, used_dev, err = self._load_with_device_fallback(_loader, "嵌入模型(本地)")
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

    @staticmethod
    def download_model_to_local(model_name: str, save_path: str):
        import os
        os.environ.setdefault("HF_HUB_OFFLINE", "0")
        from sentence_transformers import SentenceTransformer
        logger.info(f"正在下载模型 {model_name} 到 {save_path} ...")
        model = SentenceTransformer(model_name, trust_remote_code=True)
        os.makedirs(save_path, exist_ok=True)
        model.save(save_path)
        logger.info(f"模型下载完成: {save_path}")
        logger.info(f"后续启动时设置 MODEL_LOCAL_PATH={save_path} 即可离线加载")
        return save_path

    def _enable_demo_mode(self, reason: str):
        self._demo_mode = True
        self._initialized = True
        self._init_error = reason
        logger.warning(f"已启用演示模式（Mock Embedding），原因: {reason}")
        logger.warning("生产环境请配置有效的嵌入模型或手动下载模型到本地")

    def encode(self, texts: List[str]) -> List[List[float]]:
        if self._demo_mode:
            return self._mock_encode(texts)

        if not self._initialized or self.model is None:
            raise RuntimeError(f"嵌入模型未初始化: {self._init_error or '模型加载中或失败'}")

        try:
            embeddings = self.model.encode(
                texts,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"文本嵌入失败: {e}")
            raise

    def _mock_encode(self, texts: List[str]) -> List[List[float]]:
        import hashlib
        import math

        dim = settings.EMBEDDING_DIM
        results = []
        for text in texts:
            hash_bytes = hashlib.sha256(text.encode('utf-8')).digest()
            vector = []
            for i in range(dim):
                byte_idx = i % len(hash_bytes)
                val = (hash_bytes[byte_idx] / 255.0) * 2 - 1
                vector.append(val)

            norm = math.sqrt(sum(x * x for x in vector))
            if norm > 0:
                vector = [x / norm for x in vector]
            results.append(vector)
        return results

    def encode_single(self, text: str) -> List[float]:
        return self.encode([text])[0]

    def get_model_info(self) -> dict:
        return {
            "model_name": self.model_name,
            "local_path": self.local_path,
            "embedding_dim": self._actual_dim,
            "initialized": self._initialized,
            "demo_mode": self._demo_mode,
            "init_error": self._init_error,
            "device": self._device,
        }


embedding_service = EmbeddingService()