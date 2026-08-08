"""
OFD 服务 - FastAPI 入口

提供 OFD 文档解析 API：
  POST /ofd/parse       解析 OFD 结构
  POST /ofd/text        提取文本
  POST /ofd/pdf         转 PDF
  POST /ofd/images      转图片
  POST /ofd/extract     提取图片资源
  GET  /health          健康检查

启动：python -m ofd_service.main
"""
import os
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from loguru import logger
from pydantic import BaseModel

from .ofd_parser import OFDParser

# 服务配置
HOST = os.environ.get("OFD_HOST", "0.0.0.0")
PORT = int(os.environ.get("OFD_PORT", "8003"))
MAX_OFD_SIZE = 50 * 1024 * 1024  # 50MB

parser = OFDParser()

app = FastAPI(
    title="OFD Service",
    description="中国版式文档 (OFD) 解析服务 - 支持文本提取、PDF/图片转换",
    version="1.0.0",
)


class HealthResponse(BaseModel):
    status: str
    service: str


class ParseResult(BaseModel):
    format: str
    valid: bool
    pages: int
    has_images: bool
    has_fonts: bool
    metadata: dict


class TextResult(BaseModel):
    full_text: str
    pages: list
    total_pages: int
    char_count: int
    elapsed: float


@app.get("/")
async def root():
    return {
        "service": "OFD Service",
        "version": "1.0.0",
        "description": "中国版式文档 (OFD) 解析服务",
        "endpoints": {
            "parse": "POST /ofd/parse - 解析 OFD 结构",
            "text": "POST /ofd/text - 提取文本",
            "pdf": "POST /ofd/pdf - 转 PDF",
            "images": "POST /ofd/images - 转图片",
            "extract": "POST /ofd/extract - 提取图片资源",
            "health": "GET /health - 健康检查",
            "docs": "GET /docs - API 文档",
        },
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", service="ofd")


@app.post("/ofd/parse", response_model=ParseResult)
async def parse_ofd(file: UploadFile = File(...)):
    """解析 OFD 文件结构"""
    if not file.filename.lower().endswith(".ofd"):
        raise HTTPException(400, "文件必须是 .ofd 格式")

    content = await file.read()
    if len(content) > MAX_OFD_SIZE:
        raise HTTPException(413, f"文件过大，最大 {MAX_OFD_SIZE // 1024 // 1024}MB")

    try:
        info = parser.get_info(content)
        return ParseResult(**info)
    except Exception as e:
        logger.error(f"解析 OFD 失败: {e}")
        raise HTTPException(500, f"解析失败: {e}")


@app.post("/ofd/text", response_model=TextResult)
async def extract_text(file: UploadFile = File(...)):
    """提取 OFD 文本内容"""
    if not file.filename.lower().endswith(".ofd"):
        raise HTTPException(400, "文件必须是 .ofd 格式")

    content = await file.read()
    if len(content) > MAX_OFD_SIZE:
        raise HTTPException(413, f"文件过大，最大 {MAX_OFD_SIZE // 1024 // 1024}MB")

    try:
        result = parser.parse_bytes(content)
        return TextResult(
            full_text=result.text,
            pages=result.pages,
            total_pages=result.page_count,
            char_count=len(result.text),
            elapsed=result.elapsed,
        )
    except Exception as e:
        logger.error(f"提取文本失败: {e}")
        raise HTTPException(500, f"提取失败: {e}")


@app.post("/ofd/pdf")
async def convert_to_pdf(file: UploadFile = File(...)):
    """将 OFD 转换为 PDF"""
    if not file.filename.lower().endswith(".ofd"):
        raise HTTPException(400, "文件必须是 .ofd 格式")

    content = await file.read()
    if len(content) > MAX_OFD_SIZE:
        raise HTTPException(413, f"文件过大，最大 {MAX_OFD_SIZE // 1024 // 1024}MB")

    try:
        pdf_bytes = parser.to_pdf(content)
        filename = os.path.splitext(file.filename)[0] + ".pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"转换 PDF 失败: {e}")
        raise HTTPException(500, f"转换失败: {e}")


@app.post("/ofd/images")
async def convert_to_images(
    file: UploadFile = File(...),
    dpi: int = Form(200),
    pages: Optional[str] = Form(None),
):
    """将 OFD 转换为图片"""
    if not file.filename.lower().endswith(".ofd"):
        raise HTTPException(400, "文件必须是 .ofd 格式")

    content = await file.read()
    if len(content) > MAX_OFD_SIZE:
        raise HTTPException(413, f"文件过大，最大 {MAX_OFD_SIZE // 1024 // 1024}MB")

    # 解析页码
    page_list = None
    if pages:
        try:
            page_list = [int(p.strip()) for p in pages.split(",") if p.strip()]
        except ValueError:
            raise HTTPException(400, "页码格式错误，应为逗号分隔的数字")

    try:
        result = parser.to_images(content, dpi=dpi, pages=page_list)
        return {
            "total": len(result),
            "pages": [
                {
                    "page": p["page"],
                    "format": p["format"],
                    "width": p["width"],
                    "height": p["height"],
                }
                for p in result
            ],
        }
    except Exception as e:
        logger.error(f"转换图片失败: {e}")
        raise HTTPException(500, f"转换失败: {e}")


@app.post("/ofd/extract")
async def extract_images(file: UploadFile = File(...)):
    """提取 OFD 中嵌入的图片资源"""
    if not file.filename.lower().endswith(".ofd"):
        raise HTTPException(400, "文件必须是 .ofd 格式")

    content = await file.read()
    if len(content) > MAX_OFD_SIZE:
        raise HTTPException(413, f"文件过大，最大 {MAX_OFD_SIZE // 1024 // 1024}MB")

    try:
        result = parser.extract_images(content)
        return {
            "total": len(result),
            "images": [
                {"filename": img["filename"], "format": img["format"], "size": img["size"]}
                for img in result
            ],
        }
    except Exception as e:
        logger.error(f"提取图片失败: {e}")
        raise HTTPException(500, f"提取失败: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
