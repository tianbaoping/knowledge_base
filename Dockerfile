# ============================================================
# 知识库管理系统 - Dockerfile (x86_64 优先 + ARM64 兼容)
# ============================================================
# 默认构建 x86_64 架构，国内镜像源加速
# 构建:
#   docker build -t kb-app:latest .
#   docker buildx build --platform linux/amd64,linux/arm64 -t kb-app .
# ============================================================

FROM python:3.12-slim

ARG BUILD_DATE
ARG VERSION=1.0.0

LABEL org.opencontainers.image.title="知识库管理系统" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

# ============================================================
# 1. 配置国内 APT 镜像源 (清华) + 安装系统依赖
# ============================================================
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null || true && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        libgomp1 \
        libgl1 \
        libglib2.0-0 \
        file \
    && (apt-get install -y --no-install-recommends p7zip-full || true) \
    && (apt-get install -y --no-install-recommends unrar || \
        apt-get install -y --no-install-recommends unrar-free || true) \
    && (apt-get install -y --no-install-recommends antiword || true) \
    && (apt-get install -y --no-install-recommends catdoc || true) \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# 2. 配置国内 PIP 镜像源 (清华) + 安装 Python 依赖
#    先安装 CPU 版 torch，避免拉取 NVIDIA CUDA 包 (节省 ~2GB)
# ============================================================
COPY requirements.txt .

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn && \
    pip install --no-cache-dir --upgrade pip && \
    # 先安装 CPU 版 torch (避免拉取 NVIDIA CUDA 包，节省 ~2GB)
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    # 再安装其余依赖
    pip install --no-cache-dir -r requirements.txt

# ============================================================
# 3. 复制项目源码
# ============================================================
COPY app/ ./app/
COPY ocr_service/ ./ocr_service/

# 创建数据目录
RUN mkdir -p /app/data/uploads /app/data/logs /app/data/qdrant /app/data/ocr_temp /app/models

# ============================================================
# 4. 环境变量配置
# ============================================================
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODEL_DEVICE=cpu \
    QDRANT_LOCATION=data/qdrant \
    UPLOAD_DIR=data/uploads \
    LOG_DIR=data/logs \
    SQLITE_DB_PATH=data/metadata.db \
    MODEL_LOCAL_PATH=models/BAAI_bge-small-zh-v1.5 \
    RERANKER_LOCAL_PATH=models/BAAI_bge-reranker-base \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["python", "-m", "app.main"]
