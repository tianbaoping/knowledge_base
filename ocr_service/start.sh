#!/usr/bin/env bash
# =========================================================================
# PaddleOCR 服务启动脚本 (Linux)
# =========================================================================
set -e

cd "$(dirname "$0")/.."

# 配置（可通过环境变量覆盖）
export OCR_HOST="${OCR_HOST:-0.0.0.0}"
export OCR_PORT="${OCR_PORT:-8002}"
# export OCR_USE_GPU=true

echo "========================================"
echo "  PaddleOCR Service Starting..."
echo "========================================"
echo "  Host: $OCR_HOST"
echo "  Port: $OCR_PORT"
echo "  GPU:  ${OCR_USE_GPU:-false}"
echo "========================================"

exec python -m ocr_service.main
