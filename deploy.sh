#!/bin/bash
#========================================
# Knowledge Base System - One-Click Deploy (Linux)
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh                     # 完整部署 + 前台启动
#   ./deploy.sh --skip-model        # 跳过模型检查
#   ./deploy.sh --start-only        # 不重新部署, 直接启动服务
#   ./deploy.sh --recreate-env      # 强制重建 conda 环境
#   ./deploy.sh --port 8001         # 指定端口
#   ./deploy.sh --background        # 后台启动, 日志写到 data/logs/serve.log
#   ./deploy.sh --stop              # 停止后台服务
#   ./deploy.sh --restart           # 重启后台服务
#   ./deploy.sh --status            # 查看服务状态
#
# 功能特性:
#   - OCR 智能识别 (RapidOCR + PP-OCRv4)
#   - 图片和扫描版 PDF 自动 OCR 处理
#   - 实时导入进度 WebSocket 推送
#   - OCR 状态监控面板
#========================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

SKIP_MODEL=false
START_ONLY=false
RECREATE_ENV=false
BACKGROUND=false
DO_STOP=false
DO_RESTART=false
DO_STATUS=false
PORT=8000
ENV_NAME="knowledge_base"
PID_FILE="$PROJECT_DIR/data/logs/service.pid"
LOG_FILE="$PROJECT_DIR/data/logs/serve.log"

usage() {
    head -20 "$0" | tail -17
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-model)    SKIP_MODEL=true; shift ;;
        --start-only)    START_ONLY=true; shift ;;
        --recreate-env)  RECREATE_ENV=true; shift ;;
        --background)    BACKGROUND=true; shift ;;
        --stop)          DO_STOP=true; shift ;;
        --restart)       DO_RESTART=true; shift ;;
        --status)        DO_STATUS=true; shift ;;
        --port)          PORT="${2:-8000}"; shift 2 ;;
        -h|--help)       usage ;;
        *) echo "Unknown arg: $1"; usage ;;
    esac
done

C_GREEN="\033[1;32m" C_RED="\033[1;31m" C_YELLOW="\033[1;33m" C_CYAN="\033[1;36m" C_RESET="\033[0m"

mkdir -p "$PROJECT_DIR/data/uploads" "$PROJECT_DIR/data/logs" "$PROJECT_DIR/data/qdrant"

# ------- 辅助函数 -------
is_running() {
    local pid
    [[ -f "$PID_FILE" ]] && pid=$(cat "$PID_FILE" 2>/dev/null || true) || return 1
    [[ -z "${pid:-}" ]] && return 1
    kill -0 "$pid" 2>/dev/null
}

stop_service() {
    if is_running; then
        local pid
        pid=$(cat "$PID_FILE")
        echo -e "${C_YELLOW}[停止服务]${C_RESET}  PID=$pid"
        kill "$pid" 2>/dev/null || true
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.5
        done
        if kill -0 "$pid" 2>/dev/null; then
            echo "  优雅停止超时, 强制 kill -9"
            kill -9 "$pid" 2>/dev/null || true
            sleep 0.5
        fi
        rm -f "$PID_FILE"
        echo -e "  ${C_GREEN}[OK] 服务已停止${C_RESET}"
    else
        echo "  服务未运行 (PID 文件不存在或进程已退出)"
        rm -f "$PID_FILE"
    fi
}

status_service() {
    if is_running; then
        local pid=$(cat "$PID_FILE")
        echo -e "${C_GREEN}服务正在运行${C_RESET}  PID=$pid, 端口=$PORT"
        echo "  日志: tail -100f $LOG_FILE"
        local url="http://localhost:$PORT"
        echo -e "  Web:  $url"
        echo -e "  OCR:  $url/api/ocr/status"
        if command -v curl >/dev/null 2>&1; then
            local code
            code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$url/" || true)
            echo "  健康检查: HTTP $code"
            # OCR 状态检查
            local ocr_status
            ocr_status=$(curl -s --max-time 3 "$url/api/ocr/status" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['status'])" 2>/dev/null || echo "unknown")
            echo "  OCR 状态: $ocr_status"
        fi
    else
        echo -e "${C_RED}服务未运行${C_RESET}"
    fi
}

# ------- --status / --stop 优先 -------
if [[ "$DO_STATUS" == true ]]; then
    status_service
    exit 0
fi
if [[ "$DO_STOP" == true ]]; then
    stop_service
    exit 0
fi
if [[ "$DO_RESTART" == true ]]; then
    stop_service
    # restart 默认后台启动, 除非再指定别的
    BACKGROUND=true
    START_ONLY=true
fi

echo -e "${C_CYAN}========================================${C_RESET}"
echo -e "${C_CYAN}  Knowledge Base System - Deploy (Linux)${C_RESET}"
echo -e "${C_CYAN}========================================${C_RESET}"

PACKED_ENV_TAR="$PROJECT_DIR/envs/knowledge_base_env.tar.gz"
PACKED_ENV_DIR="$PROJECT_DIR/envs/knowledge_base"
PACKED_PYTHON="$PACKED_ENV_DIR/bin/python"
USE_PACKED_ENV=false

start_service() {
    local python_bin="${1:-python}"
    local title_mode="${2:-conda}"

    echo -e "\n${C_YELLOW}[启动服务]${C_RESET}"
    echo ""
    echo -e "${C_GREEN}  Web UI:  http://localhost:${PORT}${C_RESET}"
    echo -e "${C_GREEN}  API Doc: http://localhost:${PORT}/docs${C_RESET}"
    echo -e "${C_GREEN}  MCP Server: http://localhost:${PORT}/mcp  (MCP 2025-11-25)${C_RESET}"
    echo -e "${C_GREEN}  MCP REST:   http://localhost:${PORT}/api/mcp (兼容)${C_RESET}"
    echo -e "${C_GREEN}  MCP Key: kb-mcp-secret-key-2024${C_RESET}"
    echo -e "${C_GREEN}  OCR Status: http://localhost:${PORT}/api/ocr/status${C_RESET}"
    echo -e "${C_GREEN}  Import WS:  ws://localhost:${PORT}/ws/import-progress${C_RESET}"
    echo -e "  环境:    $title_mode"
    echo -e "  Python:  $( "$python_bin" -c 'import sys; print(sys.executable)' 2>/dev/null || echo $python_bin )"
    echo -e "  日志:    $LOG_FILE"
    echo ""
    if [[ "$BACKGROUND" == true ]]; then
        echo "  后台模式启动中..."
    else
        echo "  按 Ctrl+C 可停止服务"
    fi
    echo "----------------------------------------"

    export HOST="0.0.0.0"
    export PORT

    if [[ "$BACKGROUND" == true ]]; then
        cd "$PROJECT_DIR"
        nohup "$python_bin" -m app.main > "$LOG_FILE" 2>&1 &
        local bg_pid=$!
        echo "$bg_pid" > "$PID_FILE"
        sleep 2
        if kill -0 "$bg_pid" 2>/dev/null; then
            echo -e "${C_GREEN}  [OK] 后台启动成功, PID=$bg_pid${C_RESET}"
            echo -e "  查看状态:  ./deploy.sh --status"
            echo -e "  查看日志:  tail -100f $LOG_FILE"
            echo -e "  停止服务:  ./deploy.sh --stop"
        else
            echo -e "${C_RED}  [X] 启动失败 (PID=$bg_pid 已退出)${C_RESET}"
            echo "  最近日志:"
            tail -30 "$LOG_FILE" 2>/dev/null || true
            rm -f "$PID_FILE"
            exit 1
        fi
    else
        rm -f "$PID_FILE"
        exec "$python_bin" -m app.main
    fi
}

# ================= 0. Start only mode =================
if [[ "$START_ONLY" == true && "$DO_RESTART" != true ]]; then
    if [[ -x "$PACKED_PYTHON" ]]; then
        USE_PACKED_ENV=true
        echo -e "\n${C_YELLOW}[仅启动]${C_RESET} 使用预打包环境: $PACKED_PYTHON"
    else
        echo -e "\n${C_YELLOW}[仅启动]${C_RESET} 使用 conda 环境: $ENV_NAME"
        if command -v conda >/dev/null 2>&1; then
            CONDA_BASE=$(conda info --base 2>/dev/null || true)
            [[ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]] && source "$CONDA_BASE/etc/profile.d/conda.sh"
            conda activate "$ENV_NAME" 2>/dev/null || {
                echo -e "${C_RED}  [X] conda 环境 '$ENV_NAME' 不存在, 请先运行 ./deploy.sh${C_RESET}"
                exit 1
            }
        else
            echo -e "${C_RED}  [X] 没有 conda 也没有预打包环境 envs/knowledge_base${C_RESET}"
            exit 1
        fi
    fi
    start_service "$( [[ $USE_PACKED_ENV == true ]] && echo $PACKED_PYTHON || echo python )" \
                  "$( [[ $USE_PACKED_ENV == true ]] && echo 'Pre-packaged (no conda required)' || echo "conda ($ENV_NAME)" )"
    exit 0
fi

# ================= 1. Check for pre-packaged environment =================
if [[ "$RECREATE_ENV" == false && -f "$PACKED_ENV_TAR" ]]; then
    echo -e "\n${C_YELLOW}[环境检测]${C_RESET} 发现预打包环境: envs/knowledge_base_env.tar.gz"

    if [[ -x "$PACKED_PYTHON" ]]; then
        echo "  [OK] 已经解压过了, 跳过解压"
        USE_PACKED_ENV=true
    else
        echo -e "\n${C_YELLOW}[解压环境]${C_RESET} 首次运行需要解压 (1-3 分钟)"
        mkdir -p "$PACKED_ENV_DIR"
        # conda-pack 生成的 tar.gz 顶层就是 bin/ lib/ 等目录, 直接 -C 到目标目录
        tar -xzf "$PACKED_ENV_TAR" -C "$PACKED_ENV_DIR"

        if [[ -x "$PACKED_PYTHON" ]]; then
            # =========================================================
            # ⚠️ 重要: conda-pack 解压后必须执行 conda-unpack 修正 shebang 路径
            # 否则 numpy / torch / sentence-transformers 可能报错
            # =========================================================
            if [[ -x "$PACKED_ENV_DIR/bin/conda-unpack" ]]; then
                echo "  [*] 执行 conda-unpack 修正环境路径..."
                ( cd "$PACKED_ENV_DIR" && "$PACKED_ENV_DIR/bin/conda-unpack" )
            fi
            echo -e "  ${C_GREEN}[OK] 预打包环境解压完成${C_RESET}"
            USE_PACKED_ENV=true
        else
            echo -e "  ${C_RED}[!] 这个 tar.gz 可能不是 Linux 的预打包环境 (解压后未找到 bin/python)${C_RESET}"
            echo "      回退到传统 conda 安装方式..."
            rm -rf "$PACKED_ENV_DIR"
        fi
    fi

    if [[ "$USE_PACKED_ENV" == true ]]; then
        echo -e "\n${C_YELLOW}[环境校验]${C_RESET}"
        if "$PACKED_PYTHON" -c "import fastapi, uvicorn, qdrant_client, sentence_transformers, loguru, numpy; print('deps-ok')" 2>&1 | grep -q "deps-ok"; then
            echo -e "  ${C_GREEN}[OK] 依赖校验通过${C_RESET}"
        else
            echo -e "  ${C_YELLOW}[!] 部分依赖可能缺失, 后续启动时如有报错请用 --recreate-env 重建${C_RESET}"
        fi
        # OCR 依赖校验
        if "$PACKED_PYTHON" -c "import rapidocr_onnxruntime, onnxruntime, PIL; print('ocr-ok')" 2>&1 | grep -q "ocr-ok"; then
            echo -e "  ${C_GREEN}[OK] OCR 依赖校验通过 (RapidOCR + ONNX Runtime)${C_RESET}"
        else
            echo -e "  ${C_YELLOW}[!] OCR 依赖可能缺失, OCR 功能可能不可用${C_RESET}"
        fi
    fi
fi

# ================= 2. Fallback: Create conda env =================
if [[ "$USE_PACKED_ENV" == false ]]; then
    echo -e "\n${C_YELLOW}[环境检测]${C_RESET} 检查 conda ..."

    if command -v conda >/dev/null 2>&1; then
        CONDA_BASE=$(conda info --base 2>/dev/null || true)
        [[ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]] && source "$CONDA_BASE/etc/profile.d/conda.sh"
        echo "  [OK] conda: $(conda --version)"
    else
        echo -e "  ${C_RED}[X] 未找到 conda, 请先安装 Miniconda:${C_RESET}"
        echo "      wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
        echo "      bash Miniconda3-latest-Linux-x86_64.sh"
        exit 1
    fi

    if [[ "$RECREATE_ENV" == true ]] && conda env list --json 2>/dev/null | grep -q "\"$ENV_NAME\""; then
        echo "  [!] 删除现有 conda 环境: $ENV_NAME"
        conda env remove -n "$ENV_NAME" -y --quiet || true
    fi

    if conda env list --json 2>/dev/null | grep -q "\"$ENV_NAME\""; then
        echo "  [!] conda 环境 '$ENV_NAME' 已存在, 跳过创建"
    else
        echo -e "\n${C_YELLOW}[创建环境]${C_RESET} python=3.12 ..."
        conda create -n "$ENV_NAME" python=3.12 -y --quiet
        echo -e "  ${C_GREEN}[OK] conda 环境创建完成${C_RESET}"
    fi

    conda activate "$ENV_NAME"
    echo "  [OK] 激活环境: $ENV_NAME"

    echo -e "\n${C_YELLOW}[安装依赖]${C_RESET}"
    python -m pip install --upgrade pip --quiet
    set +e
    pip install -r requirements.txt --quiet
    PIP_RC=$?
    set -e
    if [[ $PIP_RC -ne 0 ]]; then
        echo -e "  ${C_YELLOW}[!] 部分依赖安装失败, 重试不使用 --quiet 查看错误${C_RESET}"
        pip install -r requirements.txt || {
            echo -e "  ${C_RED}[X] 依赖安装失败${C_RESET}"
            exit 1
        }
    fi
    echo -e "  ${C_GREEN}[OK] 依赖安装完成${C_RESET}"
fi

# ================= 3. Check model =================
if [[ "$SKIP_MODEL" == false ]]; then
    echo -e "\n${C_YELLOW}[模型检查]${C_RESET}"
    MODEL_DIR="$PROJECT_DIR/models/BAAI_bge-small-zh-v1.5"
    MODEL_FILE="$MODEL_DIR/model.safetensors"

    if [[ -f "$MODEL_FILE" ]]; then
        MODEL_SIZE=$(du -h "$MODEL_FILE" | cut -f1)
        echo "  [OK] 嵌入模型已就绪: $MODEL_SIZE"
    else
        echo "  [!] 嵌入模型不存在, 尝试自动下载..."
        echo "      (下载失败可手动从 https://huggingface.co/BAAI/bge-small-zh-v1.5 下载放到 $MODEL_DIR)"
        RUN_PY="$( [[ $USE_PACKED_ENV == true ]] && echo "$PACKED_PYTHON" || echo python )"
        set +e
        "$RUN_PY" "$PROJECT_DIR/download_model.py"
        dl_rc=$?
        set -e
        if [[ -f "$MODEL_FILE" ]]; then
            echo -e "  ${C_GREEN}[OK] 嵌入模型下载完成${C_RESET}"
        else
            echo -e "  ${C_YELLOW}[!] 嵌入模型下载失败 (rc=$dl_rc), 服务将以演示模式启动 (Mock Embedding)${C_RESET}"
        fi
    fi
else
    echo -e "\n${C_YELLOW}[模型检查]${C_RESET} --skip-model 已跳过"
fi

# ================= 3.5 Check OCR models =================
echo -e "\n${C_YELLOW}[OCR 模型检查]${C_RESET}"
OCR_MODEL_DIR="$PROJECT_DIR/ocr_service/models"
OCR_MODELS=(
    "ch_PP-OCRv4_det_infer.onnx"
    "ch_PP-OCRv4_rec_infer.onnx"
    "ch_ppocr_mobile_v2.0_cls_infer.onnx"
)
OCR_READY=true
OCR_TOTAL_SIZE=0

if [[ ! -d "$OCR_MODEL_DIR" ]]; then
    echo -e "  ${C_RED}[X] OCR 模型目录不存在: $OCR_MODEL_DIR${C_RESET}"
    echo "      OCR 功能将不可用。请确保 ocr_service/models/ 目录包含 3 个 ONNX 模型文件"
    echo "      参考 README.md 中的 OCR 模型部署说明"
    OCR_READY=false
else
    for model_file in "${OCR_MODELS[@]}"; do
        model_path="$OCR_MODEL_DIR/$model_file"
        if [[ -f "$model_path" ]]; then
            model_size=$(du -m "$model_path" 2>/dev/null | cut -f1)
            OCR_TOTAL_SIZE=$((OCR_TOTAL_SIZE + model_size))
            echo -e "  ${C_GREEN}[OK]${C_RESET} $model_file (~${model_size}MB)"
        else
            echo -e "  ${C_RED}[MISS]${C_RESET} $model_file"
            OCR_READY=false
        fi
    done

    if [[ "$OCR_READY" == true ]]; then
        echo -e "  ${C_GREEN}[OK] OCR 模型就绪 (共 3 个文件, ~${OCR_TOTAL_SIZE}MB)${C_RESET}"
        echo "      引擎: RapidOCR + ONNX Runtime"
        echo "      版本: PP-OCRv4 (中文)"
        echo "      支持: jpg/png/bmp/tiff/gif 图片 + 扫描版 PDF"
    else
        echo -e "  ${C_YELLOW}[!] OCR 模型不完整, OCR 功能将不可用${C_RESET}"
        echo "      缺失的模型文件需要手动放置到: $OCR_MODEL_DIR"
        echo "      下载地址: 参考 README.md 或 PaddleOCR 官方仓库"
    fi
fi

# ================= 4. Data dirs =================
echo -e "\n${C_YELLOW}[数据目录]${C_RESET}"
mkdir -p "$PROJECT_DIR/data/uploads" "$PROJECT_DIR/data/logs" "$PROJECT_DIR/data/qdrant" "$PROJECT_DIR/data/ocr_temp"
echo "  [OK] data/{uploads,logs,qdrant,ocr_temp} 就绪"

# ================= 5. Check port =================
echo -e "\n${C_YELLOW}[端口检查]${C_RESET} $PORT"
PORT_PID=""
if command -v ss >/dev/null 2>&1; then
    PORT_PID=$(ss -tlnp 2>/dev/null | awk -v p=":$PORT" '$4 ~ p {split($NF,a,/,|=/); for(i in a) if(a[i]=="pid") print a[i+1]}' | head -1)
elif command -v lsof >/dev/null 2>&1; then
    PORT_PID=$(lsof -t -iTCP:$PORT -sTCP:LISTEN 2>/dev/null | head -1)
fi

if [[ -n "${PORT_PID:-}" ]]; then
    # 如果是我们自己的服务, 在 --restart 场景下已经 kill 过; 否则默认跳过提示
    if [[ "$(cat "$PID_FILE" 2>/dev/null || true)" == "$PORT_PID" ]]; then
        echo "  端口被本服务旧进程占, 已在 restart 流程中清理"
    else
        echo -e "  ${C_YELLOW}[!] 端口 $PORT 已被 PID=$PORT_PID 占用${C_RESET}"
        echo "      可用其它端口:  ./deploy.sh --port 8001"
        echo "      或杀掉占用:    kill -9 $PORT_PID"
    fi
else
    echo "  [OK] 端口 $PORT 可用"
fi

# ================= 6. Start service =================
start_service "$( [[ $USE_PACKED_ENV == true ]] && echo "$PACKED_PYTHON" || echo python )" \
              "$( [[ $USE_PACKED_ENV == true ]] && echo 'Pre-packaged (no conda required)' || echo "conda ($ENV_NAME)" )"
