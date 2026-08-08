"""
OCR 引擎封装（RapidOCR 实现）

- RapidOCR 是 PaddleOCR 的 C++/ONNX Runtime 实现，兼容 PP-OCRv4 模型
- 懒加载：首次调用时才初始化模型，避免启动时长时间阻塞
- 单例：全局共享一个 RapidOCR 实例，避免重复加载模型
- 线程安全：使用锁保护初始化过程
- 支持图片和 PDF（PDF 逐页转图片后 OCR）

为什么用 RapidOCR 而非 PaddleOCR:
  PaddleOCR 3.x + PaddlePaddle 3.x 在 Windows 上存在 PIR (Paddle Intermediate
  Representation) 兼容性问题，导致 oneDNN 推理时报 ConvertPirAttribute2RuntimeAttribute
  错误。RapidOCR 使用 ONNX Runtime 推理，完美规避此问题，且保持相同的识别精度。
"""
import io
import os
import time
import threading
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger

from .config import OCR_CONFIG, MODEL_DIR


class OCREngine:
    """OCR 单例引擎（基于 RapidOCR / ONNX Runtime）"""

    _instance: Optional["OCREngine"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._ocr = None
        self._init_lock = threading.Lock()
        self._initialized = True

    @property
    def ocr(self):
        """懒加载 RapidOCR 实例"""
        if self._ocr is None:
            with self._init_lock:
                if self._ocr is None:
                    self._load_model()
        return self._ocr

    def _load_model(self):
        """加载 RapidOCR 模型（PP-OCRv4），从 ocr_service/models/ 目录加载"""
        t0 = time.time()
        det_path = OCR_CONFIG["det_model_path"]
        rec_path = OCR_CONFIG["rec_model_path"]
        cls_path = OCR_CONFIG["cls_model_path"]

        logger.info("=" * 50)
        logger.info("开始加载 RapidOCR (PP-OCRv4) 中文模型...")
        logger.info(f"  模型目录: {MODEL_DIR}")
        logger.info(f"  det: {det_path}")
        logger.info(f"  rec: {rec_path}")
        logger.info(f"  cls: {cls_path}")
        logger.info("=" * 50)

        # 校验模型文件存在
        for label, path in [("det", det_path), ("rec", rec_path), ("cls", cls_path)]:
            if not os.path.isfile(path):
                raise FileNotFoundError(
                    f"OCR {label} 模型文件不存在: {path}\n"
                    f"请确保模型文件已放置在 {MODEL_DIR} 目录下"
                )

        try:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr = RapidOCR(
                det_model_path=det_path,
                rec_model_path=rec_path,
                cls_model_path=cls_path,
            )
            elapsed = time.time() - t0
            logger.info(f"RapidOCR 模型加载完成，耗时 {elapsed:.1f}s")
        except ImportError as e:
            logger.error(f"rapidocr_onnxruntime 未安装: {e}")
            raise RuntimeError(
                f"rapidocr_onnxruntime 未安装，请运行 pip install rapidocr-onnxruntime"
            ) from e
        except Exception as e:
            logger.error(f"RapidOCR 加载失败: {e}")
            raise

    def _result_to_dict(self, result: list, page_num: int = 1) -> Dict[str, Any]:
        """
        RapidOCR 原始结果转结构化字典

        RapidOCR 返回格式:
            result: [[box, text, score], ...]
            box: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        """
        lines = []
        full_text_parts = []

        if result:
            for idx, item in enumerate(result):
                box = item[0]
                text = item[1]
                score = float(item[2])

                box_list = [[float(p[0]), float(p[1])] for p in box]

                lines.append({
                    "line_index": idx,
                    "text": text,
                    "score": round(score, 4),
                    "box": box_list,
                })
                full_text_parts.append(text)

        full_text = "\n".join(full_text_parts)
        return {
            "page": page_num,
            "text": full_text,
            "lines": lines,
            "line_count": len(lines),
            "char_count": len(full_text),
        }

    def recognize_image(self, image_bytes: bytes, page_num: int = 1) -> Dict[str, Any]:
        """
        识别图片字节流

        Args:
            image_bytes: 图片二进制数据
            page_num: 页码（用于多页场景）

        Returns:
            {
                "page": int,
                "text": str,
                "lines": [...],
                "line_count": int,
                "char_count": int,
            }
        """
        import numpy as np
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        img_array = np.array(img)

        result, elapse = self.ocr(img_array)
        return self._result_to_dict(result, page_num)

    def recognize_image_file(self, file_path: str, page_num: int = 1) -> Dict[str, Any]:
        """
        识别图片文件（直接传路径给 RapidOCR，内部处理更高效）

        Args:
            file_path: 图片文件路径
            page_num: 页码

        Returns:
            同 recognize_image
        """
        result, elapse = self.ocr(file_path)
        return self._result_to_dict(result, page_num)

    def recognize_pdf(
        self,
        pdf_bytes: bytes,
        max_pages: int = 50,
        dpi: int = 200,
    ) -> Dict[str, Any]:
        """
        识别 PDF（逐页转图片后 OCR）

        Args:
            pdf_bytes: PDF 二进制数据
            max_pages: 最大页数限制
            dpi: 渲染 DPI（影响精度和速度）

        Returns:
            {
                "total_pages": int,
                "pages": [...],
                "full_text": str,
                "char_count": int,
            }
        """
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            total_pages = len(doc)
            if total_pages > max_pages:
                raise ValueError(f"PDF 页数 {total_pages} 超过限制 {max_pages}")

            pages = []
            full_text_parts = []

            for page_num in range(total_pages):
                page = doc[page_num]
                zoom = dpi / 72
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                image_bytes = pix.tobytes("png")

                try:
                    page_result = self.recognize_image(image_bytes, page_num + 1)
                    pages.append(page_result)
                    full_text_parts.append(page_result["text"])
                except Exception as e:
                    logger.warning(f"PDF 第 {page_num + 1} 页 OCR 失败: {e}")
                    pages.append({
                        "page": page_num + 1,
                        "text": "",
                        "lines": [],
                        "line_count": 0,
                        "char_count": 0,
                        "error": str(e),
                    })

            full_text = "\n\n".join(full_text_parts)
            return {
                "total_pages": total_pages,
                "pages": pages,
                "full_text": full_text,
                "char_count": len(full_text),
            }
        finally:
            doc.close()

    def is_ready(self) -> bool:
        """检查引擎是否已加载"""
        return self._ocr is not None


ocr_engine = OCREngine()
