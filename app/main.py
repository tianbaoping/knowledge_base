import os
import sys
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from loguru import logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database.sqlite_db import db_manager
from app.services.qdrant_service import qdrant_service
from app.services.embedding_service import embedding_service
from app.services.reranker_service import reranker_service
from app.services.import_service import import_service
from app.services.parser_service import document_parser
from app.services.ocr_service import ocr_service_monitor

from app.routers.kb_router import router as kb_router
from app.routers.import_router import router as import_router
from app.routers.mcp_router import router as mcp_router
from app.routers.monitor_router import router as monitor_router
from app.routers.ocr_router import router as ocr_router
from app.routers.ws_router import router as ws_router

# 真正的 MCP Server (基于官方 mcp SDK，符合 MCP 2025-06-18 规范)
from app.mcp_server.server import get_streamable_http_app as get_mcp_http_app


def setup_logging():
    """配置双日志系统: 控制台(Journal) + 文件(轮转)"""
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    # 移除默认 logger 配置
    logger.remove()

    # 日志格式
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # 1. 控制台输出 (用于 systemd journal)
    logger.add(
        sys.stdout,
        format=log_format,
        level="INFO",
        colorize=True,
    )

    # 2. 应用主日志文件 (带轮转)
    logger.add(
        str(log_dir / "app.log"),
        format=log_format,
        level="DEBUG",
        rotation="100 MB",        # 单文件最大 100MB
        retention="10 days",      # 保留 10 天
        compression="gz",         # 压缩旧日志
        enqueue=True,             # 线程安全
        backtrace=True,           # 异常回溯
        diagnose=False,           # 生产环境关闭诊断
    )

    # 3. 错误日志单独输出
    logger.add(
        str(log_dir / "error.log"),
        format=log_format,
        level="ERROR",
        rotation="50 MB",
        retention="30 days",
        compression="gz",
        enqueue=True,
    )

    return log_dir


def cleanup_old_logs():
    """清理超过配额的旧日志文件"""
    log_dir = Path(settings.LOG_DIR)
    if not log_dir.exists():
        return

    # 日志目录最大配额 (2GB)
    MAX_LOG_DIR_SIZE = 2 * 1024 * 1024 * 1024

    # 计算当前日志目录大小
    total_size = 0
    log_files = []
    for f in log_dir.iterdir():
        if f.is_file():
            size = f.stat().st_size
            total_size += size
            log_files.append((f, size, f.stat().st_mtime))

    # 如果超过配额，按修改时间删除最旧的文件
    if total_size > MAX_LOG_DIR_SIZE:
        logger.warning(f"日志目录大小 ({total_size / 1024 / 1024:.1f}MB) 超过配额 ({MAX_LOG_DIR_SIZE / 1024 / 1024:.0f}MB)，开始清理...")

        # 按修改时间排序 (最旧的在前)
        log_files.sort(key=lambda x: x[2])

        freed = 0
        for f, size, mtime in log_files:
            if total_size - freed <= MAX_LOG_DIR_SIZE * 0.7:  # 清理到 70% 配额以下
                break
            try:
                f.unlink()
                freed += size
                logger.info(f"  已删除旧日志: {f.name} ({size / 1024:.0f}KB)")
            except OSError as e:
                logger.error(f"  删除日志失败 {f.name}: {e}")

        logger.info(f"日志清理完成，释放 {freed / 1024 / 1024:.1f}MB")


async def _load_embedding_in_background():
    try:
        logger.info("[3/5] 后台加载嵌入模型中...")
        await embedding_service.init()
        info = embedding_service.get_model_info()
        if info.get("demo_mode"):
            logger.warning(f"  ⚠ 嵌入模型加载失败，已切换为演示模式(Mock Embedding)")
            logger.warning(f"    原因: {info.get('init_error', '未知')}")
            logger.warning(f"    生产环境请配置有效的嵌入模型后重启")
        else:
            logger.info(f"  ✓ 嵌入模型加载成功: {info['model_name']}")
    except Exception as e:
        logger.error(f"  ✗ 嵌入模型加载异常: {e}")


async def _load_reranker_in_background():
    try:
        logger.info("[4/5] 后台加载重排模型中...")
        await reranker_service.init()
        info = reranker_service.get_model_info()
        if info.get("demo_mode"):
            logger.warning(f"  ⚠ 重排模型加载失败，已切换为演示模式(Mock Rerank)")
            logger.warning(f"    原因: {info.get('init_error', '未知')}")
        else:
            logger.info(f"  ✓ 重排模型加载成功: {info['model_name']}")
    except Exception as e:
        logger.error(f"  ✗ 重排模型加载异常: {e}")


async def _load_ocr_in_background():
    """后台加载 OCR 引擎"""
    try:
        logger.info("[5/5] 后台加载 OCR 引擎中...")
        from ocr_service.ocr_engine import ocr_engine

        # 触发懒加载
        if not ocr_engine.is_ready():
            ocr_instance = ocr_engine.ocr  # 触发模型加载

        # 注入到文档解析器
        document_parser.set_ocr_engine(ocr_engine)

        # 注入到状态监控
        ocr_service_monitor.set_engine(ocr_engine)

        logger.info("  ✓ OCR 引擎加载成功 (PP-OCRv4)")
        logger.info("    图片识别: 支持 jpg/png/bmp/tiff/gif")
        logger.info("    PDF OCR: 自动检测扫描版并 OCR 处理")
    except ImportError as e:
        logger.warning(f"  ⚠ OCR 引擎加载失败: {e}")
        logger.warning(f"    请安装: pip install rapidocr-onnxruntime")
        logger.warning(f"    OCR 功能将不可用，但文本 PDF/Word/TXT 解析仍可正常使用")
    except Exception as e:
        logger.error(f"  ✗ OCR 引擎加载异常: {e}")
        logger.warning(f"    OCR 功能将不可用，但文本类文件解析仍可正常使用")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化日志系统
    log_dir = setup_logging()

    logger.info("=" * 60)
    logger.info(f"知识库管理系统 v{settings.APP_VERSION} 启动中...")
    logger.info(f"日志目录: {log_dir}")
    logger.info("=" * 60)

    # 启动时清理旧日志
    cleanup_old_logs()

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    os.makedirs(settings.QDRANT_DATA_DIR, exist_ok=True)

    logger.info("[1/3] 初始化SQLite元数据库...")
    await db_manager.init()
    await import_service.cleanup_stale_records()
    logger.info("  ✓ SQLite初始化完成")

    logger.info("[2/3] 连接Qdrant向量数据库...")
    try:
        await qdrant_service.init()
        logger.info("  ✓ Qdrant连接成功(本地模式)")
    except Exception as e:
        logger.error(f"  ✗ Qdrant连接失败: {e}")
        logger.warning("  将以降级模式运行，部分功能可能不可用")

    asyncio.create_task(_load_embedding_in_background())
    asyncio.create_task(_load_reranker_in_background())
    asyncio.create_task(_load_ocr_in_background())

    # 启动 MCP Server 的 session manager 任务组
    if _mcp_session_cm is not None:
        await _mcp_session_cm.__aenter__()
        logger.info("  ✓ MCP session manager 已启动")

    logger.info("=" * 60)
    logger.info(f"知识库管理系统启动完成!")
    logger.info(f"  Web界面:  http://{settings.APP_HOST}:{settings.APP_PORT}")
    logger.info(f"  API文档:  http://{settings.APP_HOST}:{settings.APP_PORT}/docs")
    logger.info(f"  MCP服务(标准):  http://{settings.APP_HOST}:{settings.APP_PORT}/mcp  (MCP 2025-06-18 规范)")
    logger.info(f"  MCP服务(兼容):  http://{settings.APP_HOST}:{settings.APP_PORT}/api/mcp (旧版 REST)")
    logger.info(f"  MCP鉴权:  API Key = {settings.MCP_API_KEY}")
    logger.info(f"  OCR状态:  http://{settings.APP_HOST}:{settings.APP_PORT}/api/ocr/status")
    logger.info(f"  导入进度:  ws://{settings.APP_HOST}:{settings.APP_PORT}/ws/import-progress")
    logger.info("=" * 60)

    yield

    # 停止 MCP Server 的 session manager
    if _mcp_session_cm is not None:
        await _mcp_session_cm.__aexit__(None, None, None)
        logger.info("MCP session manager 已停止")

    logger.info("系统关闭中...")
    await db_manager.close()
    logger.info("系统已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    description="基于Qdrant的知识库管理系统 - 支持PDF/Word图文解析、批量导入、MCP协议服务",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(kb_router, prefix="/api")
app.include_router(import_router, prefix="/api")
app.include_router(mcp_router, prefix="/api")
app.include_router(monitor_router, prefix="/api")
app.include_router(ocr_router, prefix="/api")
app.include_router(ws_router)

# 挂载真正的 MCP Server (Streamable HTTP 传输)
# 主流 MCP 客户端 (Claude Desktop / Cursor / Cline) 通过此端点对接
# 端点: POST /mcp (JSON-RPC 2.0)
# 使用纯 ASGI 中间件转发 + lifespan 集成，确保 session manager 任务组正确初始化
_mcp_asgi_app = None
_mcp_session_cm = None
try:
    _mcp_asgi_app = get_mcp_http_app()
    # session_manager.run() 是 async context manager，需要在 lifespan 中启动
    from app.mcp_server.server import mcp as _mcp_server
    _mcp_session_cm = _mcp_server.session_manager.run()

    class _MCPASGIMiddleware:
        def __init__(self, app, mcp_app=None):
            self.app = app
            self.mcp_app = mcp_app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http" and scope.get("path") == "/mcp":
                await self.mcp_app(scope, receive, send)
            else:
                await self.app(scope, receive, send)

    app.add_middleware(_MCPASGIMiddleware, mcp_app=_mcp_asgi_app)
    logger.info("MCP Server (Streamable HTTP) 已挂载到 /mcp 端点")
except Exception as e:
    logger.warning(f"MCP Server 挂载失败 (mcp SDK 未安装?): {e}")
    logger.warning("请执行: pip install mcp>=2.0.0")


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=False,
        log_level="info",
    )