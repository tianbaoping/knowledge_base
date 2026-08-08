"""
OCR 服务配置（基于 RapidOCR / ONNX Runtime）
"""
import os
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent

# 模型存放目录（项目自带，不依赖 pip 包默认路径）
MODEL_DIR = str(Path(__file__).resolve().parent / "models")

# 服务配置
HOST = os.environ.get("OCR_HOST", "0.0.0.0")
PORT = int(os.environ.get("OCR_PORT", "8002"))

# 模型文件路径（从 ocr_service/models/ 加载）
_DEFAULT_DET = os.path.join(MODEL_DIR, "ch_PP-OCRv4_det_infer.onnx")
_DEFAULT_REC = os.path.join(MODEL_DIR, "ch_PP-OCRv4_rec_infer.onnx")
_DEFAULT_CLS = os.path.join(MODEL_DIR, "ch_ppocr_mobile_v2.0_cls_infer.onnx")

OCR_CONFIG = {
    "lang": "ch",
    "det_model_path": os.environ.get("OCR_DET_MODEL_PATH", _DEFAULT_DET),
    "rec_model_path": os.environ.get("OCR_REC_MODEL_PATH", _DEFAULT_REC),
    "cls_model_path": os.environ.get("OCR_CLS_MODEL_PATH", _DEFAULT_CLS),
}

# 上传限制
MAX_IMAGE_SIZE = 20 * 1024 * 1024
MAX_PDF_SIZE = 50 * 1024 * 1024
MAX_PDF_PAGES = 50

# 临时文件目录
TEMP_DIR = str(_BASE_DIR / "data" / "ocr_temp")
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)
