#!/usr/bin/env bash
# =========================================================================
# Knowledge Base System - Linux Packaging Script
# -------------------------------------------------------------------------
# Usage:
#   ./pack.sh                      # 完整打包 (自动检测并打包当前 conda 环境 + models)
#   ./pack.sh --no-model           # 不含模型 (目标机器自己下载模型)
#   ./pack.sh --no-env             # 不打包 conda 环境 (目标机器自己 pip 安装)
#   ./pack.sh --pack-env kb-env    # 指定 conda 环境名打包到 envs/
#   ./pack.sh --pack-env           # 等同于默认行为 (打包当前激活的 conda 环境)
# =========================================================================

set -euo pipefail

# ------- 参数解析 -------
NO_MODEL=0
NO_ENV=0
PACK_ENV=""

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

知识管理系统 Linux 一键打包脚本

Options:
      --no-model           跳过 models/ 目录 (目标机器自行下载模型)
      --no-env             跳过 conda 环境打包 (目标机器自行 pip 安装)
      --pack-env [NAME]    指定要打包的 conda 环境名
                           不指定时自动取当前 \$CONDA_DEFAULT_ENV
                           (默认: 如果当前在 conda 环境中, 自动打包)
  -h, --help               显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-model)  NO_MODEL=1; shift ;;
        --no-env)    NO_ENV=1;   shift ;;
        --pack-env)
            shift
            if [[ $# -gt 0 && "$1" != --* ]]; then
                PACK_ENV="$1"; shift
            else
                PACK_ENV="${CONDA_DEFAULT_ENV:-kb-env}"
            fi
            ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# ------- 基本路径和时间戳 -------
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M)"
PACKAGE_NAME="knowledge_base_deploy_Linux_${TIMESTAMP}"
TMP_DIR="$(mktemp -d)/${PACKAGE_NAME}"
mkdir -p "$TMP_DIR"

# ------- 彩色输出 -------
C_RESET="\033[0m"
C_CYAN="\033[1;36m"
C_GREEN="\033[1;32m"
C_YELLOW="\033[1;33m"
C_RED="\033[1;31m"
C_DARK="\033[2;37m"

echo -e "${C_CYAN}========================================${C_RESET}"
echo -e "${C_CYAN}  Knowledge Base System - Linux Pack   ${C_RESET}"
echo -e "${C_CYAN}========================================${C_RESET}"

# ------- 自动检测并打包 conda 环境 -------
# 如果没有手动指定 --pack-env, 自动检测当前 conda 环境
if [[ -z "$PACK_ENV" && "$NO_ENV" -eq 0 ]]; then
    if [[ -n "${CONDA_DEFAULT_ENV:-}" ]]; then
        PACK_ENV="$CONDA_DEFAULT_ENV"
        echo -e "\n${C_DARK}[自动检测] 当前 conda 环境: $PACK_ENV, 将自动打包${C_RESET}"
    fi
fi

if [[ -n "$PACK_ENV" ]]; then
    echo -e "\n${C_YELLOW}[1/3] 打包 conda 环境: $PACK_ENV${C_RESET}"

    # 设置 PATH 以包含 conda
    export PATH="/home/xunshi/miniconda3/bin:$PATH"

    # 检查 conda-pack 是否已安装在目标环境中
    CONDA_ENV_PATH="/home/xunshi/miniconda3/envs/$PACK_ENV"
    if [[ ! -f "$CONDA_ENV_PATH/bin/conda-pack" ]]; then
        echo -e "${C_YELLOW}  conda-pack 未安装, 正在安装到 $PACK_ENV 环境...${C_RESET}"
        "$CONDA_ENV_PATH/bin/pip" install conda-pack --quiet
    fi

    mkdir -p envs
    OUT_TAR="${PROJECT_DIR}/envs/knowledge_base_env.tar.gz"
    echo -e "  -> 输出到: $OUT_TAR (这一步可能需要 1-3 分钟)"

    # 使用 --prefix 参数直接指定环境路径
    if [[ -f "$CONDA_ENV_PATH/bin/conda-pack" ]]; then
        "$CONDA_ENV_PATH/bin/conda-pack" --prefix "$CONDA_ENV_PATH" -o "$OUT_TAR" --ignore-missing-files --force -q 2>&1
    else
        /home/xunshi/miniconda3/bin/conda-pack -n "$PACK_ENV" -o "$OUT_TAR" --ignore-missing-files --force -q 2>&1
    fi

    echo -e "${C_GREEN}  [OK] conda 环境打包完成${C_RESET}"
else
    echo -e "\n${C_YELLOW}[1/3] 未检测到 conda 环境, 跳过环境打包${C_RESET}"
    echo -e "${C_DARK}  提示: 目标机器将需要 conda create + pip install${C_RESET}"
    echo -e "${C_DARK}  如需离线部署, 请先 conda activate <env> 再运行 pack.sh${C_RESET}"
fi

# ------- 检查打包内容 -------
INCLUDE_ITEMS=(
    # 核心代码
    "app"
    # 模型和环境
    "models"
    "envs"
    # Python 依赖
    "requirements.txt"
    # 模型下载
    "download_model.py"
    # 部署脚本
    "deploy.ps1"
    "deploy.sh"
    "run.bat"
    # 打包脚本
    "pack.ps1"
    "pack.sh"
    # Docker 部署
    "Dockerfile"
    "docker-compose.yml"
    # MCP 对接文档
    "MCP_SKILL.md"
    # 项目文档
    "README.md"
    "DEPLOY.md"
    # 工具脚本
    "cleanup_stale.py"
    # 测试脚本
    "run_full_test.py"
    "test_api.py"
    # OCR 服务（RapidOCR / ONNX Runtime）
    "ocr_service"
    "test_ocr_service.py"
    # OFD 解析服务
    "ofd_service"
    # 配置文件
    ".env.example"
    # systemd 服务配置
    "knowledge-base.service"
)

echo -e "\n${C_YELLOW}[2/3] 打包内容清单:${C_RESET}"
for item in "${INCLUDE_ITEMS[@]}"; do
    src="$PROJECT_DIR/$item"
    skip_reason=""

    if [[ ! -e "$src" ]]; then
        echo -e "  ${C_RED}[MISS]${C_RESET} $item"
        continue
    fi

    if   [[ "$NO_MODEL" -eq 1 && "$item" == "models" ]]; then skip_reason="no model";
    elif [[ "$NO_ENV"   -eq 1 && "$item" == "envs"   ]]; then skip_reason="no env";
    fi

    if [[ -n "$skip_reason" ]]; then
        echo -e "  ${C_DARK}[SKIP]${C_RESET} $item ($skip_reason)"
        continue
    fi

    if [[ -d "$src" ]]; then
        size_mb=$(du -sm "$src" 2>/dev/null | awk '{print $1}')
        echo -e "  ${C_GREEN}[OK]  ${C_RESET} $item/  (~${size_mb}MB)"
    else
        echo -e "  ${C_GREEN}[OK]  ${C_RESET} $item"
    fi
done

# ------- 拷贝文件到临时目录, 排除缓存 -------
echo -e "\n${C_YELLOW}  拷贝文件 (排除 __pycache__ / *.pyc / .git / data/)...${C_RESET}"
for item in "${INCLUDE_ITEMS[@]}"; do
    src="$PROJECT_DIR/$item"
    [[ ! -e "$src" ]] && continue
    [[ "$NO_MODEL" -eq 1 && "$item" == "models" ]] && continue
    [[ "$NO_ENV"   -eq 1 && "$item" == "envs"   ]] && continue

    dst="$TMP_DIR/$item"
    if [[ -d "$src" ]]; then
        mkdir -p "$dst"
        if command -v rsync >/dev/null 2>&1; then
            rsync -a --quiet \
                --exclude '__pycache__/' \
                --exclude '*.pyc'        \
                --exclude '.git/'        \
                --exclude '.pytest_cache/' \
                --exclude 'node_modules/' \
                "$src/" "$dst/"
        else
            cp -a "$src/." "$dst/"
            find "$dst" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
            find "$dst" -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true
            find "$dst" -type d -name '.git' -exec rm -rf {} + 2>/dev/null || true
            find "$dst" -type d -name 'node_modules' -exec rm -rf {} + 2>/dev/null || true
            find "$dst" -type f -name '*.pyc' -delete 2>/dev/null || true
        fi
    else
        cp -f "$src" "$dst"
    fi
done

# ------- 自动修正 pack.sh / deploy.sh 执行权限 (避免到目标机后忘记 chmod +x) -------
chmod +x "$TMP_DIR/pack.sh" "$TMP_DIR/deploy.sh" 2>/dev/null || true

# ------- 创建 data 目录占位 (上传/日志/qdrant/ocr_temp) -------
DATA_DIRS=(
    "data/uploads"
    "data/logs"
    "data/qdrant"
    "data/ocr_temp"
)
for d in "${DATA_DIRS[@]}"; do
    mkdir -p "$TMP_DIR/$d"
    touch "$TMP_DIR/$d/.gitkeep"
done

# 额外放一个 README_LINUX_PACK.txt 方便用户知道用什么脚本
cat > "$TMP_DIR/README_LINUX_PACK.txt" <<'EOF'
本目录为知识库管理系统 Linux 部署包
=====================================

(1) 如果包里有 envs/knowledge_base_env.tar.gz:
      - 无需 conda-pack / 无需 pip 联网安装
      - 直接运行:  chmod +x deploy.sh && ./deploy.sh --skip-model

(2) 如果包里没有 envs/:
      - 目标机器需要有 conda/python3
      - 运行:  chmod +x deploy.sh && ./deploy.sh

(3) 如果包里没有 models/:
      - 运行:  python download_model.py    先下载嵌入模型
      - 或把之前下载好的模型文件手动拷贝到 models/ 目录

(4) OCR 功能说明:
      - OCR 模型已预置在 ocr_service/models/ 目录
      - 支持图片 (jpg/png/bmp/tiff/gif) 和扫描版 PDF 自动识别
      - OCR 状态查看: 访问 http://localhost:8000/api/ocr/status
      - 如需更换模型: 替换 ocr_service/models/ 下的 3 个 ONNX 文件

(5) 导入进度实时查看:
      - WebSocket 端点: ws://localhost:8000/ws/import-progress
      - 前端管理界面自动显示文件解析进度和 OCR 状态

访问地址: http://<服务器IP>:8000
EOF

# ------- 压缩 -------
echo -e "\n${C_YELLOW}[3/3] 压缩 tar.gz...${C_RESET}"
OUTPUT_PATH="${PROJECT_DIR}/${PACKAGE_NAME}.tar.gz"
rm -f "$OUTPUT_PATH"

# 统计大小 & 压缩 (zstd 更快,但为了兼容性保留 gzip)
tar -czf "$OUTPUT_PATH" -C "$(dirname "$TMP_DIR")" "$PACKAGE_NAME"

# ------- 收尾 -------
rm -rf "$(dirname "$TMP_DIR")"

SIZE_MB=$(du -sm "$OUTPUT_PATH" 2>/dev/null | awk '{print $1}')
SIZE_READABLE="${SIZE_MB}MB"
if [[ "$SIZE_MB" -ge 1024 ]]; then
    SIZE_READABLE="$(awk -v m="$SIZE_MB" 'BEGIN{printf "%.1f GB", m/1024}')"
fi

echo -e "\n${C_CYAN}========================================${C_RESET}"
echo -e "${C_GREEN}  Pack Done!${C_RESET}"
echo -e "${C_CYAN}========================================${C_RESET}"
echo -e "  文件:   ${OUTPUT_PATH}"
echo -e "  大小:   ${SIZE_READABLE}"
echo -e "  时间戳: ${TIMESTAMP}"
echo -e "\n${C_YELLOW}  目标机部署步骤:${C_RESET}"
echo -e "  1. tar -xzvf ${PACKAGE_NAME}.tar.gz"
echo -e "  2. cd knowledge_base_deploy_Linux_${TIMESTAMP}"
echo -e "  3. chmod +x deploy.sh && ./deploy.sh --skip-model"
echo -e "  4. 浏览器访问: http://localhost:8000"
echo -e "  5. OCR 状态:  http://localhost:8000/api/ocr/status"
echo -e "  6. 导入进度:  ws://localhost:8000/ws/import-progress"
echo -e ""
