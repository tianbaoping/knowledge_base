#!/bin/bash
# ============================================================
# Knowledge Base System - systemd 服务安装脚本
# ============================================================
# Usage:
#   chmod +x install-service.sh
#   sudo ./install-service.sh          # 自动检测用户和路径
#   sudo ./install-service.sh --user kb --port 8001
# ============================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 默认参数
TARGET_USER="${SUDO_USER:-$(whoami)}"
TARGET_GROUP="$(id -gn "$TARGET_USER")"
TARGET_PORT="8000"
SKIP_ENV=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user)   TARGET_USER="$2"; shift 2 ;;
        --group)  TARGET_GROUP="$2"; shift 2 ;;
        --port)   TARGET_PORT="$2"; shift 2 ;;
        --skip-env) SKIP_ENV=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--user USER] [--group GROUP] [--port PORT] [--skip-env]"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "========================================"
echo "  Knowledge Base - Service Installer"
echo "========================================"
echo ""
echo "  用户:     $TARGET_USER"
echo "  组:       $TARGET_GROUP"
echo "  端口:     $TARGET_PORT"
echo "  路径:     $PROJECT_DIR"
echo ""

# 检查预打包环境
ENV_PYTHON="$PROJECT_DIR/envs/knowledge_base/bin/python"
if [[ -x "$ENV_PYTHON" && "$SKIP_ENV" == false ]]; then
    echo "  环境:     使用预打包环境"
    echo "  Python:   $ENV_PYTHON"
else
    echo "  环境:     使用系统/conda Python"
    ENV_PYTHON="$(which python3 || echo python3)"
fi

# 创建必要目录
mkdir -p "$PROJECT_DIR/data/logs"
mkdir -p "$PROJECT_DIR/data/uploads"
mkdir -p "$PROJECT_DIR/data/qdrant"

# 设置目录权限
chown -R "$TARGET_USER:$TARGET_GROUP" "$PROJECT_DIR/data" 2>/dev/null || true

# 生成实际的 service 文件
SERVICE_FILE="/etc/systemd/system/knowledge-base.service"

echo "[生成配置] $SERVICE_FILE"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Knowledge Base Management System (AI RAG)
After=network.target network-online.target
Wants=network.target
Requires=network.target

[Service]
Type=simple
User=$TARGET_USER
Group=$TARGET_GROUP
WorkingDirectory=$PROJECT_DIR

# 环境变量
Environment=APP_HOST=0.0.0.0
Environment=APP_PORT=$TARGET_PORT
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=MODEL_LOCAL_PATH=$PROJECT_DIR/models/BAAI_bge-small-zh-v1.5
Environment=MCP_API_KEY=kb-mcp-secret-key-2024

# 启动命令
ExecStart=$ENV_PYTHON -m app.main

# 守护进程 & 异常重启
Restart=always
RestartSec=3
TimeoutStartSec=60
TimeoutStopSec=30
WatchdogSec=300
StartLimitBurst=5
StartLimitIntervalSec=60

# 资源限制
MemoryMax=4G
CPUQuota=400%

# 安全加固
NoNewPrivileges=true
ReadWritePaths=$PROJECT_DIR/data

# 日志配置
StandardOutput=journal
StandardError=journal
SyslogIdentifier=knowledge-base
LogLevelMax=info

[Install]
WantedBy=multi-user.target
Alias=knowledge-base.service
EOF

# 设置权限
chmod 644 "$SERVICE_FILE"

# 重新加载 systemd
echo "[重载配置] systemctl daemon-reload"
systemctl daemon-reload

# 设置开机自启
echo "[启用自启] systemctl enable knowledge-base.service"
systemctl enable knowledge-base.service

echo ""
echo "============================================"
echo "  安装完成！"
echo "============================================"
echo ""
echo "  启动服务:  sudo systemctl start knowledge-base"
echo "  停止服务:  sudo systemctl stop knowledge-base"
echo "  重启服务:  sudo systemctl restart knowledge-base"
echo "  查看状态:  sudo systemctl status knowledge-base"
echo "  查看日志:  sudo journalctl -u knowledge-base -f"
echo "  应用日志:  tail -f $PROJECT_DIR/data/logs/app.log"
echo ""
echo "  Web界面:  http://localhost:$TARGET_PORT"
echo "  API文档:  http://localhost:$TARGET_PORT/docs"
echo "  OCR状态:  http://localhost:$TARGET_PORT/api/ocr/status"
echo ""

# 询问是否立即启动
read -p "是否立即启动服务? [y/N]: " START_NOW
if [[ "${START_NOW,,}" == "y" ]]; then
    echo "[启动] systemctl start knowledge-base"
    systemctl start knowledge-base
    sleep 2
    systemctl status knowledge-base --no-pager || true
fi
