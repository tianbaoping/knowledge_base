# OCR 服务 (RapidOCR)

基于 **RapidOCR (PP-OCRv4 中文模型)** 的独立 OCR 微服务，使用 ONNX Runtime 推理，支持图片和扫描版 PDF 文字识别。

> **为什么用 RapidOCR？** RapidOCR 是 PaddleOCR 的 C++/ONNX Runtime 实现，兼容 PP-OCRv4 模型，且规避了 PaddlePaddle 3.x 在 Windows 上的 PIR 兼容性问题。识别精度与原版 PaddleOCR 一致。

## 特性

- PP-OCRv4 中文模型（检测 + 识别 + 方向分类）
- 基于 ONNX Runtime，跨平台兼容（Windows / Linux）
- 支持图片：JPG/PNG/BMP/TIFF/WEBP
- 支持 PDF：逐页渲染后 OCR（含扫描版 PDF）
- 懒加载：首次调用时才加载模型，启动快
- 单例模式：全局共享一个 OCR 实例，避免重复加载
- 独立服务 + 可被知识库调用

## 目录结构

```
ocr_service/
├── __init__.py          # 包初始化
├── main.py              # FastAPI 服务入口
├── ocr_engine.py        # OCR 引擎封装 (RapidOCR)
├── config.py            # 配置
├── requirements.txt     # 依赖
├── start.bat            # Windows 启动
├── start.sh             # Linux 启动
├── models/              # 模型存放（首次运行自动下载）
└── README.md            # 本文档
```

## 安装

```bash
pip install -r ocr_service/requirements.txt
```

依赖说明：
- `rapidocr-onnxruntime` - PP-OCRv4 模型的 ONNX Runtime 实现（约 15MB）
- `PyMuPDF` - PDF 渲染
- `Pillow` + `numpy` - 图片处理
- `fastapi` + `uvicorn` - Web 服务

首次运行时，RapidOCR 会自动下载 PP-OCRv4 检测和识别模型（约 50MB）到本地缓存。

## 启动

```bash
# Linux
chmod +x ocr_service/start.sh
./ocr_service/start.sh

# Windows
ocr_service\start.bat

# 或直接运行
python -m ocr_service.main
```

服务启动后：
- API 文档：http://localhost:8002/docs
- 健康检查：http://localhost:8002/health
- 首页：http://localhost:8002/

### 环境变量配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OCR_HOST` | `0.0.0.0` | 监听地址 |
| `OCR_PORT` | `8002` | 监听端口 |
| `OCR_DET_MODEL_PATH` | `ocr_service/models/ch_PP-OCRv4_det_infer.onnx` | 自定义检测模型路径 |
| `OCR_REC_MODEL_PATH` | `ocr_service/models/ch_PP-OCRv4_rec_infer.onnx` | 自定义识别模型路径 |
| `OCR_CLS_MODEL_PATH` | `ocr_service/models/ch_ppocr_mobile_v2.0_cls_infer.onnx` | 自定义方向分类模型路径 |

## API 接口

### 1. 健康检查

```
GET /health
```

```json
{
  "status": "healthy",
  "model_loaded": true,
  "model": "PP-OCRv4 Chinese"
}
```

### 2. 单文件识别

```
POST /ocr
Content-Type: multipart/form-data

file=@document.pdf
# 或
file=@image.png
```

**参数**：
- `file`: 图片或 PDF 文件（必填）
- `dpi`: PDF 渲染 DPI，默认 200，范围 72-600（仅对 PDF 生效）

**响应**：
```json
{
  "success": true,
  "format": "pdf",
  "elapsed": 3.456,
  "total_pages": 2,
  "full_text": "识别出的全文内容...\n\n第二页内容...",
  "pages": [
    {
      "page": 1,
      "text": "识别出的全文内容...",
      "lines": [
        {
          "line_index": 0,
          "text": "识别出的某行文字",
          "score": 0.9876,
          "box": [[10.0, 20.0], [100.0, 20.0], [100.0, 50.0], [10.0, 50.0]]
        }
      ],
      "line_count": 5,
      "char_count": 120
    }
  ],
  "char_count": 240
}
```

### 3. 批量识别

```
POST /ocr/batch
Content-Type: multipart/form-data

files=@a.png
files=@b.pdf
files=@c.jpg
```

**响应**：
```json
{
  "total": 3,
  "success": 3,
  "failed": 0,
  "results": [
    {
      "filename": "a.png",
      "success": true,
      "format": "image",
      "elapsed": 0.234,
      "total_pages": 1,
      "char_count": 50,
      "full_text": "...",
      "pages": [...]
    },
    ...
  ]
}
```

## 调用示例

### Python

```python
import requests

# 图片 OCR
with open("scan.png", "rb") as f:
    resp = requests.post(
        "http://localhost:8002/ocr",
        files={"file": f}
    )
print(resp.json()["full_text"])

# PDF OCR
with open("scanned.pdf", "rb") as f:
    resp = requests.post(
        "http://localhost:8002/ocr",
        files={"file": f},
        params={"dpi": 300}
    )
print(resp.json()["full_text"])
```

### curl

```bash
# 图片
curl -X POST http://localhost:8002/ocr \
  -F "file=@scan.png"

# PDF（高 DPI）
curl -X POST "http://localhost:8002/ocr?dpi=300" \
  -F "file=@scanned.pdf"
```

## 与知识库集成

OCR 服务启动后，可通过 HTTP 调用为知识库的 `parser_service.py` 扩展扫描件支持：

```python
import requests

def _parse_pdf_with_ocr(self, file_path):
    with open(file_path, "rb") as f:
        resp = requests.post(
            "http://localhost:8002/ocr",
            files={"file": f},
            timeout=300
        )
    if resp.ok:
        data = resp.json()
        return {
            "file_name": os.path.basename(file_path),
            "file_format": "pdf",
            "text_content": data["full_text"],
            "pages": [{"page": p["page"], "text": p["text"]} for p in data["pages"]],
            "total_pages": data["total_pages"],
            "char_count": data["char_count"],
        }, "OCR 解析成功"
    return None, f"OCR 服务调用失败: {resp.status_code}"
```

## 限制

| 项 | 限制 |
|----|------|
| 单张图片 | 20MB |
| 单个 PDF | 50MB |
| PDF 页数 | 50 页 |
| 批量文件 | 20 个 |

## 性能参考

| 模式 | 单页耗时 | 说明 |
|------|----------|------|
| CPU | 1-3 秒 | 推荐 DPI 200 |

## 常见问题

### Q: 首次启动很慢？

A: 首次调用会自动下载 PP-OCRv4 模型（约 50MB），之后从本地缓存加载。

### Q: 与 PaddleOCR 有什么区别？

A: RapidOCR 使用 ONNX Runtime 推理，无需安装 PaddlePaddle 深度学习框架。优点是：
- 安装简单（无 PaddlePaddle 编译依赖）
- 跨平台兼容性好（Windows/Linux 均可用）
- 内存占用更低
- 识别精度与 PP-OCRv4 一致

### Q: 支持 GPU 加速吗？

A: 当前 RapidOCR 版本使用 CPU 推理。如需 GPU 加速，可使用原版 PaddleOCR + PaddlePaddle-GPU。
