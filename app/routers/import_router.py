import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.models.schemas import ApiResponse
from app.services.import_service import import_service
from app.services.archive_service import (
    detect_archive_type, extract_archive, filter_importable_files,
    SUPPORTED_ARCHIVE_EXTS
)
from app.config import settings
from loguru import logger

router = APIRouter(prefix="/import", tags=["文件导入"])


def _fix_filename_encoding(filename: str) -> str:
    """
    修复文件名编码问题

    当浏览器在 Windows 上上传中文文件名时，可能使用 GBK 编码，
    而 Starlette 假设文件名是 UTF-8，导致解码错误。

    常见的乱码模式：
    - GBK 字节被当作 Latin-1 解码后再转为 UTF-8
    - 表现为制表符、希腊字母等特殊字符
    """
    if not filename:
        return filename

    # 检测是否可能是编码问题的乱码
    # GBK 常用字节范围 0x80-0xFF 被误解为 Latin-1 后会显示为制表符等
    box_draw_chars = {'╛', '╔', '╩', '╘', '│', '╠', '╡', '╤', '╨', '╒', '╕',
                      '╗', '╬', '╣', '║', '╦', '╚', '╩', '═', '╬', '■', '╝', '░'}
    greek_chars = {'Φ', 'Γ', 'ε', 'α', 'τ', 'π', 'σ', 'δ', 'θ', 'β', 'ω'}

    has_box_draw = any(c in filename for c in box_draw_chars)
    has_greek = any(c in filename for c in greek_chars)

    # 如果包含制表符或希腊字母，可能是乱码
    if not (has_box_draw or has_greek):
        return filename

    # 尝试修复编码
    # 策略1: 假设原始是 GBK，被误解为 Latin-1，然后存为 UTF-8
    try:
        # 将当前显示的字符转回 UTF-8 字节
        # 这些字节原本是 GBK 字节被当作 Latin-1 解释
        utf8_bytes = filename.encode('utf-8')

        # 尝试直接从 UTF-8 字节解析为 GBK（不太可能，但试试）
        try:
            fixed = utf8_bytes.decode('gbk', errors='ignore')
            # 验证是否看起来像正常中文
            if fixed and any('\u4e00' <= c <= '\u9fff' for c in fixed):
                return fixed
        except Exception:
            pass

        # 尝试: UTF-8 字节 -> Latin-1 字符 -> GBK 字节 -> GBK 解码
        try:
            latin1_str = utf8_bytes.decode('latin-1')
            gbk_bytes = latin1_str.encode('latin-1')
            fixed = gbk_bytes.decode('gbk', errors='ignore')
            if fixed and any('\u4e00' <= c <= '\u9fff' for c in fixed):
                return fixed
        except Exception:
            pass

    except Exception:
        pass

    # 如果修复失败，保留原文件名
    return filename


def _safe_temp_path(original_name: str, prefix: str = "temp") -> str:
    """生成唯一的临时文件路径，避免并发请求文件名冲突"""
    safe_name = os.path.basename(original_name)
    unique = uuid.uuid4().hex[:12]
    return os.path.join(settings.UPLOAD_DIR, f"{prefix}_{unique}_{safe_name}")


@router.post("/single", response_model=ApiResponse)
async def import_single_file(
    kb_name: str = Form(...),
    file: UploadFile = File(...),
    chunk_size: Optional[int] = Form(None),
    chunk_overlap: Optional[int] = Form(None),
    chunk_separator: Optional[str] = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    # 修复文件名编码问题
    fixed_filename = _fix_filename_encoding(file.filename)

    ext = os.path.splitext(fixed_filename)[1].lower().lstrip(".")
    if ext not in settings.SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}，支持格式: {list(settings.SUPPORTED_FORMATS.keys())}",
        )

    if not os.path.exists(settings.UPLOAD_DIR):
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    temp_path = _safe_temp_path(fixed_filename, "single")
    try:
        contents = await file.read()
        if len(contents) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件超过{settings.MAX_FILE_SIZE // 1024 // 1024}MB限制",
            )
        with open(temp_path, "wb") as f:
            f.write(contents)

        result = await import_service.import_file(kb_name, temp_path, fixed_filename,
                                                   chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                                                   chunk_separator=chunk_separator)
        return ApiResponse(data=result)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@router.post("/batch", response_model=ApiResponse)
async def import_batch_files(
    kb_name: str = Form(...),
    files: List[UploadFile] = File(...),
    chunk_size: Optional[int] = Form(None),
    chunk_overlap: Optional[int] = Form(None),
    chunk_separator: Optional[str] = Form(None),
):
    if not files:
        raise HTTPException(status_code=400, detail="未选择文件")

    temp_paths = []
    file_names_map = {}  # 记录修复后的文件名映射
    try:
        for file in files:
            if not file.filename:
                continue

            # 修复文件名编码问题
            fixed_filename = _fix_filename_encoding(file.filename)
            file_names_map[file.filename] = fixed_filename

            ext = os.path.splitext(fixed_filename)[1].lower().lstrip(".")
            if ext not in settings.SUPPORTED_FORMATS:
                continue

            contents = await file.read()
            if len(contents) > settings.MAX_FILE_SIZE:
                logger.warning(f"批量导入跳过过大文件 {fixed_filename}: {len(contents) // 1024 // 1024}MB")
                continue

            temp_path = _safe_temp_path(fixed_filename, "batch")
            with open(temp_path, "wb") as f:
                f.write(contents)
            temp_paths.append(temp_path)

        if not temp_paths:
            raise HTTPException(status_code=400, detail="没有有效的文件可导入")

        result = await import_service.batch_import(kb_name, temp_paths, "batch",
                                                    chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                                                    chunk_separator=chunk_separator)
        return ApiResponse(data=result)
    finally:
        for path in temp_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


@router.post("/archive", response_model=ApiResponse)
async def import_archive_file(
    kb_name: str = Form(...),
    file: UploadFile = File(...),
    chunk_size: Optional[int] = Form(None),
    chunk_overlap: Optional[int] = Form(None),
    chunk_separator: Optional[str] = Form(None),
):
    """
    导入压缩包文件，支持多种格式:
    - .zip
    - .tar, .tar.gz, .tar.bz2, .tar.xz
    - .rar
    - .7z
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    # 修复文件名编码
    fixed_filename = _fix_filename_encoding(file.filename)
    
    # 检测压缩类型
    archive_type = detect_archive_type(fixed_filename)
    if archive_type is None:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的压缩格式。支持格式: {SUPPORTED_ARCHIVE_EXTS}"
        )

    # 创建临时目录
    temp_dir = os.path.join(settings.UPLOAD_DIR, f"archive_temp_{uuid.uuid4().hex[:12]}")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # 保存上传的文件
        archive_path = os.path.join(temp_dir, fixed_filename)
        contents = await file.read()
        with open(archive_path, "wb") as f:
            f.write(contents)

        # 解压压缩包
        extracted_files, error = extract_archive(archive_path, temp_dir)
        
        if error:
            raise HTTPException(status_code=400, detail=f"解压失败: {error}")

        if not extracted_files:
            raise HTTPException(status_code=400, detail="压缩包中没有文件")

        # 筛选可导入的文件
        importable_files = filter_importable_files(extracted_files, settings.SUPPORTED_FORMATS)

        if not importable_files:
            raise HTTPException(
                status_code=400,
                detail=f"压缩包中没有可导入的文件。支持格式: {list(settings.SUPPORTED_FORMATS.keys())}"
            )

        logger.info(f"压缩包导入: {fixed_filename} -> {len(importable_files)} 个可导入文件")

        # 批量导入
        result = await import_service.batch_import(kb_name, importable_files, "archive",
                                                    chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                                                    chunk_separator=chunk_separator)
        return ApiResponse(data=result)
    finally:
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


# 向后兼容的 ZIP 端点
@router.post("/zip", response_model=ApiResponse)
async def import_zip_file(
    kb_name: str = Form(...),
    file: UploadFile = File(...),
    chunk_size: Optional[int] = Form(None),
    chunk_overlap: Optional[int] = Form(None),
    chunk_separator: Optional[str] = Form(None),
):
    """
    [已弃用] 请使用 /archive 端点，支持更多压缩格式
    """
    # 重定向到通用端点
    return await import_archive_file(
        kb_name=kb_name,
        file=file,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        chunk_separator=chunk_separator
    )


@router.get("/tasks", response_model=ApiResponse)
async def list_import_tasks(kb_name: Optional[str] = None):
    tasks = await import_service.list_import_tasks(kb_name)
    return ApiResponse(data=tasks)


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_import_task(task_id: int):
    task = await import_service.get_import_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(data=task)