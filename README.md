# 知识库管理系统 (Knowledge Base Management System)

基于 Qdrant 单机高性能向量数据库搭建的轻量化、可落地、可扩展的私有化知识库服务。聚焦文档全内容解析（含文本、图表）、可视化全流程管控、标准化 MCP 协议对外服务能力。

## 目录

- [项目概述](#项目概述)
- [技术架构](#技术架构)
- [目录结构](#目录结构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [API 文档](#api-文档)
- [MCP 协议服务](#mcp-协议服务)
- [API 接口访问知识库完整案例](#api-接口访问知识库完整案例)
- [Web 管理界面](#web-管理界面)
- [部署指南](#部署指南)
- [常见问题](#常见问题)

---

## 项目概述

本系统核心实现以下能力：

- **智能文件导入**：支持单文件、批量文件夹、ZIP 压缩包三种导入模式
- **图文一体化解析**：PDF/Word/OFD 文档全内容解析，不仅提取文本，还识别解析图表、表格信息
- **OFD 版式文档解析**：支持 OFD（GB/T 33190 国标版式文档）直接解析，适用于电子发票、政务公文等场景
- **OCR 智能识别**：图片文件和扫描版 PDF 自动触发 OCR 识别（基于 RapidOCR + PP-OCRv4），支持 jpg/png/bmp/tiff/gif 等格式
- **文件合规校验**：自动校验文件格式、大小、完整性、加密状态，损坏/加密/空文件自动跳过
- **智能去重**：基于文件名和 MD5 自动去重，支持跳过/覆盖策略
- **实时进度推送**：导入过程通过 WebSocket 实时推送解析进度，显示各文件的解析阶段（检测→提取→OCR→完成）
- **可视化管理**：Web 管理界面支持知识库预览、文档明细、切片预览、导入任务看板、OCR 状态面板
- **标准化 MCP 协议**：对外提供符合 MCP 规范的 API 接口，支持鉴权、检索、详情查询
- **全维度监控**：系统状态、资源监控、业务监控、异常日志一站式查看

### OCR 能力说明

系统集成了基于 RapidOCR（ONNX Runtime 实现）的 OCR 引擎，具备以下特性：

- **自动检测**：导入文件时自动检测是否为图片或扫描版 PDF（文本含量 < 50 字符），自动触发 OCR
- **统一管道**：解析管道分为 detect → extract → ocr → chunk → complete 五个阶段，进度全链路追踪
- **实时监控**：OCR 状态面板显示引擎就绪状态、模型信息、资源占用、请求统计
- **进度推送**：通过 WebSocket 实时推送每个文件的解析进度，标记是否需要 OCR 处理
- **性能优化**：OCR 引擎单例模式，模型预加载，平均处理时间可通过监控面板查看

---

## 技术架构

### 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (HTML/JS/CSS)                     │
│              Web 可视化管理界面 (端口 8000)               │
└──────────────────────────┬──────────────────────────────┘
              │ HTTP REST API / WebSocket
              ▼
┌─────────────────────────────────────────────────────────┐
│                    FastAPI 后端服务                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ 知识库路由 │ │ 导入路由  │ │ MCP路由  │ │ 监控路由   │  │
│  └─────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬─────┘  │
│  ┌─────┴─────────────┴──────────┴──────────────┴─────┐  │
│  │  OCR路由 (状态/模型/健康)    │  WebSocket路由(进度)  │  │
│  └────────────────────┬──────────────────────────────┘  │
│                       │                                  │
│  ┌────────────────────┴──────────────────────────────┐  │
│  │                    服务层 (Services)                 │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │  │ 导入服务  │ │ 解析服务  │ │ 嵌入服务  │ │ OCR服务  │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │  │ Qdrant服务│ │  MCP服务  │ │ 进度管理  │             │
│  │  └──────────┘ └──────────┘ └──────────┘             │
│  └─────────────────────┬───────────────────────────────┘  │
│                        │                                   │
│  ┌────────────────────┴───────────────────────────────┐  │
│  │                    OCR 引擎层                          │  │
│  │  ┌─────────────────────────────────────────────────┐ │  │
│  │  │  RapidOCR (ONNX Runtime) - PP-OCRv4 中文模型     │ │  │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │ │  │
│  │  │  │ 文字检测  │  │ 文字识别  │  │ 方向分类器    │   │ │  │
│  │  │  │  (det)   │  │  (rec)   │  │  (cls)       │   │ │  │
│  │  │  └──────────┘  └──────────┘  └──────────────┘   │ │  │
│  │  └─────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────┘  │
│                        │                                   │
│  ┌────────────────────┴───────────────────────────────┐  │
│  │                  数据存储层                           │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │  │
│  │  │  SQLite      │  │  Qdrant      │  │  文件存储    │  │  │
│  │  │  (元数据)    │  │  (向量存储)   │  │  (源文件)    │  │  │
│  │  └──────────────┘  └──────────────┘  └─────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 文档解析管道

```
文件上传 → 格式检测 → MD5 去重 → 解析管道处理
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
              ┌─────┴─────┐        ┌─────┴─────┐        ┌─────┴─────┐
              │  文本类    │        │  PDF/OFD  │        │  图片类    │
              │ (txt, md) │        │           │        │           │
              └─────┬─────┘        └─────┬─────┘        └─────┬─────┘
                    │                     │                     │
              直接文本提取          ┌──────┴──────┐       OCR 识别
              (extract)            │  文本PDF    │扫描版PDF  │  (RapidOCR)
                                   │  (直接解析) │  (OCR)    │
                                   └──────┬──────┘           │
                                          │                     │
              ┌──────────────────────────┤                     │
              │                     ┌─────┴─────┐              │
              │                     │  OFD 文档  │              │
              │                     │ (直接解析) │              │
              │                     └─────┬─────┘              │
              └──────────────────────────┤                     │
                                         │                     │
                                         └────────┬────────────┘
                                                  │
                                             文本切片 (chunk)
                                                  │
                                             向量嵌入 (embed)
                                                  │
                                             Qdrant 入库
```

### 核心流程

```
文件上传 → 格式校验 → MD5 去重 → 文档解析 → 文本切片 → 向量嵌入 → Qdrant 入库
                                                                          ↓
                                                                    绑定元数据
                                                                    (文件名/ID/
                                                                     切片索引/
                                                                     创建时间)

OCR 触发条件:
  - 图片文件 (jpg, png, bmp, tiff, gif) → 自动 OCR
  - PDF 文件文本含量 < 50 字符 → 自动 OCR (扫描版检测)
  - OFD 文档 → 直接解析 (easyofd)，无需 OCR
```

### 向量检索流程

```
用户查询 → 查询向量化 → Qdrant 余弦相似度检索 → 返回 Top-K 结果 → 原文溯源
```

### 导入进度推送流程

```
客户端 WebSocket 连接 → 上传文件 → 创建导入任务 → 实时进度推送
                                                              │
                                                    ┌─────────┴─────────┐
                                                    │  文件级进度:       │
                                                    │  [detect] 检测类型 │
                                                    │  [extract] 提取文本 │
                                                    │  [ocr] OCR识别(如需) │
                                                    │  [complete] 完成   │
                                                    └─────────┬─────────┘
                                                              │
                                                    任务级进度汇总
                                                    (总计/已处理/成功/失败)
```

---

## 目录结构

```
knowledge_base/
├── app/                          # 应用主目录
│   ├── __init__.py
│   ├── config.py                 # 全局配置
│   ├── main.py                   # 应用入口 (FastAPI)
│   ├── database/                 # 数据库层
│   │   ├── __init__.py
│   │   └── sqlite_db.py          # SQLite 管理器
│   ├── models/                   # 数据模型
│   │   ├── __init__.py
│   │   └── schemas.py            # Pydantic 请求/响应模型
│   ├── routers/                  # API 路由层
│   │   ├── __init__.py
│   │   ├── kb_router.py          # 知识库管理路由
│   │   ├── import_router.py      # 文件导入路由
│   │   ├── mcp_router.py         # MCP 协议路由
│   │   ├── monitor_router.py     # 系统监控路由
│   │   ├── ocr_router.py         # OCR 服务监控路由
│   │   └── ws_router.py          # WebSocket 进度推送路由
│   ├── services/                 # 业务服务层
│   │   ├── __init__.py
│   │   ├── parser_service.py     # 文档解析服务 (PDF/Word/TXT/MD/图片)
│   │   ├── import_service.py     # 文件导入服务
│   │   ├── embedding_service.py  # 向量嵌入服务
│   │   ├── reranker_service.py   # Reranker 重排服务 (CrossEncoder)
│   │   ├── qdrant_service.py     # Qdrant 向量库服务
│   │   ├── mcp_service.py        # MCP 协议服务
│   │   ├── monitor_service.py    # 系统监控服务
│   │   ├── ocr_service.py        # OCR 状态监控服务
│   │   └── import_task_manager.py # 导入任务管理器 (进度追踪)
│   └── static/                   # 前端静态文件
│       ├── index.html            # 主页面
│       ├── css/style.css         # 样式
│       └── js/
│           ├── app.js            # 交互逻辑
│           └── ocr-panel.js     # OCR 状态面板
├── ocr_service/                  # OCR 服务模块
│   ├── __init__.py
│   ├── config.py                 # OCR 配置 (模型路径/端口)
│   ├── ocr_engine.py             # OCR 引擎封装 (RapidOCR)
│   ├── recognize.py              # OCR 识别接口
│   ├── pdf_ocr.py                # PDF OCR 处理
│   ├── image_preprocessor.py     # 图片预处理
│   └── models/                   # OCR 模型文件 (PP-OCRv4)
│       ├── ch_PP-OCRv4_det_infer.onnx
│       ├── ch_PP-OCRv4_rec_infer.onnx
│       └── ch_ppocr_mobile_v2.0_cls_infer.onnx
├── ofd_service/                  # OFD 版式文档解析模块
│   ├── __init__.py               # 导出 OFDParser, OFDParseResult
│   ├── README.md                 # OFD 服务说明
│   ├── ofd_parser.py             # OFD 核心解析器 (文本/图片/PDF转换)
│   ├── main.py                   # OFD API 服务入口
│   ├── requirements.txt          # OFD 依赖 (easyofd, xmltodict)
│   └── sample_rich.ofd           # OFD 测试样例
├── data/                         # 数据目录 (运行时生成)
│   ├── qdrant/                   # Qdrant 向量数据
│   ├── uploads/                  # 上传文件存储
│   ├── logs/                     # 日志
│   ├── ocr_temp/                 # OCR 临时文件
│   └── metadata.db               # SQLite 元数据库
├── models/                       # 模型文件
│   ├── BAAI_bge-small-zh-v1.5/   # 本地嵌入模型
│   └── BAAI_bge-reranker-base/   # 本地Reranker重排模型
├── Dockerfile                    # Docker 构建文件
├── docker-compose.yml            # Docker Compose 编排
├── requirements.txt              # Python 依赖
├── run.bat                       # Windows 一键启动脚本
├── download_model.py             # 模型下载工具
├── pack.ps1                      # Windows 打包脚本
├── pack.sh                       # Linux 打包脚本
├── deploy.ps1                    # Windows 部署脚本
├── deploy.sh                     # Linux 部署脚本
└── README.md                     # 本文档
```

---

## 技术栈

| 类别 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 语言 | Python | 3.11+ | 主开发语言 |
| Web 框架 | FastAPI | 0.115.0 | 异步高性能 Web 框架 |
| ASGI 服务器 | Uvicorn | 0.30.6 | FastAPI 推荐服务器 |
| 向量数据库 | Qdrant | 1.11.0 | 单机/分布式向量数据库 |
| 元数据库 | SQLite | 3.x | 轻量级关系型数据库 |
| 文档解析 | PyMuPDF | 1.24.10 | PDF 解析 |
| 文档解析 | python-docx | 1.1.2 | Word 文档解析 |
| **OFD 解析** | **easyofd** | **20260427** | **OFD 版式文档解析 (GB/T 33190)** |
| **OFD 依赖** | **xmltodict** | **0.13.0+** | **OFD XML 解析支持** |
| **OCR 引擎** | **RapidOCR** | **1.3.0+** | **基于 PaddleOCR 的 ONNX Runtime 实现** |
| **OCR 推理** | **ONNX Runtime** | **1.16.0+** | **高性能神经网络推理** |
| **OCR 模型** | **PP-OCRv4** | **-** | **中文 OCR 模型 (检测+识别+分类)** |
| 图片处理 | Pillow | 10.0+ | 图片预处理 |
| 嵌入模型 | sentence-transformers | 3.0.1 | BAAI/bge-small-zh-v1.5 |
| 数据校验 | Pydantic | 2.9.2 | 请求/响应模型 |
| 日志 | loguru | 0.7.2 | 结构化日志 |
| 资源监控 | psutil | 5.9.8 | 系统资源监控 |
| 实时通信 | WebSocket | - | 导入进度实时推送 |
| 前端 | HTML/CSS/JS | - | 原生实现，无需构建 |
| 容器化 | Docker | - | 容器化部署 |

---

## 快速开始

### 环境要求

- Python 3.11+
- pip 包管理器
- （可选）Docker 20+ / Docker Compose 2+
- OCR 模型文件（已预置在 `ocr_service/models/` 目录）

### OCR 模型预置说明

项目已预置 **PP-OCRv4 中文 OCR 模型**，位于 `ocr_service/models/` 目录：

```
ocr_service/models/
├── ch_PP-OCRv4_det_infer.onnx      # 文字检测模型 (4.5MB)
├── ch_PP-OCRv4_rec_infer.onnx      # 文字识别模型 (10.4MB)
└── ch_ppocr_mobile_v2.0_cls_infer.onnx  # 方向分类器 (0.6MB)
```

如需更换模型或使用自定义模型，可通过环境变量指定路径：
```bash
export OCR_DET_MODEL_PATH=/path/to/det.onnx
export OCR_REC_MODEL_PATH=/path/to/rec.onnx
export OCR_CLS_MODEL_PATH=/path/to/cls.onnx
```

### 方式一：本地启动 (推荐)

**1. 克隆项目**

```bash
cd knowledge_base
```

**2. 创建虚拟环境并安装依赖**

```bash
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. 启动服务**

```bash
# 方式A：直接运行
python -m app.main

# 方式B：使用 uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Windows 也可直接双击 run.bat
```

**4. 验证服务**

```bash
# 健康检查
curl http://localhost:8000/api/health

# 检查 OCR 状态
curl http://localhost:8000/api/ocr/status
```

返回：
```json
// 健康检查
{"status":"healthy","app":"知识库管理系统","version":"1.0.0"}

// OCR 状态
{
  "code": 200,
  "data": {
    "status": "running",
    "engine_ready": true,
    "model_info": {
      "model_version": "PP-OCRv4",
      "model_files_ready": true
    }
  }
}
```

**5. 访问界面**

- Web 管理界面: http://localhost:8000
- API 文档 (Swagger): http://localhost:8000/docs
- MCP 服务端点: http://localhost:8000/api/mcp
- **OCR 状态面板**: http://localhost:8000 (管理界面内)

### 方式二：Docker 部署

**1. 一键启动**

```bash
docker-compose up -d
```

**2. 查看日志**

```bash
docker-compose logs -f
```

**3. 停止服务**

```bash
docker-compose down
```

### 首次启动流程

```
[1/4] 初始化 SQLite 元数据库...  ✓
[2/4] 连接 Qdrant 向量数据库...  ✓ (本地模式 / 远程模式)
[3/4] 后台加载嵌入模型...        ✓ (联网自动加载 / 离线切换演示模式)
[4/4] 后台加载 OCR 引擎...      ✓ (PP-OCRv4 模型预加载)

知识库管理系统启动完成!
  Web 界面:  http://0.0.0.0:8000
  API 文档:  http://0.0.0.0:8000/docs
  MCP 服务:  http://0.0.0.0:8000/api/mcp
  MCP 鉴权:  API Key = kb-mcp-secret-key-2024
  OCR 状态:  http://0.0.0.0:8000/api/ocr/status
  导入进度:  ws://0.0.0.0:8000/ws/import-progress
```

> **OCR 启动说明**：OCR 引擎在后台预加载，不阻塞主服务启动。首次调用 OCR 识别时会使用预加载的模型，响应速度更快。
> 
> **演示模式说明**：首次启动若无法联网下载嵌入模型 `BAAI/bge-small-zh-v1.5`，系统将自动切换为演示模式。演示模式使用 SHA-256 哈希生成向量，功能完全可用但语义检索精度有限。OCR 功能不受影响。
> 
> **生产环境建议**：通过 `download_model.py` 预下载嵌入模型到本地，再设置 `MODEL_LOCAL_PATH` 环境变量离线加载，详见下方 [模型离线下载与加载](#模型离线下载与加载) 章节。OCR 模型已预置，无需额外下载。

---

## 配置说明

### 环境变量配置

所有配置位于 `app/config.py`，支持通过环境变量覆盖：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_HOST` | `0.0.0.0` | 服务监听地址 |
| `APP_PORT` | `8000` | 服务监听端口 |
| `APP_VERSION` | `1.0.0` | 应用版本号 |
| `QDRANT_LOCATION` | `data/qdrant` | Qdrant 本地存储路径 |
| `QDRANT_HOST` | `localhost` | Qdrant 远程地址 |
| `QDRANT_PORT` | `6333` | Qdrant 远程端口 |
| `EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 嵌入模型名称 |
| `EMBEDDING_DIM` | `512` | 嵌入向量维度 |
| `MODEL_LOCAL_PATH` | `""` | 本地模型路径 (设置后优先离线加载) |
| `CHUNK_SIZE` | `500` | 文档切片长度 (字符) |
| `CHUNK_OVERLAP` | `50` | 切片重叠长度 (字符) |
| `MAX_FILE_SIZE` | `104857600` | 单文件最大 (100MB) |
| `MCP_API_KEY` | `kb-mcp-secret-key-2024` | MCP 接口密钥 |

### OCR 配置

OCR 相关配置位于 `ocr_service/config.py`：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OCR_HOST` | `0.0.0.0` | OCR 服务地址 (in-process 模式下不使用) |
| `OCR_PORT` | `8002` | OCR 服务端口 (in-process 模式下不使用) |
| `OCR_DET_MODEL_PATH` | `ocr_service/models/ch_PP-OCRv4_det_infer.onnx` | 文字检测模型路径 |
| `OCR_REC_MODEL_PATH` | `ocr_service/models/ch_PP-OCRv4_rec_infer.onnx` | 文字识别模型路径 |
| `OCR_CLS_MODEL_PATH` | `ocr_service/models/ch_ppocr_mobile_v2.0_cls_infer.onnx` | 方向分类器路径 |
| `MAX_IMAGE_SIZE` | `20MB` | 单图片最大尺寸 |
| `MAX_PDF_SIZE` | `50MB` | 单 PDF 最大尺寸 |
| `MAX_PDF_PAGES` | `50` | PDF OCR 最大页数 |

### 配置示例

```bash
# Windows PowerShell
$env:APP_PORT = "9000"
$env:MCP_API_KEY = "your-secure-key"
python -m app.main

# Linux/macOS
export APP_PORT=9000
export MCP_API_KEY=your-secure-key
python -m app.main
```

### OCR 模型自定义

如需使用其他 OCR 模型（如英文模型、手写识别等），可通过环境变量指定：

```bash
# 使用自定义模型路径
export OCR_DET_MODEL_PATH=/custom/models/en_PP-OCRv3_det_infer.onnx
export OCR_REC_MODEL_PATH=/custom/models/en_PP-OCRv3_rec_infer.onnx
export OCR_CLS_MODEL_PATH=/custom/models/ch_ppocr_mobile_v2.0_cls_infer.onnx

python -m app.main
```

> **注意**：自定义模型需兼容 PaddleOCR/RapidOCR 格式（ONNX 格式），且检测、识别、分类三个模型需要匹配同一版本（如 PP-OCRv3 或 PP-OCRv4）。

### 模型离线下载与加载

#### 方式一：使用下载脚本（推荐）

项目内置了 `download_model.py` 工具，一键下载模型到本地：

```bash
# 下载默认模型 (BAAI/bge-small-zh-v1.5)
python download_model.py

# 下载到指定目录
python download_model.py --save-dir /opt/models/bge-small-zh-v1.5

# 下载其他模型
python download_model.py --model BAAI/bge-large-zh-v1.5 --save-dir ./models/bge-large
```

下载完成后输出示例：
```
✓ 模型下载成功!
  路径: E:\knowledge_base\models\BAAI_bge-small-zh-v1.5
  文件数: 6

使用方法:
  Windows:
    $env:MODEL_LOCAL_PATH = 'E:\knowledge_base\models\BAAI_bge-small-zh-v1.5'
    python -m app.main
```

#### 方式二：HuggingFace CLI 下载

```bash
# 安装 huggingface-cli
pip install huggingface_hub

# 下载模型
huggingface-cli download BAAI/bge-small-zh-v1.5 \
  --local-dir ./models/bge-small-zh-v1.5
```

#### 方式三：浏览器手动下载

1. 访问 https://huggingface.co/BAAI/bge-small-zh-v1.5
2. 点击 "Files and versions" 标签
3. 下载以下文件到本地目录：
   - `config.json`
   - `model.safetensors` (或 `pytorch_model.bin`)
   - `tokenizer.json`
   - `tokenizer_config.json`
   - `vocab.txt`
   - `special_tokens_map.json`
   - `modules.json`
   - `sentence_bert_config.json`

#### 离线加载模型

下载完成后，通过以下方式让系统离线加载模型：

```bash
# Windows PowerShell
$env:MODEL_LOCAL_PATH = "E:\knowledge_base\models\bge-small-zh-v1.5"
python -m app.main

# Linux/macOS
export MODEL_LOCAL_PATH="/opt/models/bge-small-zh-v1.5"
python -m app.main

# 或修改 app/config.py (永久生效)
# MODEL_LOCAL_PATH = "E:\knowledge_base\models\bge-small-zh-v1.5"
```

启动成功后日志将显示：
```
检测到本地模型路径: ...，优先从本地加载
本地嵌入模型加载成功: ..., 维度: 512
```

> **提示**：设置 `MODEL_LOCAL_PATH` 后，系统会优先从本地路径加载模型，不再依赖网络。如果本地模型加载失败，会回退到在线下载模式。

#### 切换其他嵌入模型

系统支持所有 sentence-transformers 兼容的模型：

```bash
# BGE 系列 (中文推荐)
python download_model.py --model BAAI/bge-small-zh-v1.5 --save-dir ./models/bge-small-zh
python download_model.py --model BAAI/bge-base-zh-v1.5 --save-dir ./models/bge-base-zh
python download_model.py --model BAAI/bge-large-zh-v1.5 --save-dir ./models/bge-large-zh

# 通用英文模型
python download_model.py --model all-MiniLM-L6-v2 --save-dir ./models/all-MiniLM-L6-v2
python download_model.py --model paraphrase-multilingual-MiniLM-L12-v2 --save-dir ./models/paraphrase-multilingual

# 启动时设置对应的向量维度
# $env:EMBEDDING_DIM = "1024"  # bge-large 维度为 1024
```

**常用模型对照表**：

| 模型名称 | 维度 | 适用场景 | 大小 |
|----------|------|----------|------|
| `BAAI/bge-small-zh-v1.5` | 512 | 中文通用，速度快 | ~100MB |
| `BAAI/bge-base-zh-v1.5` | 768 | 中文精准，平衡型 | ~400MB |
| `BAAI/bge-large-zh-v1.5` | 1024 | 中文高精度 | ~1.2GB |
| `all-MiniLM-L6-v2` | 384 | 英文通用 | ~80MB |
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | 多语言 | ~420MB |

### 支持的文件格式

#### 文本类格式

| 格式 | 扩展名 | 解析方式 | 说明 |
|------|--------|----------|------|
| PDF 文档 | `.pdf` | 直接文本提取 / OCR | 自动检测：文本PDF直接提取，扫描版PDF自动OCR |
| Word 文档 | `.docx`, `.doc` | 直接文本提取 | 支持段落、表格解析 |
| **OFD 版式文档** | **`.ofd`** | **直接文本提取** | **国标 GB/T 33190，支持电子发票、政务公文等** |
| 纯文本 | `.txt` | 直接文本提取 | 支持多种编码自动检测 |
| Markdown | `.md` | 直接文本提取 | 保留 Markdown 格式 |

#### 图片格式 (OCR 识别)

| 格式 | 扩展名 | 解析方式 | 说明 |
|------|--------|----------|------|
| PNG 图片 | `.png` | OCR 识别 | 支持透明通道 |
| JPEG 图片 | `.jpg`, `.jpeg` | OCR 识别 | 最常用图片格式 |
| BMP 图片 | `.bmp` | OCR 识别 | 无压缩位图 |
| TIFF 图片 | `.tiff`, `.tif` | OCR 识别 | 支持多页 |
| GIF 图片 | `.gif` | OCR 识别 | 仅取第一帧 |

#### 智能解析策略

系统会根据文件类型自动选择最优解析方式：

```
文件导入
    │
    ├── 图片文件 (png, jpg, jpeg, bmp, tiff, gif)
    │   └── 自动 OCR 识别 → 提取文字 → 切片
    │
    ├── PDF 文件
    │   ├── 文本含量 > 50 字符 → 直接文本提取
    │   └── 文本含量 ≤ 50 字符 → 判定为扫描版 → OCR 识别
    │
    ├── Word 文件 (docx, doc)
    │   └── 直接文本提取（支持表格）
    │
    ├── OFD 文件 (ofd)
    │   └── easyofd 直接解析 → 提取文本和元数据 → 切片
    │
    └── 文本文件 (txt, md)
        └── 直接文本提取
```

新增格式可在 `app/config.py` 的 `SUPPORTED_FORMATS` 字典中扩展。

### 智能切片策略

系统采用**段落感知切片**算法，兼顾语义完整性和切片粒度控制：

```
原始文本
    │
    ├── 按换行符拆分为段落 (\n+)
    │
    └── 段落内按句子边界累积 (。！？.!?；;)
        │
        ├── 句子加入后超过 chunk_size → 保存当前 chunk，开启新 chunk
        │   └── 段落内 chunk 间保留 chunk_overlap 重叠
        │
        └── 段落结束 → 直接保存当前 chunk（即使未达 chunk_size）
            └── 段落间不重叠，保证段落边界完整性
```

**核心规则**：
- **段落边界优先**：遇到段落换行时，即使当前累积文本未达到 `CHUNK_SIZE`，也会直接将当前段落内容保存为一个独立切片
- **段内按句累积**：段落内部按句子边界逐步累积，超过 `CHUNK_SIZE` 时才切分
- **段内重叠**：同一段落内的多个 chunk 之间保留 `CHUNK_OVERLAP` 重叠字符
- **段间不重叠**：不同段落的 chunk 之间不重叠，避免跨段污染

**适用场景**：文档中包含大量短段落（如目录、列表、标题），传统固定长度切片会将多个无关段落强行合并，段落感知切片则保持每个段落的语义独立性。

---

## API 文档

### 统一响应格式

所有接口遵循统一的 `ApiResponse` 响应格式：

```json
{
    "code": 200,
    "message": "success",
    "data": { ... }
}
```

### 接口列表

#### 1. 健康检查

```
GET /api/health
```

#### 2. 系统监控

```
GET /api/monitor/status      # 系统状态概览
GET /api/monitor/resource    # 资源使用情况
GET /api/monitor/errors      # 异常日志
GET /api/monitor/logs        # 系统日志
```

#### 3. 知识库管理

```
POST   /api/kb                                      # 创建知识库
GET    /api/kb                                      # 知识库列表
GET    /api/kb/{kb_name}                            # 知识库详情
DELETE /api/kb/{kb_name}                            # 删除知识库
GET    /api/kb/{kb_name}/files                      # 文件列表
DELETE /api/kb/{kb_name}/files/{file_id}            # 删除文件
PUT    /api/kb/{kb_name}/chunks/{chunk_id}          # 编辑切片内容
DELETE /api/kb/{kb_name}/chunks/{chunk_id}          # 删除单个切片
```

**创建知识库请求示例**：
```json
POST /api/kb
{
    "name": "company_knowledge",
    "description": "公司内部知识库"
}
```

**编辑切片内容示例**：
```json
PUT /api/kb/company_knowledge/chunks/550e8400-e29b-41d4-a716-446655440000
{
    "text": "修改后的切片文本内容"
}
```

> **切片编辑说明**：编辑切片时系统会自动对新文本重新向量化并更新 Qdrant 中的向量点和 payload，payload 中会新增 `edited_at` 字段记录编辑时间。

**删除切片示例**：
```bash
DELETE /api/kb/company_knowledge/chunks/550e8400-e29b-41d4-a716-446655440000
```

> **切片删除说明**：删除切片会从 Qdrant 中永久移除对应的向量点，并自动递减文件的 `chunk_count` 和 `vector_count`。操作不可恢复。

#### 4. 文件导入

```
POST /api/import/single     # 单文件导入
POST /api/import/batch       # 批量文件导入
POST /api/import/zip         # ZIP 压缩包导入
GET  /api/import/tasks       # 导入任务列表
GET  /api/import/tasks/{id}  # 导入任务详情
```

**单文件导入示例** (multipart/form-data)：
```
POST /api/import/single
Content-Type: multipart/form-data

kb_name=company_knowledge
file=@/path/to/document.pdf
```

**批量导入示例**：
```
POST /api/import/batch
Content-Type: multipart/form-data

kb_name=company_knowledge
files=@/path/to/doc1.pdf
files=@/path/to/doc2.docx
files=@/path/to/doc3.txt
files=@/path/to/image.png
```

#### 5. OCR 服务监控

```
GET    /api/ocr/status           # OCR 服务状态
GET    /api/ocr/model-info       # OCR 模型详细信息
GET    /api/ocr/health           # OCR 健康检查
POST   /api/ocr/reset-stats      # 重置 OCR 统计数据
```

**OCR 状态响应示例**：
```json
{
  "code": 200,
  "data": {
    "status": "running",
    "engine_ready": true,
    "initialized": true,
    "uptime_seconds": 300,
    "uptime_display": "0h 5m 0s",
    "model_info": {
      "det_model": "ch_PP-OCRv4_det_infer.onnx",
      "rec_model": "ch_PP-OCRv4_rec_infer.onnx",
      "cls_model": "ch_ppocr_mobile_v2.0_cls_infer.onnx",
      "model_version": "PP-OCRv4",
      "framework": "RapidOCR + ONNX Runtime"
    },
    "memory": {
      "rss_mb": 991.45,
      "vms_mb": 14137.72,
      "percent": 0.8
    },
    "stats": {
      "total_requests": 10,
      "successful_requests": 9,
      "failed_requests": 1,
      "success_rate": 90.0,
      "total_pages_processed": 12,
      "total_chars_extracted": 2500,
      "avg_processing_time_ms": 250.5,
      "last_request_time": "2026-08-03T16:00:00"
    }
  }
}
```

**OCR 模型信息响应示例**：
```json
{
  "code": 200,
  "data": {
    "model_version": "PP-OCRv4",
    "framework": "RapidOCR + ONNX Runtime",
    "model_directory": "/path/to/ocr_service/models",
    "model_files": [
      {"name": "ch_PP-OCRv4_det_infer.onnx", "size_mb": 4.53},
      {"name": "ch_PP-OCRv4_rec_infer.onnx", "size_mb": 10.35},
      {"name": "ch_ppocr_mobile_v2.0_cls_infer.onnx", "size_mb": 0.56}
    ],
    "total_model_size_mb": 15.44,
    "model_files_ready": true
  }
}
```

#### 6. 实时进度推送 (WebSocket)

```
WS /ws/import-progress    # 导入进度实时推送
```

**WebSocket 消息格式**：
```json
// 初始化消息
{
  "type": "init",
  "task_id": null,
  "message": "WebSocket 连接成功"
}

// 任务创建消息
{
  "type": "task_created",
  "task_id": "abc12345",
  "kb_name": "company_knowledge",
  "total_files": 5
}

// 文件进度更新
{
  "type": "file_progress",
  "task_id": "abc12345",
  "file_name": "document.pdf",
  "stage": "extract",
  "progress": 50,
  "message": "文本提取完成",
  "needs_ocr": false
}

// OCR 进度更新
{
  "type": "file_progress",
  "task_id": "abc12345",
  "file_name": "scanned.pdf",
  "stage": "ocr",
  "progress": 60,
  "message": "OCR 识别中...",
  "needs_ocr": true,
  "ocr_reason": "PDF 文本含量极少，判定为扫描版"
}

// 任务完成消息
{
  "type": "task_completed",
  "task_id": "abc12345",
  "status": "completed",
  "total_files": 5,
  "successful": 4,
  "failed": 1,
  "progress": 100.0
}
```

**WebSocket 客户端示例**：
```javascript
// JavaScript
const ws = new WebSocket('ws://localhost:8000/ws/import-progress');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(`[${data.type}] ${data.message || ''}`);
    
    if (data.type === 'file_progress') {
        const ocrTag = data.needs_ocr ? ' [OCR]' : '';
        console.log(`${data.file_name}: ${data.progress}%${ocrTag} - ${data.message}`);
    }
    
    if (data.type === 'task_completed') {
        console.log(`任务完成: ${data.successful}/${data.total_files} 成功`);
    }
};
```

```python
# Python
import websocket
import json

ws = websocket.create_connection('ws://localhost:8000/ws/import-progress')

while True:
    msg = ws.recv()
    data = json.loads(msg)
    print(f"[{data['type']}] {data.get('message', '')}")
    
    if data['type'] == 'file_progress':
        ocr_tag = ' [OCR]' if data.get('needs_ocr') else ''
        print(f"  {data['file_name']}: {data['progress']}%{ocr_tag}")
```

#### 5. MCP 协议接口 (需鉴权)

所有 MCP 接口需在请求头中携带鉴权信息：

```
Authorization: Bearer kb-mcp-secret-key-2024
```

```
POST /api/mcp/search                                    # 知识库检索
GET  /api/mcp/knowledge-bases                           # 知识库列表
GET  /api/mcp/knowledge-bases/{kb}/documents/{chunk_id} # 文档详情
GET  /api/mcp/health                                    # MCP 服务健康检查
GET  /api/mcp/tools                                     # 可用工具列表
POST /api/mcp/tool/call                                 # 工具调用
```

**知识库检索示例**：
```json
POST /api/mcp/search
Authorization: Bearer kb-mcp-secret-key-2024
{
    "query": "公司的考勤制度是什么？",
    "kb_name": "company_knowledge",
    "top_k": 5,
    "score_threshold": 0.3,
    "use_reranker": true
}
```

**检索响应示例** (注意：`/api/mcp/search` 直接返回 SearchResponse，不包裹 ApiResponse)：
```json
{
    "query": "公司的考勤制度是什么？",
    "results": [
        {
            "chunk_id": "550e8400-e29b-41d4-a716-446655440000",
            "text": "公司实行标准工时制度...",
            "score": 0.8923,
            "metadata": {
                "file_name": "employee_handbook.pdf",
                "kb_name": "company_knowledge",
                "file_id": 1,
                "index": 0,
                "collection": "company_knowledge"
            }
        }
    ],
    "total": 1,
    "retrieval_info": {
        "method": "向量语义检索 + Reranker 精排",
        "model_name": "BAAI/bge-small-zh-v1.5",
        "vector_dim": 512,
        "demo_mode": false,
        "distance_metric": "余弦相似度 (Cosine)",
        "collections_searched": ["company_knowledge"],
        "recall_top_k": 10,
        "use_reranker": true,
        "reranker_model": "BAAI/bge-reranker-base",
        "embed_time_ms": 12.3,
        "search_time_ms": 5.1,
        "rerank_time_ms": 26.7,
        "total_time_ms": 44.1,
        "max_score": 0.8923,
        "min_score": 0.8923,
        "avg_score": 0.8923
    }
}
```

---

## MCP 协议服务

### MCP 服务端点

- **基础路径**: `http://{host}:8000/api/mcp`
- **协议**: 完全遵循 MCP (Model Context Protocol) 规范
- **鉴权**: Bearer Token 方式

### 可用 MCP 工具

| 工具名 | 说明 | 参数 |
|--------|------|------|
| `knowledge_search` | 检索知识库（支持Reranker精排） | `query` (必填), `kb_name`, `top_k`, `score_threshold`, `use_reranker` |
| `list_knowledge_bases` | 查询所有知识库 | 无 |
| `get_document_detail` | 查询文档切片详情 | `kb_name` (必填), `chunk_id` (必填) |
| `service_health_check` | 服务健康检测 | 无 |

### 对接大模型示例

**Python 调用**：
```python
import requests

API_KEY = "kb-mcp-secret-key-2024"
BASE_URL = "http://localhost:8000/api/mcp"

headers = {"Authorization": f"Bearer {API_KEY}"}

# 搜索知识库 (注意: /search 直接返回 SearchResponse, 不是 ApiResponse)
response = requests.post(
    f"{BASE_URL}/search",
    json={
        "query": "如何申请年假？",
        "kb_name": "hr_policy",
        "top_k": 3,
        "score_threshold": 0.3
    },
    headers=headers
)
data = response.json()  # 直接取, 不需要 ["data"]
for item in data["results"]:
    print(f"[{item['score']:.2f}] {item['text'][:80]}")

# 获取文档详情
detail = requests.get(
    f"{BASE_URL}/knowledge-bases/hr_policy/documents/{chunk_id}",
    headers=headers
).json()["data"]
```

**cURL 调用**：
```bash
# 健康检查
curl -H "Authorization: Bearer kb-mcp-secret-key-2024" \
     http://localhost:8000/api/mcp/health

# 知识库检索
curl -X POST \
     -H "Authorization: Bearer kb-mcp-secret-key-2024" \
     -H "Content-Type: application/json" \
     -d '{"query":"年假申请","top_k":3}' \
     http://localhost:8000/api/mcp/search
```

### 批量检索 (无知识库限定)

```python
# kb_name 置空则搜索所有知识库
response = requests.post(
    f"{BASE_URL}/search",
    json={"query": "搜索关键词", "top_k": 5},
    headers=headers
)
```

---

## API 接口访问知识库完整案例

以下示例演示从「创建知识库 → 导入文件 → 语义检索 → 查看切片」的完整流程。
所有示例假设服务运行在 `http://localhost:8000`。

### 方式一：cURL 完整流程

```bash
# ============ 1. 创建知识库 ============
curl -X POST http://localhost:8000/api/kb \
     -H "Content-Type: application/json" \
     -d '{"name": "company_docs", "description": "公司文档库"}'
# 返回: {"code":200,"message":"success","data":{"success":true,"message":"知识库 'company_docs' 创建成功"}}

# ============ 2. 导入单文件 ============
curl -X POST http://localhost:8000/api/import/single \
     -F "kb_name=company_docs" \
     -F "file=@/path/to/handbook.pdf" \
     -F "chunk_size=500" \
     -F "chunk_overlap=50"
# 返回: {"code":200,"message":"success","data":{"file_name":"handbook.pdf","status":"success","chunk_count":42,...}}

# ============ 3. 导入 ZIP 压缩包 (批量) ============
curl -X POST http://localhost:8000/api/import/zip \
     -F "kb_name=company_docs" \
     -F "file=@/path/to/docs.zip"

# ============ 4. 查看导入任务状态 ============
curl http://localhost:8000/api/import/tasks?kb_name=company_docs

# ============ 5. 语义检索 (需 MCP 鉴权) ============
curl -X POST http://localhost:8000/api/mcp/search \
     -H "Authorization: Bearer kb-mcp-secret-key-2024" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "公司请假制度是什么？",
       "kb_name": "company_docs",
       "top_k": 5,
       "score_threshold": 0.3
     }'
# 返回 (SearchResponse, 不包裹 ApiResponse):
# {
#   "query": "公司请假制度是什么？",
#   "results": [
#     {"chunk_id":"abc-123","text":"员工请假需提前...","score":0.89,"metadata":{...}},
#     ...
#   ],
#   "total": 5,
#   "retrieval_info": {"embed_time_ms":12.3,"search_time_ms":5.1,...}
# }

# ============ 6. 查看知识库列表 ============
curl -H "Authorization: Bearer kb-mcp-secret-key-2024" \
     http://localhost:8000/api/mcp/knowledge-bases

# ============ 7. 查看指定切片详情 ============
curl -H "Authorization: Bearer kb-mcp-secret-key-2024" \
     "http://localhost:8000/api/mcp/knowledge-bases/company_docs/documents/abc-123"
```

### 方式二：Python 完整流程

```python
import requests
import time

BASE = "http://localhost:8000"
API_KEY = "kb-mcp-secret-key-2024"
MCP_HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# ---- 1. 创建知识库 ----
resp = requests.post(f"{BASE}/api/kb", json={"name": "tech_wiki", "description": "技术文档库"})
print(f"创建知识库: {resp.json()}")

# ---- 2. 导入文件 ----
with open("guide.pdf", "rb") as f:
    resp = requests.post(
        f"{BASE}/api/import/single",
        data={"kb_name": "tech_wiki", "chunk_size": "500", "chunk_overlap": "50"},
        files={"file": ("guide.pdf", f, "application/pdf")},
    )
import_result = resp.json()["data"]
print(f"导入结果: {import_result['status']}, 切片数: {import_result['chunk_count']}")

# ---- 3. 等待模型就绪后检索 ----
resp = requests.post(
    f"{BASE}/api/mcp/search",
    json={"query": "如何配置数据库连接？", "kb_name": "tech_wiki", "top_k": 3},
    headers=MCP_HEADERS,
)
search_data = resp.json()  # SearchResponse 直接返回, 无需 ["data"]
for item in search_data["results"]:
    print(f"  [{item['score']:.2f}] {item['text'][:100]}")
    print(f"    来源: {item['metadata']['file_name']} (chunk {item['metadata']['index']})")

# ---- 4. 跨知识库检索 (不指定 kb_name) ----
resp = requests.post(
    f"{BASE}/api/mcp/search",
    json={"query": "部署流程", "top_k": 5},
    headers=MCP_HEADERS,
)
for item in resp.json()["results"]:
    print(f"  [{item['score']:.2f}] [{item['metadata']['kb_name']}] {item['text'][:80]}")

# ---- 5. 使用 MCP 工具调用接口 (统一入口) ----
resp = requests.post(
    f"{BASE}/api/mcp/tool/call",
    json={"tool_name": "knowledge_search", "arguments": {"query": "API鉴权方式", "top_k": 3}},
    headers=MCP_HEADERS,
)
# tool/call 返回 ApiResponse 格式, 需要取 ["data"]
print(resp.json()["data"]["results"])

# ---- 6. 删除文件 ----
resp = requests.delete(f"{BASE}/api/kb/tech_wiki/files/{import_result['file_id']}")
print(f"删除文件: {resp.json()}")

# ---- 7. 删除知识库 ----
resp = requests.delete(f"{BASE}/api/kb/tech_wiki")
print(f"删除知识库: {resp.json()}")
```

### API 响应格式速查

| 接口 | 响应格式 | 取数据方式 |
|------|----------|------------|
| `/api/kb/*` | ApiResponse `{code, message, data}` | `resp.json()["data"]` |
| `/api/import/*` | ApiResponse `{code, message, data}` | `resp.json()["data"]` |
| `/api/monitor/*` | ApiResponse `{code, message, data}` | `resp.json()["data"]` |
| `/api/health` | 直接返回 `{status, app, version}` | `resp.json()` |
| `/api/mcp/search` | SearchResponse `{query, results, total, retrieval_info}` | `resp.json()` |
| `/api/mcp/knowledge-bases` | ApiResponse `{code, message, data}` | `resp.json()["data"]` |
| `/api/mcp/health` | ApiResponse `{code, message, data}` | `resp.json()["data"]` |
| `/api/mcp/tools` | ApiResponse `{code, message, data}` | `resp.json()["data"]` |
| `/api/mcp/tool/call` | ApiResponse `{code, message, data}` | `resp.json()["data"]` |
| `/api/mcp/knowledge-bases/{kb}/documents/{id}` | ApiResponse `{code, message, data}` | `resp.json()["data"]` |

> **注意**：`/api/mcp/search` 是唯一直接返回 `SearchResponse` 的接口（不包裹 `ApiResponse`），因为它需要兼容 MCP 协议规范。其他 MCP 接口仍返回标准 `ApiResponse`。

---

## Web 管理界面

启动后访问 `http://localhost:8000` 即可使用可视化管理界面。

### 功能模块

| 模块 | 功能说明 |
|------|----------|
| **系统概览** | 知识库总数、向量总数、运行时长、今日导入数等核心指标 |
| **OCR 状态面板** | OCR 引擎状态、模型信息、资源占用、请求统计、平均处理时间 |
| **知识库管理** | 知识库列表、创建/删除、文档明细、文件切片预览、切片编辑/删除 |
| **文件导入** | 单文件上传、批量上传、ZIP 压缩包导入、实时进度追踪 |
| **知识检索** | 在线搜索测试，支持知识库筛选、结果数量、相似度阈值配置 |
| **系统监控** | 服务状态、资源使用、Qdrant 连接状态 |
| **日志管理** | 异常日志查询、系统日志查看 |
| **MCP 服务** | 工具列表、API Key 查看、健康检测 |

### OCR 状态面板

管理界面内置 OCR 状态面板，实时展示：

- **引擎状态**：运行中 / 已停止 / 未就绪
- **模型信息**：模型版本（PP-OCRv4）、框架（RapidOCR + ONNX Runtime）、模型文件列表
- **资源占用**：RSS 内存、虚拟内存、CPU 使用率
- **请求统计**：总请求数、成功率、平均处理时间、已处理页数、已提取字符数
- **操作按钮**：重置统计数据

### 导入进度追踪

导入文件时显示实时进度：

- **文件级进度**：每个文件的解析阶段（检测→提取→OCR→完成）
- **OCR 标识**：需要 OCR 处理的文件会标记 `[OCR]` 徽章
- **任务级进度**：总进度、已处理文件数、成功/失败统计
- **失败列表**：显示解析失败的文件和失败原因

### 操作流程

1. **创建知识库** → 进入「知识库管理」→ 点击「创建知识库」
2. **导入文件** → 进入「文件导入」→ 选择单文件/批量/ZIP 导入
3. **查看进度** → 导入过程中实时展示进度，完成后显示成功/失败清单
4. **OCR 处理** → 图片和扫描版 PDF 自动触发 OCR，进度条标记 `[OCR]`
5. **查看 OCR 状态** → 进入「OCR 状态面板」查看引擎运行情况
6. **预览内容** → 点击知识库 → 点击文件 → 查看切片内容
7. **检索测试** → 进入「知识检索」→ 输入问题 → 查看搜索结果

---

## 部署指南

### 本地部署

适用于 Windows/Linux 服务器，单机运行即可：

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务 (含 OCR 引擎预加载)
python -m app.main
# 或
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

启动后将自动加载：
- SQLite 元数据库
- Qdrant 向量数据库
- 嵌入模型（联网自动下载 / 离线加载）
- **OCR 引擎（RapidOCR PP-OCRv4 预加载）**

### Docker 部署

```bash
# 构建并启动
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f knowledge-base

# 查看 OCR 状态
curl http://localhost:8000/api/ocr/status

# 停止服务
docker-compose down
```

> **注意**：Docker 部署时，OCR 模型和嵌入模型需要在镜像中预置或通过卷挂载。

### 生产环境建议

1. **嵌入模型预下载**：在联网环境下运行 `python download_model.py` 预下载模型，之后设置 `MODEL_LOCAL_PATH` 离线加载；或直接联网首次启动自动下载
2. **OCR 模型确认**：确保 `ocr_service/models/` 目录下有 3 个 ONNX 模型文件（已预置）
3. **API Key 修改**：通过环境变量 `MCP_API_KEY` 设置安全的鉴权密钥
4. **数据持久化**：确保 `data/` 目录有读写权限，生产环境建议挂载独立磁盘
5. **反向代理**：建议使用 Nginx 做反向代理，配置 HTTPS 和限流
6. **进程守护**：Windows 环境可使用 NSSM 注册为系统服务；Linux 环境可使用 systemd
7. **资源监控**：OCR 引擎运行时占用约 1GB 内存，建议服务器内存 ≥ 2GB

**systemd 配置示例**：
```ini
[Unit]
Description=Knowledge Base Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/knowledge_base
Environment=MODEL_LOCAL_PATH=/opt/knowledge_base/models/bge-small-zh-v1.5
Environment=MCP_API_KEY=your-secure-key
# OCR 模型路径（使用默认预置路径时无需配置）
# Environment=OCR_DET_MODEL_PATH=/opt/knowledge_base/ocr_service/models/ch_PP-OCRv4_det_infer.onnx
# Environment=OCR_REC_MODEL_PATH=/opt/knowledge_base/ocr_service/models/ch_PP-OCRv4_rec_infer.onnx
# Environment=OCR_CLS_MODEL_PATH=/opt/knowledge_base/ocr_service/models/ch_ppocr_mobile_v2.0_cls_infer.onnx
ExecStart=/opt/knowledge_base/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### OCR 模型部署说明

#### 预置模型

项目默认预置 **PP-OCRv4 中文 OCR 模型**，位于 `ocr_service/models/` 目录：

```
ocr_service/models/
├── ch_PP-OCRv4_det_infer.onnx      # 文字检测模型
├── ch_PP-OCRv4_rec_infer.onnx      # 文字识别模型
└── ch_ppocr_mobile_v2.0_cls_infer.onnx  # 方向分类器
```

模型文件总计约 15.4MB，占用空间小，已包含在项目仓库中。

#### 自定义模型部署

如需使用其他模型版本或语言：

1. **下载模型文件**：从 PaddleOCR 官方仓库下载对应的 ONNX 模型
2. **放置到指定目录**：将 3 个模型文件放入 `ocr_service/models/` 或自定义目录
3. **配置环境变量**：

```bash
# 方式一：覆盖默认目录
cp en_PP-OCRv3_det_infer.onnx ocr_service/models/
cp en_PP-OCRv3_rec_infer.onnx ocr_service/models/

# 方式二：指定自定义路径
export OCR_DET_MODEL_PATH=/custom/path/det.onnx
export OCR_REC_MODEL_PATH=/custom/path/rec.onnx
export OCR_CLS_MODEL_PATH=/custom/path/cls.onnx
```

> **注意**：检测、识别、分类三个模型必须来自同一版本（如 PP-OCRv3 或 PP-OCRv4），不支持跨版本混用。

#### 模型验证

启动服务后通过 API 验证模型是否正确加载：

```bash
curl http://localhost:8000/api/ocr/model-info | python3 -m json.tool
```

返回 `model_files_ready: true` 表示模型加载成功。

### 集群扩展

当前为单机部署架构，后续可平滑升级：

- Qdrant 切换为集群模式：修改 `QDRANT_HOST` 指向集群地址
- 嵌入模型扩展：更换 `EMBEDDING_MODEL` 配置即可切换模型
- OCR 模型扩展：替换 `ocr_service/models/` 下的模型文件
- 文件格式扩展：在 `config.py` 的 `SUPPORTED_FORMATS` 中注册新格式

---

## 常见问题

### Q: 启动时提示"无法连接到 HuggingFace"？

A: 系统将自动切换为演示模式。推荐通过以下方式解决：
- **方式1（推荐）**：在联网环境下运行 `python download_model.py` 预下载模型，之后设置 `MODEL_LOCAL_PATH` 离线加载
- **方式2**：确保服务器可访问 `huggingface.co`
- **方式3**：使用 `HF_HUB_OFFLINE=1` + 预下载模型到 `~/.cache/huggingface/`

### Q: OCR 模型加载失败怎么办？

A: 检查以下几点：
1. 确认 `ocr_service/models/` 目录下有 3 个 ONNX 模型文件
2. 确认文件大小正常（总计约 15.4MB）
3. 通过 API 检查状态：`curl http://localhost:8000/api/ocr/health`
4. 查看日志中的错误信息
5. 若模型文件损坏，从仓库重新获取或从 PaddleOCR 官方下载

### Q: OCR 识别准确率不高怎么办？

A: 可尝试以下优化：
1. **图片质量**：上传清晰、分辨率高的图片（建议 ≥ 300 DPI）
2. **图片预处理**：系统会自动进行灰度化、二值化、降噪等处理
3. **模型调整**：可更换更高精度的 OCR 模型（如 PP-OCRv4 → PP-OCRv5）
4. **语言设置**：当前默认中文模型，如需英文识别请更换对应模型

### Q: 如何判断文件是否会触发 OCR？

A: 系统会自动判断：
- **图片文件**（png, jpg, bmp, tiff, gif）：自动触发 OCR
- **PDF 文件**：检测文本含量，若平均每页 ≤ 50 字符则判定为扫描版并触发 OCR
- 触发 OCR 的文件在导入进度中会标记 `[OCR]` 徽章

### Q: OCR 处理速度慢怎么办？

A: 影响 OCR 速度的因素：
- **文件大小**：图片越大处理越慢，建议单张 ≤ 20MB
- **PDF 页数**：OCR 按页处理，页数越多越慢（默认最大 50 页）
- **硬件性能**：CPU 性能越好越快
- **优化建议**：设置合适的 `MAX_IMAGE_SIZE` 和 `MAX_PDF_PAGES` 限制

### Q: 端口 8000 被占用怎么办？

A: 修改 `config.py` 中的 `APP_PORT` 或通过环境变量 `APP_PORT` 指定其他端口。

### Q: 支持哪些文件格式？

A: 当前支持：
- **文本类**：PDF (.pdf)、Word (.docx/.doc)、**OFD 版式文档 (.ofd)**、TXT (.txt)、Markdown (.md)
- **图片类**：PNG (.png)、JPEG (.jpg/.jpeg)、BMP (.bmp)、TIFF (.tiff/.tif)、GIF (.gif)

可在 `config.py` 的 `SUPPORTED_FORMATS` 中扩展。

### Q: OFD 文件解析失败怎么办？

A: 可能原因及解决方案：
1. **缺少依赖**：OFD 解析需要 `easyofd` 和 `xmltodict`，确认已安装：
   ```bash
   pip install easyofd xmltodict
   ```
2. **文件格式不标准**：部分厂商生成的 OFD 可能不完全遵循 GB/T 33190 标准，尝试用官方工具转换后再导入
3. **OFD 版本兼容性**：当前支持 OFD 1.0/2.0 版本，更高版本请联系技术支持
4. **加密/签名 OFD**：加密或带签名的 OFD 文件无法直接解析，需先解密或去除签名
5. **查看日志**：详细错误信息可在 `data/logs/` 目录下查看

### Q: OFD 文件中的图片能否被识别？

A: OFD 内嵌的图片资源会被自动识别并提取元数据（格式、大小、位置）。如需对图片内容进行 OCR 识别，建议先将 OFD 转换为图片后单独导入，系统会自动触发 OCR。

### Q: 如何修改嵌入模型？

A: 有两种方式：
- **在线模式**（联网环境）：通过环境变量指定模型名，首次启动会自动下载：
```bash
export EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
export EMBEDDING_DIM=1024
```
- **离线模式**（推荐）：先下载模型到本地，再设置路径：
```bash
python download_model.py --model BAAI/bge-large-zh-v1.5 --save-dir ./models/bge-large
export MODEL_LOCAL_PATH="./models/bge-large"
export EMBEDDING_DIM=1024
```
注意：更换模型需同步修改 `EMBEDDING_DIM`，且旧数据需要重新导入。

### Q: 文件大小限制是多少？

A: 默认单文件最大 100MB，可通过 `config.py` 中的 `MAX_FILE_SIZE` 修改。
OCR 相关限制：
- 单图片最大 20MB（`ocr_service/config.py` 中的 `MAX_IMAGE_SIZE`）
- 单 PDF 最大 50MB（`MAX_PDF_SIZE`）
- PDF OCR 最大 50 页（`MAX_PDF_PAGES`）

### Q: 如何重置所有数据？

A: 删除 `data/` 目录下的所有文件后重启服务即可：
```bash
# Linux/macOS
rm -rf data/*

# Windows PowerShell
Remove-Item -Recurse -Force data\*
```

### Q: MCP 接口返回 401 鉴权失败？

A: 请确认请求头包含正确的 Authorization：
```
Authorization: Bearer {API_KEY}
```
默认密钥为 `kb-mcp-secret-key-2024`，生产环境请通过 `MCP_API_KEY` 修改。

### Q: OCR 状态面板显示"引擎未就绪"？

A: 可能原因：
1. 模型文件缺失：检查 `ocr_service/models/` 目录
2. 模型加载超时：查看日志确认是否有加载错误
3. 内存不足：OCR 引擎需要至少 1GB 可用内存
4. **解决**：重启服务，OCR 引擎会在后台自动重新加载

### Q: 如何批量导入整个文件夹？

A: 将文件夹打包为 ZIP 后通过 `/api/import/zip` 接口导入，或使用 `/api/import/batch` 多文件上传接口。

### Q: 导入进度 WebSocket 连接不上？

A: 检查以下几点：
1. 服务是否正常运行
2. WebSocket 端点是否正确：`ws://localhost:8000/ws/import-progress`
3. 浏览器是否支持 WebSocket
4. 是否有反向代理拦截 WebSocket 连接

---

## 许可证

本项目仅供学习和商业使用。

---

**版本**: v2.2.0 | **更新日期**: 2026-08-05

### 更新日志

#### v2.2.0 (2026-08-05)

新增功能：
- **段落感知切片**：优化文档切片算法，遇到段落换行时即使未达 `CHUNK_SIZE` 也直接切分，保持段落语义完整性
- **切片编辑功能**：支持在 Web 界面和 API 中编辑切片内容，编辑后自动重新向量化并更新 Qdrant 中的向量点和 payload
- **切片删除功能**：支持删除单个切片，从 Qdrant 永久移除向量点并自动递减文件 chunk_count

新增 API 接口：
- `PUT /api/kb/{kb_name}/chunks/{chunk_id}` — 编辑切片内容
- `DELETE /api/kb/{kb_name}/chunks/{chunk_id}` — 删除单个切片

新增 MCP 工具（工具数 23 → 25）：
- `update_chunk` — 编辑切片内容（自动重新向量化）
- `delete_chunk` — 删除单个切片

修复问题：
- 修复 `config.py` 中 `APP_PORT` 默认值(8080)与 Dockerfile/docker-compose/文档(8000)不一致的问题

#### v2.1.0 (2026-08-04)

新增功能：
- **OFD 版式文档解析**：支持 GB/T 33190 国标 OFD 文件直接解析，适用于电子发票、政务公文等场景
- **OFD 文本提取**：基于 easyofd 库实现 OFD 文档的文本、元数据、图片资源提取
- **OFD 集成管线**：完整接入文件导入 → 检测 → 解析 → 切片 → 向量化 → 入库流程

新增支持格式：
- OFD 版式文档：.ofd

依赖变更：
- 新增 `easyofd>=20260427`（OFD 解析核心）
- 新增 `xmltodict>=0.13.0`（OFD XML 解析）

#### v2.0.0 (2026-08-03)

新增功能：
- **OCR 智能识别**：集成 RapidOCR (PP-OCRv4) 引擎，支持图片和扫描版 PDF 自动 OCR 识别
- **智能文件检测**：自动识别文件类型，判断是否需要 OCR 处理
- **解析管道**：文档解析流程重构为 detect → extract → ocr → chunk → complete 五个阶段
- **实时进度推送**：通过 WebSocket 实时推送文件解析进度
- **OCR 状态面板**：管理界面新增 OCR 引擎状态监控面板
- **请求统计**：记录 OCR 请求数、成功率、平均处理时间等指标

支持的新格式：
- 图片类：png, jpg, jpeg, bmp, tiff, gif

#### v1.0.0 (2026-07-31)

初始版本发布：
- 知识库 CRUD 管理
- 文件导入（单文件/批量/ZIP）
- 向量检索
- MCP 协议服务
- Web 管理界面