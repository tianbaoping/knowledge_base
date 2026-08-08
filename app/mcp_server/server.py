"""
知识库管理系统 - 真正的 MCP Server (Model Context Protocol)

基于官方 Python SDK (mcp >= 2.0) 的 MCPServer 实现，符合 MCP 2025-06-18 / 2026-07-28 规范。
支持双传输：
  1. stdio              - 本地 Claude Desktop / Cursor 子进程模式
  2. Streamable HTTP    - 远程 HTTP 调用，挂载到 FastAPI 主应用

工具返回格式严格遵循 MCP 规范：
  {content: [{type: "text", text: "..."}], isError: bool}

主流 MCP 客户端 (Claude Desktop / Cursor / Cline / VS Code MCP 扩展) 可零配置直接对接。
"""
import json
from typing import Optional, List
from loguru import logger
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.config import settings
from app.services.mcp_service import mcp_service as svc
from app.services.ocr_service import ocr_service_monitor


# 创建 MCP Server 实例
mcp = MCPServer(
    name="knowledge-base-mcp",
    instructions=(
        "私有化知识库管理系统 MCP 服务。"
        "提供知识库检索、知识库管理、文件管理、文件导入、导入任务追踪、OCR 识别和系统监控能力。"
        "OCR 功能支持直接识别图片和扫描版 PDF (基于 RapidOCR + PP-OCRv4)。"
        "典型工作流：先 list_knowledge_bases 确认可用知识库，再用 knowledge_search 检索，"
        "需要 OCR 时可用 ocr_recognize_image 或 ocr_recognize_pdf 直接识别文件内容。"
    ),
)


def _to_text(data):
    """将任意数据序列化为文本，作为 MCP 工具返回的 content"""
    if isinstance(data, (dict, list)):
        return json.dumps(data, ensure_ascii=False, default=str)
    return str(data)


# ==================== 检索类工具 ====================

@mcp.tool()
async def knowledge_search(
    query: str,
    kb_name: Optional[str] = None,
    top_k: int = 5,
    score_threshold: float = 0.3,
    use_reranker: Optional[bool] = None,
    reranker_recall_top_k: Optional[int] = None,
):
    """
    搜索私有知识库，返回与问题最相关的文本片段。支持指定知识库或跨库检索。支持 Reranker 重排序优化。

    Args:
        query: 用户的搜索问题
        kb_name: 知识库名称，为空则搜索所有知识库
        top_k: 最终返回结果数量，默认5，最大50
        score_threshold: 相似度阈值(0-1)，默认0.3，低于此值的结果不返回
        use_reranker: 是否使用 Reranker 重排序（默认true）。开启后先召回指定数量再精排返回top_k条
        reranker_recall_top_k: Reranker第一阶段向量召回数量，默认10，需>=top_k，最大200

    Returns:
        JSON 字符串，包含 query/results/total/retrieval_info 字段
    """
    result = await svc.search(
        query=query,
        kb_name=kb_name,
        top_k=top_k,
        score_threshold=score_threshold,
        use_reranker=use_reranker,
        reranker_recall_top_k=reranker_recall_top_k,
    )
    return _to_text(result)


@mcp.tool()
async def get_document_detail(kb_name: str, chunk_id: str):
    """
    根据切片ID查询对应的原文内容，用于检索结果溯源。

    Args:
        kb_name: 知识库名称
        chunk_id: 切片ID (从 knowledge_search 结果中获取)
    """
    result = await svc.get_document_detail(kb_name, chunk_id)
    if not result:
        return _to_text({"error": "文档不存在", "kb_name": kb_name, "chunk_id": chunk_id})
    return _to_text(result)


# ==================== 知识库管理工具 ====================

@mcp.tool()
async def list_knowledge_bases():
    """查询所有可用的知识库集合信息，包括向量数量、状态等。"""
    result = await svc.list_knowledge_bases()
    return _to_text(result)


@mcp.tool()
async def create_knowledge_base(name: str, description: str = ""):
    """
    创建一个新的知识库。

    Args:
        name: 知识库名称 (1-100字符)
        description: 知识库描述 (可选)
    """
    result = await svc.create_knowledge_base(name, description)
    return _to_text(result)


@mcp.tool()
async def get_knowledge_base_detail(kb_name: str):
    """
    获取知识库详情，包括知识库信息和所有文件列表。

    Args:
        kb_name: 知识库名称
    """
    result = await svc.get_knowledge_base_detail(kb_name)
    return _to_text(result)


@mcp.tool()
async def delete_knowledge_base(kb_name: str):
    """
    删除知识库及其所有文件和向量数据 (不可恢复)。

    Args:
        kb_name: 知识库名称
    """
    result = await svc.delete_knowledge_base(kb_name)
    return _to_text(result)


# ==================== 文件管理工具 ====================

@mcp.tool()
async def list_files(kb_name: str):
    """
    列出知识库中的所有文件记录。

    Args:
        kb_name: 知识库名称
    """
    result = await svc.list_files(kb_name)
    return _to_text(result)


@mcp.tool()
async def delete_file(kb_name: str, file_id: int):
    """
    删除知识库中的指定文件及其所有向量。

    Args:
        kb_name: 知识库名称
        file_id: 文件ID
    """
    result = await svc.delete_file(kb_name, file_id)
    return _to_text(result)


@mcp.tool()
async def get_file_chunks(kb_name: str, file_id: int):
    """
    获取指定文件的所有切片内容，用于查看文件被切分后的具体内容。

    Args:
        kb_name: 知识库名称
        file_id: 文件ID
    """
    result = await svc.get_file_chunks(kb_name, file_id)
    return _to_text(result)


# ==================== 切片管理工具 ====================

@mcp.tool()
async def update_chunk(kb_name: str, chunk_id: str, text: str):
    """
    编辑指定切片的文本内容，系统会自动重新向量化并更新向量数据库中的点和 payload。

    Args:
        kb_name: 知识库名称
        chunk_id: 切片ID (从 get_file_chunks 或 knowledge_search 结果中获取)
        text: 修改后的切片文本内容
    """
    result = await svc.update_chunk(kb_name, chunk_id, text)
    return _to_text(result)


@mcp.tool()
async def delete_chunk(kb_name: str, chunk_id: str):
    """
    删除指定的切片，从向量数据库中永久移除该切片 (不可恢复)。
    删除后会自动递减对应文件的 chunk_count。

    Args:
        kb_name: 知识库名称
        chunk_id: 切片ID (从 get_file_chunks 或 knowledge_search 结果中获取)
    """
    result = await svc.delete_chunk(kb_name, chunk_id)
    return _to_text(result)


# ==================== 文件导入工具 ====================

@mcp.tool()
async def import_single_file(
    kb_name: str,
    file_path: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
):
    """
    从服务器本地文件路径导入单个文件到知识库。支持格式: pdf/docx/txt/md/png/jpg/jpeg/bmp/tiff/gif。
    图片和扫描版 PDF 会自动触发 OCR 识别。
    注意: file_path 必须是知识库服务器上的绝对路径。

    Args:
        kb_name: 知识库名称
        file_path: 服务器上的文件绝对路径，如 /data/docs/handbook.pdf
        chunk_size: 切片长度(字符数)，默认500
        chunk_overlap: 切片重叠长度(字符数)，默认50
    """
    result = await svc.import_single_file(
        kb_name=kb_name,
        file_path=file_path,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return _to_text(result)


@mcp.tool()
async def import_batch_files(
    kb_name: str,
    file_paths: List[str],
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
):
    """
    从服务器本地批量导入多个文件到知识库。传入文件路径列表，逐个处理并返回批量统计。

    Args:
        kb_name: 知识库名称
        file_paths: 服务器上的文件绝对路径列表，如 ["/data/d1.pdf", "/data/d2.pdf"]
        chunk_size: 切片长度(字符数)，默认500
        chunk_overlap: 切片重叠长度(字符数)，默认50
    """
    result = await svc.import_batch_files(
        kb_name=kb_name,
        file_paths=file_paths,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return _to_text(result)


@mcp.tool()
async def import_zip_file(
    kb_name: str,
    zip_path: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
):
    """
    从服务器本地 ZIP 压缩包批量导入文件到知识库。自动解压并导入所有支持格式的文件。

    Args:
        kb_name: 知识库名称
        zip_path: 服务器上的 ZIP 文件绝对路径，如 /data/batch_docs.zip
        chunk_size: 切片长度(字符数)，默认500
        chunk_overlap: 切片重叠长度(字符数)，默认50
    """
    result = await svc.import_zip_file(
        kb_name=kb_name,
        zip_path=zip_path,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return _to_text(result)


# ==================== 导入任务工具 ====================

@mcp.tool()
async def list_import_tasks(kb_name: Optional[str] = None):
    """
    查询导入任务列表，可按知识库筛选。

    Args:
        kb_name: 知识库名称 (可选，为空则返回所有)
    """
    result = await svc.list_import_tasks(kb_name)
    return _to_text(result)


@mcp.tool()
async def get_import_task(task_id: int):
    """
    查询导入任务详情，包括任务状态和每个文件的处理结果。

    Args:
        task_id: 任务ID
    """
    result = await svc.get_import_task(task_id)
    if not result:
        return _to_text({"error": "任务不存在", "task_id": task_id})
    return _to_text(result)


# ==================== 系统监控工具 ====================

@mcp.tool()
async def service_health_check():
    """检测知识库服务是否正常运行，包括 Qdrant 状态和嵌入模型状态。"""
    result = await svc.health_check()
    return _to_text(result)


@mcp.tool()
async def get_system_status():
    """获取系统状态概览，包括知识库数、文件数、向量数、今日导入数等。"""
    result = await svc.get_system_status()
    return _to_text(result)


@mcp.tool()
async def get_resource_info():
    """获取系统资源使用情况，包括磁盘、内存、向量存储大小等。"""
    result = await svc.get_resource_info()
    return _to_text(result)


# ==================== OCR 服务监控工具 ====================

@mcp.tool()
async def get_ocr_status():
    """
    获取 OCR 引擎完整状态，包括运行状态、引擎就绪、模型信息、内存占用和请求统计。

    Returns:
        JSON 字符串，包含 status/engine_ready/model_info/memory/stats 字段
    """
    status = ocr_service_monitor.get_status()
    return _to_text(status)


@mcp.tool()
async def get_ocr_model_info():
    """
    获取 OCR 模型详细信息，包括模型版本、文件列表、总大小等。

    Returns:
        JSON 字符串，包含 model_version/framework/model_files/total_model_size_mb 等字段
    """
    model_info = ocr_service_monitor.get_model_info()
    return _to_text(model_info)


@mcp.tool()
async def ocr_health_check():
    """
    OCR 服务健康检查，检测引擎是否就绪、模型文件是否完整。

    Returns:
        JSON 字符串，包含 healthy/status/engine_ready/model_files_ready/message 字段
    """
    status = ocr_service_monitor.get_status()
    model_info = ocr_service_monitor.get_model_info()
    healthy = status["engine_ready"] and model_info["model_files_ready"]
    return _to_text({
        "healthy": healthy,
        "status": status["status"],
        "engine_ready": status["engine_ready"],
        "model_files_ready": model_info["model_files_ready"],
        "message": "OCR 服务运行正常" if healthy else "OCR 服务未就绪",
    })


@mcp.tool()
async def reset_ocr_stats():
    """
    重置 OCR 统计数据（请求数、成功率、处理时间等）。

    Returns:
        JSON 字符串，包含 success 和 message 字段
    """
    ocr_service_monitor.reset_stats()
    return _to_text({"success": True, "message": "OCR 统计数据已重置"})


# ==================== OCR 识别工具 ====================

@mcp.tool()
async def ocr_recognize_image(
    file_path: str,
    page_num: int = 1,
):
    """
    使用 OCR 识别服务器上的图片文件，提取图片中的文字内容。
    支持格式: png, jpg, jpeg, bmp, tiff, gif

    Args:
        file_path: 服务器上的图片文件绝对路径，如 /data/images/screenshot.png
        page_num: 页码（用于多页场景，默认1）

    Returns:
        JSON 字符串，包含 text/lines/line_count/char_count 字段
    """
    import os
    from ocr_service.ocr_engine import ocr_engine

    if not os.path.isfile(file_path):
        return _to_text({"error": "文件不存在", "file_path": file_path})

    try:
        import time
        t0 = time.time()
        result = ocr_engine.recognize_image_file(file_path, page_num)
        elapsed_ms = (time.time() - t0) * 1000

        # 记录 OCR 统计
        ocr_service_monitor.record_request(
            pages=1,
            chars=result["char_count"],
            processing_time_ms=elapsed_ms,
            success=True,
        )

        result["processing_time_ms"] = round(elapsed_ms, 1)
        result["file_path"] = file_path
        return _to_text(result)
    except Exception as e:
        ocr_service_monitor.record_request(success=False)
        return _to_text({
            "error": "图片 OCR 识别失败",
            "file_path": file_path,
            "message": str(e),
        })


@mcp.tool()
async def ocr_recognize_pdf(
    file_path: str,
    max_pages: int = 50,
    dpi: int = 200,
):
    """
    使用 OCR 识别服务器上的 PDF 文件（扫描版 PDF 需用此工具，文本 PDF 建议用 import_single_file）。
    逐页渲染为图片后进行 OCR 识别。

    Args:
        file_path: 服务器上的 PDF 文件绝对路径，如 /data/docs/scanned.pdf
        max_pages: 最大处理页数（默认50），超过会报错
        dpi: 渲染 DPI（默认200），越高精度越高但速度越慢

    Returns:
        JSON 字符串，包含 total_pages/pages/full_text/char_count/processing_time_ms 字段
    """
    import os
    from ocr_service.ocr_engine import ocr_engine

    if not os.path.isfile(file_path):
        return _to_text({"error": "文件不存在", "file_path": file_path})

    file_size = os.path.getsize(file_path)
    # 读取 PDF 字节
    try:
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()
    except Exception as e:
        return _to_text({
            "error": "文件读取失败",
            "file_path": file_path,
            "message": str(e),
        })

    try:
        import time
        t0 = time.time()
        result = ocr_engine.recognize_pdf(pdf_bytes, max_pages, dpi)
        elapsed_ms = (time.time() - t0) * 1000

        # 记录 OCR 统计
        ocr_service_monitor.record_request(
            pages=result["total_pages"],
            chars=result["char_count"],
            processing_time_ms=elapsed_ms,
            success=True,
        )

        result["processing_time_ms"] = round(elapsed_ms, 1)
        result["file_path"] = file_path
        result["file_size_mb"] = round(file_size / 1024 / 1024, 2)
        return _to_text(result)
    except ValueError as e:
        ocr_service_monitor.record_request(success=False)
        return _to_text({
            "error": "PDF 页数超出限制",
            "file_path": file_path,
            "message": str(e),
            "max_pages": max_pages,
        })
    except Exception as e:
        ocr_service_monitor.record_request(success=False)
        return _to_text({
            "error": "PDF OCR 识别失败",
            "file_path": file_path,
            "message": str(e),
        })


# ==================== 启动入口 ====================

def run_stdio():
    """以 stdio 传输启动 MCP Server (供 Claude Desktop 等本地客户端使用)"""
    logger.info("启动 MCP Server (stdio 传输)...")
    mcp.run(transport="stdio")


def run_http(host: str = "0.0.0.0", port: int = 9000):
    """以 Streamable HTTP 传输独立启动 MCP Server"""
    logger.info(f"启动 MCP Server (Streamable HTTP) on {host}:{port}...")
    mcp.run(transport="streamable-http", host=host, port=port)


def get_streamable_http_app():
    """获取 Streamable HTTP ASGI 应用，用于挂载到 FastAPI 主应用"""
    allowed_hosts = [
        value.strip() for value in settings.MCP_ALLOWED_HOSTS.split(",") if value.strip()
    ]
    allowed_origins = [
        value.strip() for value in settings.MCP_ALLOWED_ORIGINS.split(",") if value.strip()
    ]
    return mcp.streamable_http_app(
        host=settings.MCP_SERVER_HOST,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        ),
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        run_http()
    else:
        run_stdio()
