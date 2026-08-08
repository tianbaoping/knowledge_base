"""
OCR 服务 - FastAPI 入口 (基于 RapidOCR / ONNX Runtime)

提供通用 OCR API：
  POST /ocr              识别单张图片或 PDF
  POST /ocr/batch        批量识别
  GET  /health           健康检查
  GET  /                 服务信息

启动：python -m ocr_service.main
"""
import os
import time
import asyncio
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from loguru import logger

from .config import HOST, PORT, MAX_IMAGE_SIZE, MAX_PDF_SIZE, MAX_PDF_PAGES, TEMP_DIR
from .ocr_engine import ocr_engine


# ---------- 日志配置 ----------
logger.add(
    os.path.join(TEMP_DIR, "ocr_service.log"),
    rotation="10 MB",
    retention="7 days",
    level="INFO",
)


# ---------- 响应模型 ----------
class OCRLine(BaseModel):
    line_index: int
    text: str
    score: float
    box: List[List[float]]


class OCRPageResult(BaseModel):
    page: int
    text: str
    lines: List[OCRLine]
    line_count: int
    char_count: int
    error: Optional[str] = None


class OCRResponse(BaseModel):
    success: bool
    format: str
    elapsed: float
    total_pages: int
    full_text: str
    pages: List[OCRPageResult]
    char_count: int


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model: str


# ---------- 生命周期 ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"OCR 服务启动 @ {HOST}:{PORT}")
    logger.info(f"临时目录: {TEMP_DIR}")
    logger.info("引擎: RapidOCR (PP-OCRv4) / ONNX Runtime, 模型懒加载")
    yield
    logger.info("OCR 服务关闭")


# ---------- FastAPI 应用 ----------
app = FastAPI(
    title="OCR Service (RapidOCR)",
    description="基于 RapidOCR (PP-OCRv4) 的中文 OCR 服务，支持图片和 PDF",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {
        "service": "OCR Service (RapidOCR)",
        "version": "1.0.0",
        "model": "PP-OCRv4 Chinese",
        "engine": "RapidOCR / ONNX Runtime",
        "endpoints": {
            "ocr": "POST /ocr - 识别图片或 PDF",
            "batch": "POST /ocr/batch - 批量识别",
            "health": "GET /health - 健康检查",
            "docs": "GET /docs - API 文档",
        },
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy" if ocr_engine.is_ready() else "starting",
        model_loaded=ocr_engine.is_ready(),
        model="PP-OCRv4 Chinese",
    )


def _detect_format(filename: str, content: bytes) -> str:
    """根据文件名和内容判断格式"""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if ext in ("jpg", "jpeg", "png", "bmp", "tiff", "tif", "webp"):
        return "image"
    if ext == "pdf":
        return "pdf"
    # 通过文件头判断
    if content[:4] == b"%PDF":
        return "pdf"
    if content[:2] in (b"\xff\xd8", b"\x89P", b"BM", b"II", b"MM"):
        return "image"
    raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext or '未知'}")


@app.post("/ocr", response_model=OCRResponse)
async def ocr(
    file: UploadFile = File(...),
    dpi: int = Query(200, ge=72, le=600, description="PDF 渲染 DPI（仅对 PDF 生效）"),
):
    """
    识别单张图片或 PDF

    支持格式：
    - 图片: jpg/jpeg/png/bmp/tiff/webp
    - PDF: .pdf（逐页转图片后 OCR）
    """
    t0 = time.time()
    content = await file.read()
    fmt = _detect_format(file.filename or "", content)

    if fmt == "image":
        if len(content) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"图片超过 {MAX_IMAGE_SIZE // 1024 // 1024}MB 限制",
            )
    elif fmt == "pdf":
        if len(content) > MAX_PDF_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"PDF 超过 {MAX_PDF_SIZE // 1024 // 1024}MB 限制",
            )

    # OCR 在线程池中执行（避免阻塞事件循环）
    try:
        if fmt == "image":
            result = await asyncio.to_thread(ocr_engine.recognize_image, content, 1)
            pages = [result]
            full_text = result["text"]
            total_pages = 1
        else:  # pdf
            result = await asyncio.to_thread(
                ocr_engine.recognize_pdf, content, MAX_PDF_PAGES, dpi
            )
            pages = result["pages"]
            full_text = result["full_text"]
            total_pages = result["total_pages"]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"OCR 处理失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"OCR 处理失败: {str(e)}")

    elapsed = time.time() - t0
    logger.info(
        f"OCR 完成: {file.filename}, 格式={fmt}, 页数={total_pages}, "
        f"字符数={len(full_text)}, 耗时={elapsed:.2f}s"
    )

    return OCRResponse(
        success=True,
        format=fmt,
        elapsed=round(elapsed, 3),
        total_pages=total_pages,
        full_text=full_text,
        pages=pages,
        char_count=len(full_text),
    )


@app.post("/ocr/batch")
async def ocr_batch(
    files: List[UploadFile] = File(...),
    dpi: int = Query(200, ge=72, le=600),
):
    """
    批量识别多个图片或 PDF

    逐个处理，单个失败不影响其他文件
    """
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="单次最多 20 个文件")

    results = []
    for i, f in enumerate(files):
        t0 = time.time()
        try:
            content = await f.read()
            fmt = _detect_format(f.filename or "", content)

            if fmt == "image" and len(content) > MAX_IMAGE_SIZE:
                results.append({
                    "filename": f.filename,
                    "success": False,
                    "error": f"图片超过 {MAX_IMAGE_SIZE // 1024 // 1024}MB 限制",
                })
                continue
            if fmt == "pdf" and len(content) > MAX_PDF_SIZE:
                results.append({
                    "filename": f.filename,
                    "success": False,
                    "error": f"PDF 超过 {MAX_PDF_SIZE // 1024 // 1024}MB 限制",
                })
                continue

            if fmt == "image":
                result = await asyncio.to_thread(ocr_engine.recognize_image, content, 1)
                full_text = result["text"]
                total_pages = 1
                pages = [result]
            else:
                result = await asyncio.to_thread(
                    ocr_engine.recognize_pdf, content, MAX_PDF_PAGES, dpi
                )
                full_text = result["full_text"]
                total_pages = result["total_pages"]
                pages = result["pages"]

            elapsed = time.time() - t0
            results.append({
                "filename": f.filename,
                "success": True,
                "format": fmt,
                "elapsed": round(elapsed, 3),
                "total_pages": total_pages,
                "char_count": len(full_text),
                "full_text": full_text,
                "pages": pages,
            })
        except Exception as e:
            logger.error(f"批量 OCR 第 {i+1} 个文件 {f.filename} 失败: {e}")
            results.append({
                "filename": f.filename,
                "success": False,
                "error": str(e),
            })

    success_count = sum(1 for r in results if r["success"])
    return {
        "total": len(results),
        "success": success_count,
        "failed": len(results) - success_count,
        "results": results,
    }


def run():
    """启动服务"""
    import uvicorn
    uvicorn.run(
        "ocr_service.main:app",
        host=HOST,
        port=PORT,
        log_level="info",
        timeout_keep_alive=300,
    )


if __name__ == "__main__":
    run()
