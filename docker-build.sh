#!/bin/bash
# ============================================================
# 知识库管理系统 - 多架构 Docker 镜像构建脚本
# ============================================================
# 支持: linux/amd64 (x86_64) + linux/arm64 (ARM)
# 
# 用法:
#   ./docker-build.sh              # 构建多架构镜像 (需要 buildx)
#   ./docker-build.sh --local      # 仅构建当前架构 (无需 buildx)
#   ./docker-build.sh --push       # 构建并推送到镜像仓库
#   ./docker-build.sh --save       # 构建并导出为 tar 包
# ============================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
echo_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
echo_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 项目配置
IMAGE_NAME="kb-app"
IMAGE_TAG="${IMAGE_NAME}:latest"
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 模式: multi (多架构) / local (本地架构) / push (推送) / save (导出)
MODE="multi"

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --local)  MODE="local"; shift ;;
        --push)   MODE="push"; shift ;;
        --save)   MODE="save"; shift ;;
        --tag)    IMAGE_TAG="$2"; shift 2 ;;
        --help|-h)
            echo "用法: $0 [--local|--push|--save] [--tag <name:tag>]"
            echo ""
            echo "选项:"
            echo "  (默认)    构建多架构镜像 (linux/amd64 + linux/arm64)"
            echo "  --local   仅构建当前架构 (无需 buildx)"
            echo "  --push    构建并推送到镜像仓库"
            echo "  --save    构建并导出为 tar 文件"
            echo "  --tag     指定镜像标签 (默认: kb-app:latest)"
            exit 0
            ;;
        *) echo_error "未知参数: $1"; exit 1 ;;
    esac
done

cd "$PROJECT_DIR"

echo ""
echo_info "=========================================="
echo_info " 知识库管理系统 - Docker 镜像构建"
echo_info "=========================================="
echo_info " 项目目录: $PROJECT_DIR"
echo_info " 镜像名称: $IMAGE_TAG"
echo_info " 构建模式: $MODE"
echo_info " 构建时间: $BUILD_DATE"
echo_info "=========================================="
echo ""

# ============================================================
# 步骤 1: 检查 Docker 环境
# ============================================================
echo_info "[1/4] 检查 Docker 环境..."

if ! command -v docker &> /dev/null; then
    echo_error "Docker 未安装，请先安装 Docker"
    echo_info "  Ubuntu:   sudo apt-get install docker.io"
    echo_info "  CentOS:   sudo yum install docker"
    echo_info "  macOS:    brew install --cask docker"
    exit 1
fi

DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
echo_ok "Docker 版本: $DOCKER_VERSION"

# ============================================================
# 步骤 2: 检查 Dockerfile 和项目文件
# ============================================================
echo_info "[2/4] 检查项目文件..."

if [ ! -f "Dockerfile" ]; then
    echo_error "未找到 Dockerfile"
    exit 1
fi
echo_ok "Dockerfile 存在"

if [ ! -f "requirements.txt" ]; then
    echo_error "未找到 requirements.txt"
    exit 1
fi
echo_ok "requirements.txt 存在"

if [ ! -d "app" ]; then
    echo_error "未找到 app/ 目录"
    exit 1
fi
echo_ok "app/ 目录存在"

if [ ! -d "ocr_service" ]; then
    echo_error "未找到 ocr_service/ 目录"
    exit 1
fi
echo_ok "ocr_service/ 目录存在"

# 检查模型目录
if [ -d "models" ] && [ "$(ls -A models 2>/dev/null)" ]; then
    MODEL_SIZE=$(du -sh models 2>/dev/null | cut -f1)
    echo_ok "模型目录存在: models/ ($MODEL_SIZE)"
    echo_warn "注意: 模型不打包进镜像，运行时通过 volume 挂载"
else
    echo_warn "模型目录为空或不存在"
    echo_warn "容器启动时会尝试从 HuggingFace 在线下载模型"
fi

echo ""

# ============================================================
# 步骤 3: 构建镜像
# ============================================================
echo_info "[3/4] 开始构建 Docker 镜像..."

BUILD_ARGS="--build-arg BUILD_DATE=${BUILD_DATE} --build-arg VERSION=1.0.0"

case $MODE in
    # ---- 多架构构建 (需要 buildx) ----
    multi)
        echo_info "构建多架构镜像: linux/amd64 + linux/arm64"
        
        # 检查 buildx
        if ! docker buildx version &> /dev/null; then
            echo_warn "docker buildx 不可用，尝试启用..."
            docker buildx create --name multiarch --use 2>/dev/null || true
            if ! docker buildx version &> /dev/null; then
                echo_error "docker buildx 不可用"
                echo_info "请安装 buildx 或使用 --local 模式"
                echo_info "  启用 buildx: docker buildx create --use"
                exit 1
            fi
        fi
        
        # 确保 buildx builder 支持 multi-platform
        BUILDER_NAME=$(docker buildx inspect --name 2>/dev/null || echo "")
        if [ -z "$BUILDER_NAME" ] || [ "$BUILDER_NAME" = "default" ]; then
            echo_info "创建多架构 builder..."
            docker buildx create --name kb-builder --driver docker-container --use
            docker buildx inspect --bootstrap
        fi
        
        docker buildx build \
            --platform linux/amd64,linux/arm64 \
            $BUILD_ARGS \
            -t "$IMAGE_TAG" \
            --load \
            .
        
        echo_ok "多架构镜像构建完成: $IMAGE_TAG"
        ;;

    # ---- 本地架构构建 (最简单) ----
    local)
        echo_info "构建本地架构镜像..."
        docker build $BUILD_ARGS -t "$IMAGE_TAG" .
        echo_ok "本地镜像构建完成: $IMAGE_TAG"
        ;;

    # ---- 构建并推送 ----
    push)
        echo_info "构建并推送多架构镜像..."
        docker buildx build \
            --platform linux/amd64,linux/arm64 \
            $BUILD_ARGS \
            -t "$IMAGE_TAG" \
            --push \
            .
        echo_ok "镜像推送完成: $IMAGE_TAG"
        ;;

    # ---- 构建并导出为 tar ----
    save)
        TARBALL="${IMAGE_NAME}-$(uname -m)-$(date +%Y%m%d).tar"
        echo_info "构建并导出为 tar: $TARBALL"
        
        docker build $BUILD_ARGS -t "$IMAGE_TAG" .
        docker save -o "$TARBALL" "$IMAGE_TAG"
        
        TARBALL_SIZE=$(du -sh "$TARBALL" | cut -f1)
        echo_ok "镜像导出完成: $TARBALL ($TARBALL_SIZE)"
        echo_info "在目标机器加载: docker load -i $TARBALL"
        ;;
esac

echo ""

# ============================================================
# 步骤 4: 验证镜像
# ============================================================
echo_info "[4/4] 验证镜像..."

if [ "$MODE" = "multi" ] || [ "$MODE" = "local" ] || [ "$MODE" = "save" ]; then
    # 检查镜像是否存在
    if docker image inspect "$IMAGE_TAG" &> /dev/null; then
        IMAGE_SIZE=$(docker image inspect "$IMAGE_TAG" --format='{{.Size}}' 2>/dev/null)
        IMAGE_SIZE_MB=$((IMAGE_SIZE / 1024 / 1024))
        echo_ok "镜像验证通过: $IMAGE_TAG (${IMAGE_SIZE_MB}MB)"
    else
        echo_warn "镜像未找到 (多架构构建使用 --load 时可能不显示)"
    fi
fi

echo ""
echo_info "=========================================="
echo_info " 构建完成!"
echo_info "=========================================="
echo_info ""
echo_info " 运行镜像:"
echo_info "   docker run -d --name kb -p 8000:8000 \\"
echo_info "     -v kb_data:/app/data \\"
echo_info "     -v \$(pwd)/models:/app/models:ro \\"
echo_info "     $IMAGE_TAG"
echo_info ""
echo_info " 或使用 Docker Compose:"
echo_info "   docker compose up -d"
echo_info ""
echo_info " 访问地址: http://localhost:8000"
echo_info "=========================================="
