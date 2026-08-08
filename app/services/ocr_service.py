"""
OCR 服务状态监控

提供 OCR 引擎状态、模型信息、资源使用情况等
"""
import os
import time
import threading
from typing import Dict, Any, Optional
from loguru import logger


class OCRServiceMonitor:
    """OCR 服务状态监控器"""

    def __init__(self):
        self._engine = None
        self._initialized = False
        self._start_time = None
        self._last_check_time = None
        self._model_info = {
            "det_model": "ch_PP-OCRv4_det_infer.onnx",
            "rec_model": "ch_PP-OCRv4_rec_infer.onnx",
            "cls_model": "ch_ppocr_mobile_v2.0_cls_infer.onnx",
            "model_version": "PP-OCRv4",
            "framework": "RapidOCR + ONNX Runtime",
        }
        self._stats = {
            "total_requests": 0,
            "total_pages_processed": 0,
            "total_chars_extracted": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "avg_processing_time_ms": 0,
            "total_processing_time_ms": 0,
        }
        self._stats_lock = threading.Lock()

    def set_engine(self, engine):
        """设置 OCR 引擎引用"""
        self._engine = engine
        self._initialized = True
        self._start_time = time.time()
        logger.info("OCR 服务监控已激活")

    def record_request(self, pages: int = 0, chars: int = 0,
                       processing_time_ms: float = 0, success: bool = True):
        """记录一次 OCR 请求"""
        with self._stats_lock:
            self._stats["total_requests"] += 1
            self._stats["total_pages_processed"] += pages
            self._stats["total_chars_extracted"] += chars
            self._stats["total_processing_time_ms"] += processing_time_ms

            if success:
                self._stats["successful_requests"] += 1
            else:
                self._stats["failed_requests"] += 1

            # 更新平均处理时间
            total = self._stats["total_requests"]
            if total > 0:
                self._stats["avg_processing_time_ms"] = (
                    self._stats["total_processing_time_ms"] / total
                )

    def get_status(self) -> Dict[str, Any]:
        """获取 OCR 服务状态"""
        uptime_seconds = 0
        if self._start_time:
            uptime_seconds = time.time() - self._start_time

        # 检查引擎是否就绪
        engine_ready = False
        if self._engine:
            try:
                engine_ready = self._engine.is_ready()
            except Exception:
                pass

        # 获取内存使用情况（如果 psutil 可用）
        memory_info = {}
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            memory_info = {
                "rss_mb": round(mem_info.rss / 1024 / 1024, 2),
                "vms_mb": round(mem_info.vms / 1024 / 1024, 2),
                "percent": round(process.memory_percent(), 2),
            }
        except ImportError:
            memory_info = {
                "rss_mb": "unknown (psutil not installed)",
                "vms_mb": "unknown",
                "percent": "unknown",
            }
        except Exception as e:
            memory_info = {
                "error": str(e),
            }

        # 计算运行时间
        hours, remainder = divmod(int(uptime_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        return {
            "status": "running" if engine_ready else "initializing" if self._initialized else "stopped",
            "engine_ready": engine_ready,
            "initialized": self._initialized,
            "uptime_seconds": int(uptime_seconds),
            "uptime_display": uptime_str,
            "model_info": self._model_info,
            "memory": memory_info,
            "stats": {
                "total_requests": self._stats["total_requests"],
                "successful_requests": self._stats["successful_requests"],
                "failed_requests": self._stats["failed_requests"],
                "success_rate": (
                    round(self._stats["successful_requests"] / self._stats["total_requests"] * 100, 1)
                    if self._stats["total_requests"] > 0 else 0
                ),
                "total_pages_processed": self._stats["total_pages_processed"],
                "total_chars_extracted": self._stats["total_chars_extracted"],
                "avg_processing_time_ms": round(self._stats["avg_processing_time_ms"], 1),
                "last_request_time": self._last_check_time,
            },
        }

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型详细信息"""
        # ocr_service.py 在 app/services/ 下，需要往上3级到项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        model_dir = os.path.join(project_root, "ocr_service", "models")

        model_files = []
        total_size = 0
        if os.path.exists(model_dir):
            for f in os.listdir(model_dir):
                if f.endswith(".onnx"):
                    fpath = os.path.join(model_dir, f)
                    size = os.path.getsize(fpath)
                    model_files.append({
                        "name": f,
                        "size_mb": round(size / 1024 / 1024, 2),
                    })
                    total_size += size

        return {
            **self._model_info,
            "model_directory": model_dir,
            "model_files": model_files,
            "total_model_size_mb": round(total_size / 1024 / 1024, 2),
            "model_files_ready": len(model_files) == 3,  # 3个模型文件
        }

    def reset_stats(self):
        """重置统计数据"""
        with self._stats_lock:
            self._stats = {
                "total_requests": 0,
                "total_pages_processed": 0,
                "total_chars_extracted": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "avg_processing_time_ms": 0,
                "total_processing_time_ms": 0,
            }
        logger.info("OCR 统计数据已重置")


ocr_service_monitor = OCRServiceMonitor()
