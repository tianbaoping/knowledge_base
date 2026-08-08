#!/bin/bash
# ============================================================
# Knowledge Base System - 生产环境一键部署脚本
# ============================================================
# 功能:
#   1. 解压预打包 conda 环境
#   2. 生成并安装 systemd 服务 (异常重启 + 守护进程 + 开机自启)
#   3. 配置 journald 日志限额
#   4. 配置应用日志 logrotate 轮转
#   5. 设置日志清理定时任务
#
# Usage:
#   chmod +x deploy-prod.sh
#   sudo ./deploy-prod.sh                    # 全自动部署
#   sudo ./deploy-prod.sh --skip-env         # 跳过环境解压
#   sudo ./deploy-prod.sh --skip-logs        # 跳过日志配置
#   sudo ./deploy-prod.sh --port 8001        # 指定端口
# ============================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 默认参数
TARGET_USER="${SUDO_USER:-$(whoami)}"
TARGET_GROUP="$(id -gn "$TARGET_USER")"
TARGET_PORT="8000"
SKIP_ENV=false
SKIP_LOGS=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user)      TARGET_USER="$2"; shift 2 ;;
        --group)     TARGET_GROUP="$2"; shift 2 ;;
        --port)      TARGET_PORT="$2"; shift 2 ;;
        --skip-env)  SKIP_ENV=true; shift ;;
        --skip-logs) SKIP_LOGS=true; shift ;;
        -h|--help)
            head -20 "$0" | tail -18
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# 颜色
C_GREEN='\033[1;32m'
C_RED='\033[1;31m'
C_YELLOW='\033[1;33m'
C_CYAN='\033[1;36m'
C_RESET='\033[0m'

echo -e "${C_CYAN}"
echo "================================================"
echo "  Knowledge Base System - 生产环境部署"
echo "================================================"
echo -e "${C_RESET}"

# 检查 root 权限
if [[ $EUID -ne 0 ]]; then
    echo -e "${C_RED}错误: 请使用 sudo 运行此脚本${C_RESET}"
    exit 1
fi

echo "  用户:     $TARGET_USER"
echo "  组:       $TARGET_GROUP"
echo "  端口:     $TARGET_PORT"
echo "  路径:     $PROJECT_DIR"
echo ""

# ========================================
# Step 1: 解压预打包环境
# ========================================
if [[ "$SKIP_ENV" == false ]]; then
    echo -e "${C_YELLOW}[Step 1] 检查/解压预打包环境${C_RESET}"

    ENV_TAR="$PROJECT_DIR/envs/knowledge_base_env.tar.gz"
    ENV_DIR="$PROJECT_DIR/envs/knowledge_base"

    if [[ -x "$ENV_DIR/bin/python" ]]; then
        echo "  [OK] 环境已存在: $ENV_DIR"
    elif [[ -f "$ENV_TAR" ]]; then
        echo "  [解压] $ENV_TAR -> $ENV_DIR"
        mkdir -p "$ENV_DIR"
        tar -xzf "$ENV_TAR" -C "$ENV_DIR"

        # 执行 conda-unpack 修正路径
        if [[ -x "$ENV_DIR/bin/conda-unpack" ]]; then
            echo "  [修正] conda-unpack"
            (cd "$ENV_DIR" && "$ENV_DIR/bin/conda-unpack")
        fi

        echo "  [OK] 环境解压完成"
    else
        echo "  [WARN] 未找到预打包环境，将使用系统 Python"
        ENV_PYTHON="$(which python3 || echo '/usr/bin/python3')"
    fi
else
    echo -e "${C_YELLOW}[Step 1] 跳过环境解压 (--skip-env)${C_RESET}"
fi

# 确定 Python 路径
ENV_DIR="$PROJECT_DIR/envs/knowledge_base"
if [[ -x "$ENV_DIR/bin/python" ]]; then
    ENV_PYTHON="$ENV_DIR/bin/python"
else
    ENV_PYTHON="$(which python3)"
fi
echo "  Python: $ENV_PYTHON"

# ========================================
# Step 2: 创建必要目录
# ========================================
echo -e "\n${C_YELLOW}[Step 2] 创建目录结构${C_RESET}"
mkdir -p "$PROJECT_DIR/data/logs"
mkdir -p "$PROJECT_DIR/data/uploads"
mkdir -p "$PROJECT_DIR/data/qdrant"
mkdir -p "$PROJECT_DIR/data/ocr_temp"
mkdir -p "$PROJECT_DIR/scripts"
chown -R "$TARGET_USER:$TARGET_GROUP" "$PROJECT_DIR/data" 2>/dev/null || true
echo "  [OK] data/{logs,uploads,qdrant,ocr_temp}"

# ========================================
# Step 3: 生成并安装 systemd 服务
# ========================================
echo -e "\n${C_YELLOW}[Step 3] 配置 systemd 服务${C_RESET}"

SERVICE_FILE="/etc/systemd/system/knowledge-base.service"

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

# ============ 环境变量 ============
Environment=APP_HOST=0.0.0.0
Environment=APP_PORT=$TARGET_PORT
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=MODEL_LOCAL_PATH=$PROJECT_DIR/models/BAAI_bge-small-zh-v1.5
Environment=MCP_API_KEY=kb-mcp-secret-key-2024

# ============ 启动命令 ============
ExecStart=$ENV_PYTHON -m app.main

# ============ 守护进程 & 异常重启 ============
# 异常退出时自动重启
Restart=always
# 重试间隔
RestartSec=3
# 启动超时
TimeoutStartSec=60
# 停止超时
TimeoutStopSec=30
# 看门狗: 进程卡死超时 (5分钟)
WatchdogSec=300
# 60秒内重启超过5次则放弃
StartLimitBurst=5
StartLimitIntervalSec=60

# ============ 资源限制 ============
MemoryMax=4G
CPUQuota=400%

# ============ 安全加固 ============
NoNewPrivileges=true
ReadWritePaths=$PROJECT_DIR/data

# ============ 双日志系统 ============
# 输出到 systemd journal
StandardOutput=journal
StandardError=journal
SyslogIdentifier=knowledge-base
LogLevelMax=info

[Install]
WantedBy=multi-user.target
Alias=knowledge-base.service
EOF

chmod 644 "$SERVICE_FILE"

# 重新加载 systemd
systemctl daemon-reload
systemctl enable knowledge-base.service

echo "  [OK] systemd 服务已配置"
echo "  [OK] 开机自启已启用"

# ========================================
# Step 4: 配置日志系统
# ========================================
if [[ "$SKIP_LOGS" == false ]]; then
    echo -e "\n${C_YELLOW}[Step 4] 配置日志系统${C_RESET}"

    # 4a. 配置 journald 限额
    echo "  [配置] /etc/systemd/journald.conf"
    JOURNALD_CONF="/etc/systemd/journald.conf"

    # 备份原配置
    if [[ -f "$JOURNALD_CONF" && ! -f "${JOURNALD_CONF}.bak.kb" ]]; then
        cp "$JOURNALD_CONF" "${JOURNALD_CONF}.bak.kb"
    fi

    # 设置 journald 限额
    if [[ -f "$JOURNALD_CONF" ]]; then
        # 移除旧配置
        sed -i '/^SystemMaxUse=/d' "$JOURNALD_CONF"
        sed -i '/^SystemKeepFree=/d' "$JOURNALD_CONF"
        sed -i '/^MaxRetentionSec=/d' "$JOURNALD_CONF"
        sed -i '/^MaxLevelStore=/d' "$JOURNALD_CONF"
        sed -i '/^MaxLevelPush=/d' "$JOURNALD_CONF"
        # 添加新配置
        cat >> "$JOURNALD_CONF" << 'JEOF'

# === Knowledge Base 日志限额配置 ===
SystemMaxUse=500M
SystemKeepFree=1G
MaxRetentionSec=1month
MaxLevelStore=info
MaxLevelPush=info
JEOF
    fi

    # 4b. 配置 logrotate (应用日志轮转)
    echo "  [配置] /etc/logrotate.d/knowledge-base"
    LOGROTATE_CONF="/etc/logrotate.d/knowledge-base"

    cat > "$LOGROTATE_CONF" << EOF
# Knowledge Base 应用日志轮转
$PROJECT_DIR/data/logs/*.log {
    size 100M
    rotate 10
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}

# OCR 服务日志
$PROJECT_DIR/ocr_service/data/logs/*.log {
    size 50M
    rotate 5
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF

    chmod 644 "$LOGROTATE_CONF"

    # 4c. 设置日志清理定时任务 (每天凌晨3点执行)
    echo "  [配置] 日志清理定时任务"
    CRON_FILE="/etc/cron.d/knowledge-base-log-cleanup"

    cat > "$CRON_FILE" << EOF
# Knowledge Base 日志自动清理
# 每天凌晨 3:00 检查并清理超出配额的日志
0 3 * * * $TARGET_USER $ENV_PYTHON $PROJECT_DIR/scripts/clean_logs.py --clean >> $PROJECT_DIR/data/logs/cleanup.log 2>&1
EOF

    chmod 644 "$CRON_FILE"

    # 重启 journald
    systemctl restart systemd-journald 2>/dev/null || true

    echo "  [OK] journald 限额: 500MB, 保留1个月"
    echo "  [OK] logrotate: 单文件100MB, 保留10个备份"
    echo "  [OK] 定时任务: 每天 3:00 自动清理"
else
    echo -e "\n${C_YELLOW}[Step 4] 跳过日志配置 (--skip-logs)${C_RESET}"
fi

# ========================================
# 完成
# ========================================
echo -e "\n${C_GREEN}"
echo "================================================"
echo "  🎉 部署完成！"
echo "================================================"
echo -e "${C_RESET}"

cat << EOF

  🔵 启动/停止服务
  ─────────────────────────────────────
  启动:   systemctl start knowledge-base
  停止:   systemctl stop knowledge-base
  重启:   systemctl restart knowledge-base
  状态:   systemctl status knowledge-base

  🔵 查看日志
  ─────────────────────────────────────
  Journal:  journalctl -u knowledge-base -f
  应用日志: tail -f $PROJECT_DIR/data/logs/app.log
  错误日志: tail -f $PROJECT_DIR/data/logs/error.log
  清理日志: python $PROJECT_DIR/scripts/clean_logs.py

  🔵 访问地址
  ─────────────────────────────────────
  Web界面:  http://localhost:$TARGET_PORT
  API文档:  http://localhost:$TARGET_PORT/docs
  OCR状态:  http://localhost:$TARGET_PORT/api/ocr/status

  🔵 日志管理
  ─────────────────────────────────────
  Journal限额: 500MB (配置在 journald.conf)
  应用日志:   单文件100MB, 保留10天, 自动压缩
  定时清理:   每天 3:00 检查, 超出配额自动清理

  🔵 其他命令
  ─────────────────────────────────────
  预览清理:   python scripts/clean_logs.py --clean --dry-run
  指定配额:   python scripts/clean_logs.py --clean --size 1G
  压缩旧日志: python scripts/clean_logs.py --compress

EOF

# 询问是否立即启动
read -p "是否立即启动服务? [y/N]: " START_NOW
if [[ "${START_NOW,,}" == "y" ]]; then
    echo -e "\n${C_YELLOW}[启动] systemctl start knowledge-base${C_RESET}"
    systemctl start knowledge-base
    sleep 3
    echo -e "\n${C_GREEN}[状态]${C_RESET}"
    systemctl status knowledge-base --no-pager || true
fi
