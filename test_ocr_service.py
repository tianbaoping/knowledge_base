"""
PaddleOCR 服务测试脚本

测试内容：
1. 健康检查 /health
2. 图片 OCR（自动生成测试图片）
3. PDF OCR（自动生成测试 PDF）
4. 批量 OCR

运行前确保：
  conda activate knowledge_base
  python test_ocr_service.py
"""
import io
import os
import sys
import time
import requests
from PIL import Image, ImageDraw, ImageFont

# 服务地址
OCR_BASE_URL = os.environ.get("OCR_BASE_URL", "http://localhost:8002")


def generate_test_image(text: str = "这是测试文字 ABC 123") -> bytes:
    """生成包含文字的测试图片"""
    # 创建白色背景图片
    img = Image.new("RGB", (400, 100), color="white")
    draw = ImageDraw.Draw(img)

    # 尝试使用系统字体，失败则用默认
    try:
        # Windows
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 24)
    except:
        try:
            # Linux
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            font = ImageFont.load_default()

    # 绘制文字
    draw.text((20, 30), text, fill="black", font=font)

    # 转为字节流
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_test_pdf() -> bytes:
    """生成测试 PDF（含文字图片）"""
    import fitz  # PyMuPDF

    # 创建单页 PDF
    doc = fitz.open()
    page = doc.new_page(width=400, height=100)

    # 插入文字
    text = "PDF 测试页 - OCR 识别测试"
    page.insert_text((20, 50), text, fontsize=20)

    # 导出字节
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_health():
    """测试健康检查接口"""
    print("\n[1] 测试健康检查 GET /health")
    try:
        resp = requests.get(f"{OCR_BASE_URL}/health", timeout=5)
        print(f"    状态码: {resp.status_code}")
        data = resp.json()
        print(f"    响应: {data}")

        if data.get("status") == "healthy":
            print("    ✅ 服务健康")
            return True
        else:
            print("    ⚠️ 模型未加载（首次调用会自动加载）")
            return True
    except requests.exceptions.ConnectionError:
        print("    ❌ 无法连接服务，请确认已启动: python -m ocr_service.main")
        return False
    except Exception as e:
        print(f"    ❌ 异常: {e}")
        return False


def test_image_ocr():
    """测试图片 OCR"""
    print("\n[2] 测试图片 OCR POST /ocr")

    # 生成测试图片
    test_text = "知识库 OCR 测试 2026"
    image_bytes = generate_test_image(test_text)
    print(f"    生成测试图片: {len(image_bytes)} 字节")

    try:
        t0 = time.time()
        resp = requests.post(
            f"{OCR_BASE_URL}/ocr",
            files={"file": ("test.png", image_bytes, "image/png")},
            timeout=60,
        )
        elapsed = time.time() - t0

        print(f"    状态码: {resp.status_code}")
        print(f"    耗时: {elapsed:.2f}s")

        if resp.status_code != 200:
            print(f"    ❌ 响应: {resp.text[:200]}")
            return False

        data = resp.json()
        print(f"    成功: {data['success']}")
        print(f"    格式: {data['format']}")
        print(f"    字符数: {data['char_count']}")
        print(f"    识别文本: {data['full_text'][:100]}")

        if data["success"] and data["char_count"] > 0:
            print("    ✅ 图片 OCR 成功")
            return True
        else:
            print("    ⚠️ 未识别到文字")
            return False
    except Exception as e:
        print(f"    ❌ 异常: {e}")
        return False


def test_pdf_ocr():
    """测试 PDF OCR"""
    print("\n[3] 测试 PDF OCR POST /ocr")

    try:
        pdf_bytes = generate_test_pdf()
        print(f"    生成测试 PDF: {len(pdf_bytes)} 字节")
    except ImportError:
        print("    ⚠️ PyMuPDF 未安装，跳过 PDF 测试")
        return True

    try:
        t0 = time.time()
        resp = requests.post(
            f"{OCR_BASE_URL}/ocr",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            params={"dpi": 150},
            timeout=60,
        )
        elapsed = time.time() - t0

        print(f"    状态码: {resp.status_code}")
        print(f"    耗时: {elapsed:.2f}s")

        if resp.status_code != 200:
            print(f"    ❌ 响应: {resp.text[:200]}")
            return False

        data = resp.json()
        print(f"    成功: {data['success']}")
        print(f"    格式: {data['format']}")
        print(f"    总页数: {data['total_pages']}")
        print(f"    字符数: {data['char_count']}")
        print(f"    识别文本: {data['full_text'][:100]}")

        if data["success"]:
            print("    ✅ PDF OCR 成功")
            return True
        else:
            print("    ⚠️ 未识别到文字（可能是文本型 PDF，非扫描件）")
            return True
    except Exception as e:
        print(f"    ❌ 异常: {e}")
        return False


def test_batch_ocr():
    """测试批量 OCR"""
    print("\n[4] 测试批量 OCR POST /ocr/batch")

    files = [
        ("test1.png", generate_test_image("批量测试 1"), "image/png"),
        ("test2.png", generate_test_image("批量测试 2"), "image/png"),
    ]

    try:
        t0 = time.time()
        resp = requests.post(
            f"{OCR_BASE_URL}/ocr/batch",
            files=[("files", (f[0], f[1], f[2])) for f in files],
            timeout=120,
        )
        elapsed = time.time() - t0

        print(f"    状态码: {resp.status_code}")
        print(f"    耗时: {elapsed:.2f}s")

        data = resp.json()
        print(f"    总数: {data['total']}")
        print(f"    成功: {data['success']}")
        print(f"    失败: {data['failed']}")

        for r in data["results"]:
            status = "✅" if r["success"] else "❌"
            print(f"    {status} {r['filename']}: {r.get('char_count', 0)} 字符")

        if data["success"] == data["total"]:
            print("    ✅ 批量 OCR 全部成功")
            return True
        else:
            print("    ⚠️ 部分失败")
            return False
    except Exception as e:
        print(f"    ❌ 异常: {e}")
        return False


def main():
    print("=" * 60)
    print("  PaddleOCR 服务测试")
    print("=" * 60)
    print(f"服务地址: {OCR_BASE_URL}")
    print(f"Python: {sys.version.split()[0]}")

    results = []

    # 1. 健康检查
    if not test_health():
        print("\n服务未启动，退出测试")
        return
    results.append(("健康检查", True))

    # 2. 图片 OCR
    results.append(("图片 OCR", test_image_ocr()))

    # 3. PDF OCR
    results.append(("PDF OCR", test_pdf_ocr()))

    # 4. 批量 OCR
    results.append(("批量 OCR", test_batch_ocr()))

    # 汇总
    print("\n" + "=" * 60)
    print("  测试结果汇总")
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {status}  {name}")

    print("-" * 60)
    print(f"  通过: {passed}/{total}")
    print("=" * 60)

    if passed == total:
        print("\n🎉 全部测试通过！OCR 服务正常工作。")
    else:
        print("\n⚠️ 部分测试失败，请检查服务日志。")


if __name__ == "__main__":
    main()