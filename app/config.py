from pydantic_settings import BaseSettings
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent

_UPLOAD_DIR = str(_BASE_DIR / "data" / "uploads")
_LOG_DIR = str(_BASE_DIR / "data" / "logs")
_QDRANT_DATA_DIR = "data/qdrant"
_SQLITE_DB_PATH = str(_BASE_DIR / "data" / "metadata.db")

class Settings(BaseSettings):
    BASE_DIR: str = str(_BASE_DIR)
    APP_NAME: str = "知识库管理系统"
    APP_VERSION: str = "1.0.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_LOCATION: str = _QDRANT_DATA_DIR

    UPLOAD_DIR: str = _UPLOAD_DIR
    LOG_DIR: str = _LOG_DIR
    QDRANT_DATA_DIR: str = _QDRANT_DATA_DIR
    SQLITE_DB_PATH: str = _SQLITE_DB_PATH

    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"
    EMBEDDING_DIM: int = 512
    MODEL_LOCAL_PATH: str = str(_BASE_DIR / "models" / "BAAI_bge-small-zh-v1.5")

    RERANKER_MODEL: str = "BAAI/bge-reranker-base"
    RERANKER_LOCAL_PATH: str = str(_BASE_DIR / "models" / "BAAI_bge-reranker-base")
    RERANKER_ENABLED: bool = True
    RERANKER_RECALL_TOP_K: int = 10
    RERANKER_FINAL_TOP_K: int = 5

    # 模型推理设备: "cpu" (默认,最稳定) / "cuda" / "auto"
    # 注意: 部分本地模型在 CUDA 加载时会触发 "meta tensor" 错误,
    # 如遇此问题请保持 "cpu" 或删除本地模型重新下载完整权重。
    MODEL_DEVICE: str = "cpu"

    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    CHUNK_SEPARATOR: str = ""

    MAX_FILE_SIZE: int = 100 * 1024 * 1024
    MAX_CONCURRENT_IMPORTS: int = 5

    MCP_SERVER_HOST: str = "0.0.0.0"
    MCP_SERVER_PORT: int = 8001
    MCP_API_KEY: str = "kb-mcp-secret-key-2024"
    MCP_ALLOWED_HOSTS: str = "127.0.0.1:*,localhost:*,[::1]:*,192.168.0.3:*"
    MCP_ALLOWED_ORIGINS: str = (
        "http://127.0.0.1:*,http://localhost:*,http://[::1]:*,http://192.168.0.3:*"
    )

    SUPPORTED_FORMATS: dict = {
        "pdf": "PDF文档",
        "docx": "Word文档",
        "doc": "Word文档(旧版)",
        "txt": "纯文本",
        "md": "Markdown",
        "ofd": "OFD版式文档",
        "png": "PNG图片",
        "jpg": "JPEG图片",
        "jpeg": "JPEG图片",
        "bmp": "BMP图片",
        "tiff": "TIFF图片",
        "tif": "TIFF图片",
        "gif": "GIF图片",
    }

    class Config:
        extra = "ignore"

settings = Settings()
