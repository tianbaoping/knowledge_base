# 知识库管理系统 - MCP Server 对接文档

> 本文档面向智能体（AI Agent）开发者，描述如何通过 MCP (Model Context Protocol) 协议对接知识库管理系统。
> 本系统已实现**真正的 MCP Server**（基于官方 Python SDK `mcp >= 2.0`），符合 MCP 2025-11-25 规范。
> Claude Desktop、Cursor、Cline、VS Code MCP 扩展等主流客户端可**零配置直接对接**。

---

## 目录

- [目录](#目录)
- [服务信息](#服务信息)
- [传输方式](#传输方式)
- [客户端配置](#客户端配置)
- [工具清单总览](#工具清单总览)
- [检索类工具](#检索类工具)
- [知识库管理工具](#知识库管理工具)
- [文件管理工具](#文件管理工具)
- [切片管理工具](#切片管理工具)
- [文件导入工具](#文件导入工具)
- [导入任务工具](#导入任务工具)
- [系统监控工具](#系统监控工具)
- [OCR 服务监控工具](#ocr-服务监控工具)
- [OCR 识别工具](#ocr-识别工具)
- [工具返回格式](#工具返回格式)
- [典型工作流](#典型工作流)
- [cURL 调试](#curl-调试)
- [兼容性说明](#兼容性说明)

---

## 服务信息

| 项目 | 值 |
|------|-----|
| 服务名称 | knowledge-base-mcp |
| 协议版本 | MCP 2025-11-25 |
| SDK | `mcp >= 2.0` (官方 Python SDK) |
| Streamable HTTP 端点 | `http://{host}:8000/mcp` |
| stdio 启动命令 | `python -m app.mcp_server.server` |
| 工具数量 | 25 |
| 默认端口 | 8000 |

---

## 传输方式

本 MCP Server 支持两种标准传输方式：

### 1. Streamable HTTP（远程对接，推荐）

- **端点**: `POST http://{host}:8000/mcp`
- **协议**: JSON-RPC 2.0 over HTTP
- **Accept 头**: 必须同时包含 `application/json` 和 `text/event-stream`
- **适用场景**: Cursor、远程 Agent、Web 后端

### 2. stdio（本地对接）

- **启动命令**: `python -m app.mcp_server.server`
- **协议**: JSON-RPC 2.0 over stdin/stdout
- **适用场景**: Claude Desktop、本地 IDE 插件

---

## 客户端配置

### Claude Desktop

编辑配置文件 `claude_desktop_config.json`：

**Streamable HTTP 模式**（推荐）:
```json
{
  "mcpServers": {
    "knowledge-base": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

**stdio 模式**（本地子进程）:
```json
{
  "mcpServers": {
    "knowledge-base": {
      "command": "python",
      "args": ["-m", "app.mcp_server.server"],
      "cwd": "E:\\BaoPing_Work\\knowledge_base"
    }
  }
}
```

> 配置文件路径：
> - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
> - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### Cursor

在 Settings → MCP 中添加：

```json
{
  "mcpServers": {
    "knowledge-base": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Cline / VS Code MCP 扩展

```json
{
  "mcp.servers": {
    "knowledge-base": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Python SDK 客户端

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    async with streamable_http_client("http://localhost:8000/mcp") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 列出工具
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"  {tool.name}: {tool.description}")

            # 调用检索工具
            result = await session.call_tool(
                "knowledge_search",
                {"query": "年假天数", "kb_name": "company-handbook", "top_k": 5}
            )
            for content in result.content:
                print(content.text)

asyncio.run(main())
```

---

## 工具清单总览

| # | 工具名 | 类别 | 功能简述 |
|---|--------|------|----------|
| 1 | `knowledge_search` | 检索 | 语义检索知识库，支持Reranker精排，返回最相关文本片段 |
| 2 | `get_document_detail` | 检索 | 按切片ID查询原文内容（溯源） |
| 3 | `list_knowledge_bases` | 知识库管理 | 列出所有知识库 |
| 4 | `create_knowledge_base` | 知识库管理 | 创建新知识库 |
| 5 | `get_knowledge_base_detail` | 知识库管理 | 获取知识库详情+文件列表 |
| 6 | `delete_knowledge_base` | 知识库管理 | 删除知识库（不可恢复） |
| 7 | `list_files` | 文件管理 | 列出知识库中的所有文件 |
| 8 | `delete_file` | 文件管理 | 删除指定文件 |
| 9 | `get_file_chunks` | 文件管理 | 查看文件的切片内容 |
| 10 | `update_chunk` | 切片管理 | 编辑切片内容（自动重新向量化） |
| 11 | `delete_chunk` | 切片管理 | 删除单个切片（不可恢复） |
| 12 | `import_single_file` | 文件导入 | 从服务器路径导入单个文件 |
| 13 | `import_batch_files` | 文件导入 | 从服务器路径批量导入文件 |
| 14 | `import_zip_file` | 文件导入 | 从ZIP压缩包批量导入 |
| 15 | `list_import_tasks` | 导入任务 | 查询导入任务列表 |
| 16 | `get_import_task` | 导入任务 | 查询导入任务详情 |
| 17 | `service_health_check` | 系统监控 | 服务健康检查 |
| 18 | `get_system_status` | 系统监控 | 系统状态概览 |
| 19 | `get_resource_info` | 系统监控 | 资源使用情况 |
| 20 | `get_ocr_status` | OCR 服务监控 | 获取 OCR 引擎完整状态（就绪/模型/内存/统计） |
| 21 | `get_ocr_model_info` | OCR 服务监控 | 获取 OCR 模型详细信息（版本/文件列表/大小） |
| 22 | `ocr_health_check` | OCR 服务监控 | OCR 服务健康检查（引擎+模型文件） |
| 23 | `reset_ocr_stats` | OCR 服务监控 | 重置 OCR 请求统计数据 |
| 24 | `ocr_recognize_image` | OCR 识别 | 直接 OCR 识别服务器上的图片文件 |
| 25 | `ocr_recognize_pdf` | OCR 识别 | 直接 OCR 识别服务器上的 PDF 文件（扫描版） |

---

## 检索类工具

### 1. knowledge_search

搜索私有知识库，返回与问题最相关的文本片段。支持指定知识库或跨库检索。支持 Reranker 重排序优化（两阶段检索：先向量召回10条，再Reranker精排返回Top-K条）。

**参数**:

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| query | string | ✅ | - | 搜索问题 |
| kb_name | string | ❌ | null | 知识库名称，为空搜索所有 |
| top_k | int | ❌ | 5 | 最终返回结果数量 (1-50) |
| score_threshold | float | ❌ | 0.3 | 相似度阈值 (0-1) |
| use_reranker | boolean | ❌ | true | 是否使用Reranker重排序。开启后先召回10条再精排返回top_k条 |

**调用示例**:
```json
{
  "query": "年假有几天",
  "kb_name": "company-handbook",
  "top_k": 5,
  "score_threshold": 0.3,
  "use_reranker": true
}
```

**返回**: JSON 字符串，包含 `query`、`results`(含 text/score/metadata)、`total`、`retrieval_info`

**retrieval_info 关键字段**:

| 字段 | 说明 |
|------|------|
| `method` | 检索方法：向量语义检索 / 向量语义检索+Reranker精排 |
| `recall_top_k` | 第一阶段向量召回数量（启用Reranker时为10） |
| `use_reranker` | 是否使用Reranker |
| `reranker_model` | Reranker模型名称 |
| `rerank_time_ms` | Reranker精排耗时（毫秒） |
| `embed_time_ms` | 向量化耗时 |
| `search_time_ms` | 向量检索耗时 |
| `total_time_ms` | 总耗时 |

### 2. get_document_detail

按切片ID查询原文内容，用于检索结果溯源。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| kb_name | string | ✅ | 知识库名称 |
| chunk_id | string | ✅ | 切片ID（从检索结果获取） |

---

## 知识库管理工具

### 3. list_knowledge_bases

列出所有可用的知识库。无参数。

### 4. create_knowledge_base

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | ✅ | 知识库名称 (1-100字符) |
| description | string | ❌ | 知识库描述 |

### 5. get_knowledge_base_detail

**参数**: `kb_name` (string, 必填)

### 6. delete_knowledge_base

**参数**: `kb_name` (string, 必填) — 不可恢复操作

---

## 文件管理工具

### 7. list_files

**参数**: `kb_name` (string, 必填)

### 8. delete_file

**参数**: `kb_name` (string, 必填), `file_id` (int, 必填)

### 9. get_file_chunks

**参数**: `kb_name` (string, 必填), `file_id` (int, 必填)

---

## 切片管理工具

> 本组工具用于对已分块的切片进行编辑和删除，支持精细化知识库内容管理。

### 10. update_chunk

编辑指定切片的文本内容，系统会自动重新向量化并更新向量数据库中的点和 payload。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| kb_name | string | ✅ | 知识库名称 |
| chunk_id | string | ✅ | 切片ID (从 get_file_chunks 或 knowledge_search 结果中获取) |
| text | string | ✅ | 修改后的切片文本内容 |

**调用示例**:
```json
{
  "kb_name": "company-handbook",
  "chunk_id": "550e8400-e29b-41d4-a716-446655440000",
  "text": "公司实行标准工时制度，工作时间为周一至周五 9:00-18:00。"
}
```

**返回**: JSON 字符串：
```json
{
  "success": true,
  "message": "切片编辑成功",
  "chunk_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

> **说明**: 编辑后系统会自动用新的文本重新生成向量并更新 Qdrant 中的点，payload 中会新增 `edited_at` 字段记录编辑时间。

### 11. delete_chunk

删除指定的切片，从向量数据库中永久移除该切片（不可恢复）。删除后会自动递减对应文件的 chunk_count。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| kb_name | string | ✅ | 知识库名称 |
| chunk_id | string | ✅ | 切片ID (从 get_file_chunks 或 knowledge_search 结果中获取) |

**调用示例**:
```json
{
  "kb_name": "company-handbook",
  "chunk_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**返回**: JSON 字符串：
```json
{
  "success": true,
  "message": "切片删除成功"
}
```

> **注意**: 删除操作不可恢复，切片对应的向量会从 Qdrant 中永久移除。如需恢复需重新导入原文件。

---

## 文件导入工具

> 文件导入工具接收**服务器本地文件路径**（非上传），适用于智能体在服务器侧自动化导入。

### 12. import_single_file

从服务器本地路径导入单个文件。

**参数**:

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| kb_name | string | ✅ | - | 知识库名称 |
| file_path | string | ✅ | - | 服务器上的文件绝对路径 |
| chunk_size | int | ❌ | 500 | 切片长度(字符数) |
| chunk_overlap | int | ❌ | 50 | 切片重叠长度(字符数) |

**支持格式**: pdf, docx, txt, md, ofd, png, jpg, jpeg, bmp, tiff, gif

### 13. import_batch_files

批量导入多个文件。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| kb_name | string | ✅ | 知识库名称 |
| file_paths | array[string] | ✅ | 文件绝对路径列表 |
| chunk_size | int | ❌ | 切片长度 |
| chunk_overlap | int | ❌ | 切片重叠长度 |

### 14. import_zip_file

从ZIP压缩包批量导入，自动解压并处理所有支持格式的文件。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| kb_name | string | ✅ | 知识库名称 |
| zip_path | string | ✅ | 服务器上的ZIP文件绝对路径 |
| chunk_size | int | ❌ | 切片长度 |
| chunk_overlap | int | ❌ | 切片重叠长度 |

---

## 导入任务工具

### 15. list_import_tasks

**参数**: `kb_name` (string, 可选)

### 16. get_import_task

**参数**: `task_id` (int, 必填)

---

## 系统监控工具

### 17. service_health_check

检测服务是否正常运行。无参数。

### 18. get_system_status

获取系统状态概览（知识库数、文件数、向量数等）。无参数。

### 19. get_resource_info

获取系统资源使用情况（磁盘、内存等）。无参数。

---

## OCR 服务监控工具

> 本组工具用于监控 OCR 引擎运行状态和模型信息，需在服务启动后通过 `main.py` 的 OCR 引擎加载流程自动初始化。

### 20. get_ocr_status

获取 OCR 引擎完整状态，包括引擎就绪状态、模型信息、内存占用、请求统计等。无参数。

**返回**: JSON 字符串，包含以下字段：

| 字段 | 说明 |
|------|------|
| `status` | 引擎状态：`running` / `initializing` / `stopped` |
| `engine_ready` | 引擎是否就绪（布尔） |
| `uptime_display` | 运行时长（如 `0h 5m 30s`） |
| `model_info` | 模型版本、文件列表、框架信息 |
| `memory` | RSS 内存、虚拟内存、CPU 占比 |
| `stats` | 请求总数、成功率、平均处理时间、已处理页数 |

### 21. get_ocr_model_info

获取 OCR 模型详细信息。无参数。

**返回**: JSON 字符串，包含：
- `model_version`: `PP-OCRv4`
- `framework`: `RapidOCR + ONNX Runtime`
- `model_files`: 3 个 ONNX 文件的名称和大小
- `total_model_size_mb`: 模型总大小
- `model_files_ready`: 3 个模型文件是否齐全

### 22. ocr_health_check

OCR 服务健康检查，检测引擎是否就绪、模型文件是否完整。无参数。

**返回**: JSON 字符串：
```json
{
  "healthy": true,
  "status": "running",
  "engine_ready": true,
  "model_files_ready": true,
  "message": "OCR 服务运行正常"
}
```

### 23. reset_ocr_stats

重置 OCR 请求统计数据（请求数、成功率、处理时间等归零）。无参数。

**返回**: `{"success": true, "message": "OCR 统计数据已重置"}`

---

## OCR 识别工具

> 本组工具提供直接 OCR 识别能力，无需通过知识库导入流程，可直接识别服务器上的图片或 PDF 文件。

### 24. ocr_recognize_image

使用 OCR 识别服务器上的图片文件，提取图片中的文字内容。

**参数**:

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| file_path | string | ✅ | - | 服务器上的图片文件绝对路径 |
| page_num | int | ❌ | 1 | 页码（多页场景使用） |

**支持格式**: png, jpg, jpeg, bmp, tiff, gif

**调用示例**:
```json
{
  "file_path": "/data/images/contract_scan.png"
}
```

**返回**: JSON 字符串：
```json
{
  "page": 1,
  "text": "甲方：XX公司\n乙方：YY公司\n签订日期：2026-08-01",
  "lines": [
    {"line_index": 0, "text": "甲方：XX公司", "score": 0.98, "box": [[x1,y1],...]},
    ...
  ],
  "line_count": 3,
  "char_count": 28,
  "processing_time_ms": 245.3,
  "file_path": "/data/images/contract_scan.png"
}
```

### 25. ocr_recognize_pdf

使用 OCR 识别服务器上的 PDF 文件（扫描版 PDF 适用）。逐页渲染为图片后识别。

**参数**:

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| file_path | string | ✅ | - | 服务器上的 PDF 文件绝对路径 |
| max_pages | int | ❌ | 50 | 最大处理页数（超过会报错） |
| dpi | int | ❌ | 200 | 渲染 DPI（越高精度越高但速度越慢） |

**调用示例**:
```json
{
  "file_path": "/data/docs/scanned_report.pdf",
  "max_pages": 20,
  "dpi": 200
}
```

**返回**: JSON 字符串：
```json
{
  "total_pages": 5,
  "pages": [
    {
      "page": 1,
      "text": "封面内容...",
      "lines": [...],
      "line_count": 10,
      "char_count": 150
    },
    ...
  ],
  "full_text": "封面内容...\n\n第二章内容...",
  "char_count": 800,
  "processing_time_ms": 3520.5,
  "file_path": "/data/docs/scanned_report.pdf",
  "file_size_mb": 12.5
}
```

> **注意**: 文本 PDF 建议使用 `import_single_file` 直接解析（速度更快、精度更高）。`ocr_recognize_pdf` 适用于扫描版 PDF（纯图片，无文本层）。

---

## 工具返回格式

所有工具返回均遵循 MCP 规范的 `content` 格式：

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"query\": \"年假\", \"results\": [...], \"total\": 3}"
    }
  ],
  "isError": false
}
```

- `content[0].text` 是业务数据的 JSON 字符串，智能体解析后使用
- `isError` 为 `true` 时表示工具执行出错

---

## 典型工作流

### 工作流 1: 知识库问答（最常用）

```
1. list_knowledge_bases          → 确认可用知识库
2. knowledge_search              → 语义检索（默认启用Reranker精排）
   两阶段检索: 向量召回10条 → Reranker精排 → 返回Top-K条
3. get_document_detail           → 溯源原文（可选）
```

### 工作流 1b: 快速检索（无需Reranker）

```
1. knowledge_search              → 使用 use_reranker=false 跳过精排
   直接向量检索返回Top-K条，速度更快
   适用于对响应时间要求高的场景
```

### 工作流 2: 知识库初始化

```
1. create_knowledge_base         → 创建知识库
2. import_batch_files            → 批量导入文件
   (图片/扫描版 PDF 自动触发 OCR)
3. get_import_task               → 查看导入进度（含 OCR 状态）
4. knowledge_search              → 验证检索效果
```

### 工作流 3: 文件直接 OCR 识别

```
1. ocr_health_check              → 确认 OCR 引擎就绪
2. ocr_recognize_image           → 直接识别图片文字
   或 ocr_recognize_pdf          → 直接识别扫描版 PDF
3. 提取结果用于后续处理或导入
```

### 工作流 4: OCR 状态监控

```
1. get_ocr_status                → 查看引擎状态和统计
2. get_ocr_model_info            → 查看模型版本和完整性
3. reset_ocr_stats               → 重置统计数据
```

### 工作流 5: 知识库运维

```
1. get_system_status             → 查看系统概览
2. get_ocr_status                → 查看 OCR 状态
3. list_files                    → 检查文件清单
4. delete_file                   → 清理过期文件
5. service_health_check          → 确认服务健康
```

### 工作流 6: 切片精细化管理

```
1. get_file_chunks               → 查看文件的切片列表
2. update_chunk                  → 编辑有误的切片内容（自动重新向量化）
3. delete_chunk                  → 删除无意义的切片
4. knowledge_search              → 验证编辑后的检索效果
```

---

## cURL 调试

### 列出工具

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

### 调用检索工具

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "knowledge_search",
      "arguments": {"query": "年假天数", "kb_name": "company-handbook"}
    }
  }'
```

> **注意**: Accept 头必须同时包含 `application/json` 和 `text/event-stream`，否则返回 406。

---

## 兼容性说明

本系统同时提供两套接口：

| 接口 | 端点 | 协议 | 适用场景 |
|------|------|------|----------|
| **标准 MCP Server** | `POST /mcp` | JSON-RPC 2.0 | Claude Desktop / Cursor / Cline 等 MCP 客户端 |
| 旧版 REST API | `/api/mcp/*` | HTTP REST | Web 管理界面、自定义脚本 |

- **标准 MCP Server**（`/mcp`）: 基于官方 mcp SDK，主流 MCP 客户端可直接对接
- **旧版 REST API**（`/api/mcp/*`）: 保留向后兼容，供 Web 前端和已有集成使用

新项目对接请优先使用标准 MCP Server 端点。

---

> **版本**: v3.2.0 | **协议**: MCP 2025-11-25 | **工具数量**: 25 | **更新日期**: 2026-08-06
