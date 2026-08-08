# 知识库管理系统 - 部署使用教程

## 一、安装包内容

安装包 `knowledge_base_deploy_xxxxxxxx.zip` 已包含以下内容，目标机器**无需联网下载依赖**：

| 内容 | 说明 |
|------|------|
| `app/` | 应用代码 |
| `models/BAAI_bge-small-zh-v1.5/` | 嵌入模型文件 (~100MB) |
| `envs/knowledge_base_env.tar.gz` | 预打包 conda 环境 (~53MB，含全部依赖) |
| `requirements.txt` | 依赖清单（备用，环境打包失败时使用） |
| `deploy.ps1` | Windows 一键部署脚本 |
| `deploy.sh` | Linux 一键部署脚本 |
| `download_model.py` | 模型下载工具 |
| `run_full_test.py` | 全流程测试脚本 |
| `test_api.py` | API 测试脚本 |
| `DEPLOY.md` | 本文档 |

## 二、环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11、Windows Server 2019+、Ubuntu 20.04+ |
| 内存 | 最低 2GB，推荐 4GB+ |
| 磁盘 | 500MB（解压后） |
| 网络 | **不需要**（预打包环境 + 内置模型，开箱即用） |

> **Windows 用户**：安装包内已打包 conda 环境，无需安装 Python 或 conda，解压即用。
> **Linux 用户**：预打包环境为 Windows 版本，Linux 上需安装 Miniconda（见下方说明）。

## 三、Windows 部署（推荐，零依赖）

### 3.1 一键部署

```powershell
# 1. 解压安装包到任意目录（如 D:\knowledge_base）
# 2. 在解压目录右键 → "在终端中打开"（或打开 PowerShell 切换到该目录）
# 3. 执行一键部署
.\deploy.ps1 -SkipModel
```

脚本自动完成：
1. 检测预打包环境 → 解压 `envs/knowledge_base_env.tar.gz`
2. 验证依赖完整性
3. 检查模型文件
4. 检查端口占用
5. 启动服务

启动后显示：
```
  Web UI:  http://localhost:8000
  API Doc: http://localhost:8000/docs
  MCP API: http://localhost:8000/api/mcp
  MCP Key: kb-mcp-secret-key-2024
  Env:     Pre-packaged (no conda required)
```

### 3.2 仅启动服务（已部署过）

```powershell
.\deploy.ps1 -StartOnly
```

### 3.3 强制重建 conda 环境（不用预打包环境）

```powershell
# 需要本机已安装 conda，从 requirements.txt 重新安装依赖
.\deploy.ps1 -RecreateEnv
```

### 3.4 手动部署（不用脚本）

```powershell
# 如果不用预打包环境，需自行安装 Python 3.12+
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

## 四、Linux 部署（Ubuntu）

### 4.1 安装 Miniconda（仅需一次）

```bash
# 下载 Miniconda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

# 安装（按提示操作）
bash Miniconda3-latest-Linux-x86_64.sh

# 重新加载环境变量
source ~/.bashrc
```

### 4.2 一键部署

```bash
# 1. 解压安装包
unzip knowledge_base_deploy_xxxxxxxx.zip -d knowledge_base
cd knowledge_base

# 2. 赋予执行权限
chmod +x deploy.sh

# 3. 一键部署（模型已内置，跳过下载）
./deploy.sh --skip-model
```

脚本自动完成：
1. 检测预打包环境（Windows 版，Linux 不可用 → 自动跳过）
2. 创建 conda 环境 `knowledge_base`（Python 3.12）
3. 从 `requirements.txt` 安装依赖
4. 检查模型文件
5. 启动服务

### 4.3 仅启动服务

```bash
./deploy.sh --start-only
```

### 4.4 强制重建环境

```bash
./deploy.sh --recreate-env --skip-model
```

## 五、部署后验证

### 5.1 基础验证

服务启动后，浏览器访问：

| 地址 | 说明 |
|------|------|
| http://localhost:8000 | Web 管理界面 |
| http://localhost:8000/docs | API 文档 |
| http://localhost:8000/api/mcp/health | MCP 健康检查 |

### 5.2 运行自动化测试

```powershell
# 确保服务已启动，另开终端运行
python run_full_test.py
```

测试覆盖（29项）：健康检查 → 创建知识库 → 上传文件 → 向量入库 → 知识检索 → MCP接口 → 鉴权测试 → 异常容错

### 5.3 手动接口测试

```powershell
# 健康检查
Invoke-RestMethod -Uri "http://localhost:8000/api/health"

# 创建知识库
Invoke-RestMethod -Uri "http://localhost:8000/api/kb" -Method Post `
  -ContentType "application/json" `
  -Body '{"name":"测试库","description":"测试"}'

# MCP 知识检索
Invoke-RestMethod -Uri "http://localhost:8000/api/mcp/search" -Method Post `
  -ContentType "application/json" `
  -Headers @{ "Authorization" = "Bearer kb-mcp-secret-key-2024" } `
  -Body '{"query":"测试问题","kb_name":"测试库","top_k":5}'
```

### 5.4 Python 调用示例

```python
import requests

# 知识检索
resp = requests.post(
    "http://localhost:8000/api/mcp/search",
    headers={"Authorization": "Bearer kb-mcp-secret-key-2024"},
    json={
        "query": "你要问的问题",
        "kb_name": "知识库名称",
        "top_k": 5,
        "score_threshold": 0.3
    }
)
for item in resp.json()["results"]:
    print(f"[{item['score']:.1%}] {item['text'][:100]}")
```

## 六、日常使用

### 6.1 Web 界面操作

1. **创建知识库**：左侧菜单「知识库管理」→ 点击「新建知识库」→ 输入名称 → 点击「确认」
2. **导入文件**：选择知识库 → 点击「导入文件」→ 选择 PDF/Word/TXT/**OFD** 文件
3. **知识检索**：左侧菜单「知识检索」→ 输入问题 → 查看检索结果和检索过程
4. **系统监控**：左侧菜单「系统监控」→ 查看运行状态、资源占用

### 6.2 停止服务

在服务运行终端按 `Ctrl+C` 停止。

## 七、配置说明

修改 `app/config.py` 或通过环境变量调整配置：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `APP_PORT` | 8000 | 服务端口 |
| `EMBEDDING_MODEL` | BAAI/bge-small-zh-v1.5 | 嵌入模型名称 |
| `EMBEDDING_DIM` | 512 | 向量维度 |
| `MODEL_LOCAL_PATH` | models/BAAI_bge-small-zh-v1.5 | 本地模型路径 |
| `MCP_API_KEY` | kb-mcp-secret-key-2024 | MCP 接口密钥 |
| `CHUNK_SIZE` | 500 | 文档切片长度 |
| `CHUNK_OVERLAP` | 50 | 切片重叠字符数 |
| `MAX_FILE_SIZE` | 104857600 | 单文件最大 100MB |

## 八、打包安装包

在已部署的开发机上打包，分发给其他机器：

```powershell
# 完整打包（含模型 + conda环境，约110MB，目标机器零依赖）
.\pack.ps1

# 不含模型打包（约55MB，目标机器需自行下载模型）
.\pack.ps1 -NoModel

# 不含 conda 环境打包（约100MB，目标机器需自行安装依赖）
.\pack.ps1 -NoEnv

# 最小打包（不含模型和环境，约5MB）
.\pack.ps1 -NoModel -NoEnv
```

> **注意**：预打包的 conda 环境是平台相关的。Windows 上打包的环境只能用于 Windows 目标机器。
> Linux 目标机器需通过 `deploy.sh` 从 `requirements.txt` 创建环境。

## 九、常见问题

### Q: 启动时端口被占用？

**Windows:**
```powershell
# 查看并终止占用 8000 端口的进程
$pid = (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess
Stop-Process -Id $pid -Force
```

**Linux:**
```bash
# 查看占用端口的进程
ss -tlnp | grep :8000
# 终止进程
kill -9 <PID>
```

### Q: 模型加载失败？
- 检查 `models/BAAI_bge-small-zh-v1.5/` 目录下是否有 `model.safetensors`
- 运行 `python download_model.py` 重新下载
- 无模型时系统以演示模式运行（检索精度有限）

### Q: 预打包环境解压失败？
```powershell
# 手动解压 conda 环境
mkdir envs\knowledge_base
tar -xzf envs\knowledge_base_env.tar.gz -C envs\knowledge_base

# 验证
.\envs\knowledge_base\python.exe -c "import fastapi; print('OK')"

# 使用预打包环境启动
.\envs\knowledge_base\python.exe -m app.main
```

### Q: Linux 上提示 conda not found？
```bash
# 安装 Miniconda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
source ~/.bashrc

# 然后重新运行
./deploy.sh --skip-model
```

### Q: 依赖安装失败（Linux）？
```bash
# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q: Qdrant 数据库锁冲突？

**Windows:**
```powershell
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -Path "data\qdrant\.lock" -Force -ErrorAction SilentlyContinue
```

**Linux:**
```bash
pkill -f "python.*app.main"
rm -f data/qdrant/.lock
```

### Q: 如何迁移到其他机器？
1. 打包：`.\pack.ps1`
2. 拷贝 `data/` 目录到新机器（包含知识库数据）
3. 解压安装包，运行部署脚本
4. 将 `data/` 目录覆盖到新部署目录

## 十、目录结构

```
knowledge_base/
├── app/                        # 应用代码
│   ├── main.py                 # 入口
│   ├── config.py               # 配置
│   ├── routers/                # API 路由
│   ├── services/               # 业务服务
│   ├── database/               # 数据库
│   ├── models/                 # 数据模型
│   └── static/                 # Web 界面
├── ocr_service/                # OCR 服务模块
├── ofd_service/                # OFD 版式文档解析模块
├── models/                     # 嵌入模型文件
│   └── BAAI_bge-small-zh-v1.5/
├── envs/                       # 预打包 conda 环境
│   ├── knowledge_base_env.tar.gz  # 环境压缩包
│   └── knowledge_base/         # 解压后的环境（首次运行自动生成）
├── data/                       # 运行数据（自动生成）
│   ├── uploads/                # 上传文件
│   ├── qdrant/                 # 向量数据库
│   ├── logs/                   # 日志
│   └── metadata.db             # 元数据
├── deploy.ps1                  # Windows 部署脚本
├── deploy.sh                   # Linux 部署脚本
├── pack.ps1                    # 打包脚本
├── download_model.py           # 模型下载工具
├── run_full_test.py            # 全流程测试脚本
├── requirements.txt            # Python 依赖
└── DEPLOY.md                   # 本文档
```
