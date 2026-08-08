# OFD 服务 - 中国版式文档解析

OFD (Open Fixed-layout Document) 是中国版式文档国家标准 (GB/T 33190)，在电子发票、公文传输等领域广泛使用。本服务提供 OFD 文档解析能力。

## 特性

- 文本提取：提取 OFD 文档中的文本内容
- 结构解析：解析 OFD 文件结构（页面、资源、元数据）
- PDF 转换：将 OFD 转换为 PDF 格式
- 图片转换：将 OFD 页面渲染为图片
- 资源提取：提取 OFD 中嵌入的图片资源

## 目录结构

```
ofd_service/
├── __init__.py        # 包初始化，导出 OFDParser
├── ofd_parser.py      # OFD 解析工具类（核心）
├── main.py            # FastAPI 服务入口
├── requirements.txt   # 依赖
├── sample_rich.ofd    # 示例 OFD 文件
└── README.md          # 本文档
```

## 安装

```bash
pip install -r ofd_service/requirements.txt
```

核心依赖：
- `easyofd` - OFD 解析库
- `PyMuPDF` - PDF/图片处理
- `fastapi` + `uvicorn` - Web 服务（仅启动 API 时需要）
- `loguru` - 日志

## 使用方式

### 1. 作为 Python 工具类（推荐）

```python
from ofd_service import OFDParser

parser = OFDParser()

# 从文件解析
result = parser.parse_file("invoice.ofd")
print(result.valid)        # True
print(result.page_count)   # 6
print(result.text)         # 全文文本
print(result.pages)        # [{"page": 1, "text": "...", "char_count": 70}, ...]
print(result.metadata)     # {"DocRoot": "Doc_0/Document.xml"}

# 从字节流解析
with open("doc.ofd", "rb") as f:
    result = parser.parse_bytes(f.read())

# 轻量级元信息（不提取文本）
info = parser.get_info("doc.ofd")

# 转 PDF
pdf_bytes = parser.to_pdf("doc.ofd")

# 转图片
images = parser.to_images("doc.ofd", dpi=200)
for img in images:
    print(f"第 {img['page']} 页: {img['width']}x{img['height']}")

# 提取嵌入图片
imgs = parser.extract_images("doc.ofd")

# 序列化为 dict
d = result.to_dict()
```

### 2. 作为 FastAPI 服务

```bash
# 启动服务（默认端口 8003）
python -m ofd_service.main

# 或指定端口
OFD_PORT=9000 python -m ofd_service.main
```

服务启动后访问：
- API 文档：http://localhost:8003/docs
- 健康检查：http://localhost:8003/health

## API 接口

### POST /ofd/parse - 解析 OFD 结构

```
curl -X POST http://localhost:8003/ofd/parse \
  -F "file=@invoice.ofd"
```

### POST /ofd/text - 提取文本

```
curl -X POST http://localhost:8003/ofd/text \
  -F "file=@invoice.ofd"
```

响应：
```json
{
  "full_text": "提取的完整文本...",
  "pages": [{"page": 1, "text": "第 1 页文本", "char_count": 100}],
  "total_pages": 6,
  "char_count": 2404,
  "elapsed": 0.002
}
```

### POST /ofd/pdf - 转 PDF

```
curl -X POST http://localhost:8003/ofd/pdf \
  -F "file=@invoice.ofd" \
  -o output.pdf
```

### POST /ofd/images - 转图片

```
curl -X POST http://localhost:8003/ofd/images \
  -F "file=@invoice.ofd" \
  -F "dpi=200"
```

### POST /ofd/extract - 提取嵌入图片

```
curl -X POST http://localhost:8003/ofd/extract \
  -F "file=@invoice.ofd"
```

## OFDParser API

| 方法 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `parse_file(path)` | 文件路径 | `OFDParseResult` | 完整解析（文本+结构+元数据） |
| `parse_bytes(bytes)` | 字节流 | `OFDParseResult` | 完整解析 |
| `get_info(path_or_bytes)` | 路径或字节流 | `dict` | 轻量级元信息 |
| `to_pdf(path_or_bytes)` | 路径或字节流 | `bytes` | 转 PDF |
| `to_images(path_or_bytes, dpi, pages)` | 路径或字节流, DPI, 页码列表 | `list[dict]` | 转图片 |
| `extract_images(path_or_bytes)` | 路径或字节流 | `list[dict]` | 提取嵌入图片 |

## OFDParseResult 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `valid` | `bool` | 是否有效 OFD |
| `page_count` | `int` | 总页数 |
| `text` | `str` | 全文文本 |
| `pages` | `list[dict]` | 分页文本 `[{page, text, char_count}]` |
| `metadata` | `dict` | 元数据 |
| `has_images` | `bool` | 是否包含图片 |
| `has_fonts` | `bool` | 是否包含字体 |
| `image_resources` | `list[dict]` | 图片资源列表 |
| `elapsed` | `float` | 解析耗时（秒） |
| `error` | `str\|None` | 错误信息 |

## 限制

| 项目 | 限制 |
|------|------|
| 单个 OFD 文件 | 50MB |

## 注意事项

1. easyofd 库对某些 OFD 标准版本支持有限，如遇解析问题请检查 OFD 文件是否符合 GB/T 33190 标准
2. PDF/图片转换依赖 easyofd 的渲染能力，复杂文档可能渲染不完整
3. 对于生产环境，建议使用官方 OFD 阅读器验证转换结果
