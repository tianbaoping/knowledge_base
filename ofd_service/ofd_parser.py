"""
OFD 文档解析工具类

独立的 OFD 解析工具，无外部配置依赖，可在任何模块中直接导入使用。

OFD (Open Fixed-layout Document) 是中国版式文档国家标准 (GB/T 33190)，
本质是一个 ZIP 压缩包，内部使用 XML 描述文档结构。

用法示例::

    from ofd_service.ofd_parser import OFDParser

    parser = OFDParser()

    # 从文件路径解析
    result = parser.parse_file("invoice.ofd")
    print(result.text)

    # 从字节流解析
    with open("doc.ofd", "rb") as f:
        result = parser.parse_bytes(f.read())
    print(result.text)
    print(result.page_count)
    print(result.metadata)

    # 转 PDF
    pdf_bytes = parser.to_pdf("doc.ofd")

    # 转图片
    images = parser.to_images("doc.ofd", dpi=200)
    for img in images:
        print(f"第{img['page']}页 {img['width']}x{img['height']}")
"""
import base64
import io
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from loguru import logger


class OFDParseResult:
    """OFD 解析结果"""

    def __init__(self):
        self.valid: bool = False
        self.page_count: int = 0
        self.text: str = ""
        self.pages: List[Dict[str, Any]] = []
        self.metadata: Dict[str, str] = {}
        self.has_images: bool = False
        self.has_fonts: bool = False
        self.image_resources: List[Dict[str, Any]] = []
        self.elapsed: float = 0.0
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "page_count": self.page_count,
            "text": self.text,
            "pages": self.pages,
            "metadata": self.metadata,
            "has_images": self.has_images,
            "has_fonts": self.has_fonts,
            "image_count": len(self.image_resources),
            "elapsed": self.elapsed,
            "error": self.error,
        }

    def __repr__(self):
        return (
            f"OFDParseResult(valid={self.valid}, pages={self.page_count}, "
            f"chars={len(self.text)}, has_images={self.has_images})"
        )


class OFDParser:
    """
    OFD 文档解析工具类

    提供以下能力：
        - 文本提取 (parse_file / parse_bytes)
        - 结构解析 (get_info)
        - PDF 转换 (to_pdf)
        - 图片转换 (to_images)
        - 图片资源提取 (extract_images)

    无状态、线程安全，可直接实例化使用。
    """

    # OFD 内部 XML 命名空间
    _OFD_NS = "http://www.ofdspec.org/2016"
    _IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff"}

    def parse_file(self, file_path: str) -> OFDParseResult:
        """
        解析 OFD 文件

        Args:
            file_path: OFD 文件路径

        Returns:
            OFDParseResult
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        if path.suffix.lower() != ".ofd":
            raise ValueError(f"文件必须是 .ofd 格式: {file_path}")

        with open(path, "rb") as f:
            return self.parse_bytes(f.read())

    def parse_bytes(self, ofd_bytes: bytes) -> OFDParseResult:
        """
        解析 OFD 字节流，提取文本和结构信息

        Args:
            ofd_bytes: OFD 文件二进制数据

        Returns:
            OFDParseResult
        """
        import time
        t0 = time.time()
        result = OFDParseResult()

        try:
            # 1. 解析结构
            structure = self._parse_structure(ofd_bytes)
            result.valid = True
            result.page_count = len(structure["pages"])
            result.has_images = len(structure["resources"]["images"]) > 0
            result.has_fonts = len(structure["resources"]["fonts"]) > 0
            result.metadata = structure["metadata"]

            # 2. 提取文本
            pages, full_text_parts = self._extract_text_from_xml(ofd_bytes)
            result.pages = pages
            result.text = "\n".join(full_text_parts)

            # 3. 提取图片资源信息
            result.image_resources = self._extract_image_list(ofd_bytes)

        except zipfile.BadZipFile:
            result.error = "无效的 OFD 文件（非 ZIP 格式）"
            logger.error(result.error)
        except ET.ParseError as e:
            result.error = f"OFD XML 解析失败: {e}"
            logger.error(result.error)
        except Exception as e:
            result.error = str(e)
            logger.error(f"OFD 解析失败: {e}")

        result.elapsed = round(time.time() - t0, 3)
        return result

    def get_info(self, file_path_or_bytes) -> Dict[str, Any]:
        """
        获取 OFD 文档元信息（轻量级，不提取全文文本）

        Args:
            file_path_or_bytes: 文件路径或字节流

        Returns:
            {"format": "OFD", "valid": bool, "pages": int, ...}
        """
        ofd_bytes = self._read_input(file_path_or_bytes)
        structure = self._parse_structure(ofd_bytes)
        return {
            "format": "OFD",
            "valid": True,
            "pages": len(structure["pages"]),
            "has_images": len(structure["resources"]["images"]) > 0,
            "has_fonts": len(structure["resources"]["fonts"]) > 0,
            "metadata": structure["metadata"],
        }

    def to_pdf(self, file_path_or_bytes) -> bytes:
        """
        将 OFD 转换为 PDF

        Args:
            file_path_or_bytes: 文件路径或字节流

        Returns:
            PDF 二进制数据
        """
        try:
            from easyofd import OFD
        except ImportError:
            raise RuntimeError("easyofd 未安装，请运行 pip install easyofd")

        ofd_bytes = self._read_input(file_path_or_bytes)
        ofd_b64 = base64.b64encode(ofd_bytes).decode("utf-8")

        ofd = OFD()
        ofd.read(ofd_b64)
        pdf_bytes = ofd.to_pdf()

        logger.info(f"OFD -> PDF 转换完成，{len(pdf_bytes)} bytes")
        return pdf_bytes

    def to_images(
        self,
        file_path_or_bytes,
        dpi: int = 200,
        pages: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        将 OFD 转换为图片

        Args:
            file_path_or_bytes: 文件路径或字节流
            dpi: 渲染 DPI，默认 200
            pages: 指定页码列表（1-based），None 表示全部

        Returns:
            [{"page": int, "image": bytes, "format": "PNG", "width": int, "height": int}]
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError("PyMuPDF 未安装，请运行 pip install PyMuPDF")

        ofd_bytes = self._read_input(file_path_or_bytes)
        pdf_bytes = self.to_pdf(ofd_bytes)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)

        if pages:
            page_indices = [p - 1 for p in pages if 1 <= p <= total_pages]
        else:
            page_indices = range(total_pages)

        result = []
        for idx in page_indices:
            page = doc[idx]
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")

            result.append({
                "page": idx + 1,
                "image": img_bytes,
                "format": "PNG",
                "width": pix.width,
                "height": pix.height,
            })

        doc.close()
        logger.info(f"OFD -> 图片转换完成，共 {len(result)} 页")
        return result

    def extract_images(self, file_path_or_bytes) -> List[Dict[str, Any]]:
        """
        提取 OFD 中嵌入的图片资源

        Args:
            file_path_or_bytes: 文件路径或字节流

        Returns:
            [{"filename": str, "image": bytes, "format": str, "size": int}]
        """
        ofd_bytes = self._read_input(file_path_or_bytes)
        result = []

        with zipfile.ZipFile(io.BytesIO(ofd_bytes)) as zf:
            for name in zf.namelist():
                lower_name = name.lower()
                if "/images/" in lower_name or "/image/" in lower_name:
                    ext = Path(name).suffix.lower().lstrip(".")
                    if ext in self._IMG_EXTS:
                        try:
                            img_bytes = zf.read(name)
                            result.append({
                                "filename": name,
                                "image": img_bytes,
                                "format": ext.upper(),
                                "size": len(img_bytes),
                            })
                        except Exception as e:
                            logger.warning(f"提取图片 {name} 失败: {e}")

        return result

    # ==================== 内部方法 ====================

    @staticmethod
    def _read_input(file_path_or_bytes) -> bytes:
        """统一处理文件路径或字节流输入"""
        if isinstance(file_path_or_bytes, (str, Path)):
            path = Path(file_path_or_bytes)
            if not path.exists():
                raise FileNotFoundError(f"文件不存在: {path}")
            with open(path, "rb") as f:
                return f.read()
        elif isinstance(file_path_or_bytes, bytes):
            return file_path_or_bytes
        else:
            raise TypeError(f"不支持的输入类型: {type(file_path_or_bytes)}")

    def _parse_structure(self, ofd_bytes: bytes) -> Dict[str, Any]:
        """解析 OFD 文件结构"""
        result = {
            "pages": [],
            "resources": {"fonts": [], "images": []},
            "metadata": {},
        }

        with zipfile.ZipFile(io.BytesIO(ofd_bytes)) as zf:
            namelist = zf.namelist()

            # 解析 OFD.xml 入口
            if "OFD.xml" in namelist:
                ofd_xml = zf.read("OFD.xml").decode("utf-8")
                root = ET.fromstring(ofd_xml)
                for child in root:
                    if "DocBody" in child.tag or "DocInfo" in child.tag:
                        for elem in child:
                            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                            if elem.text and elem.text.strip():
                                result["metadata"][tag] = elem.text.strip()

            # 解析页面信息
            pages_dir = None
            for name in namelist:
                if "/Pages/" in name and name.endswith(".xml"):
                    parts = name.split("/")
                    for i, p in enumerate(parts):
                        if p == "Pages":
                            pages_dir = "/".join(parts[: i + 1])
                            break
                    break

            if pages_dir:
                page_files = sorted(
                    [n for n in namelist if n.startswith(pages_dir) and n.endswith(".xml")]
                )
                for idx, pf in enumerate(page_files):
                    result["pages"].append({"index": idx, "file": pf})

            # 查找资源文件
            for name in namelist:
                lower_name = name.lower()
                if "/fonts/" in lower_name or "/font/" in lower_name:
                    result["resources"]["fonts"].append(name)
                elif "/images/" in lower_name or "/image/" in lower_name:
                    result["resources"]["images"].append(name)

        return result

    def _extract_text_from_xml(
        self, ofd_bytes: bytes
    ) -> Tuple[List[Dict], List[str]]:
        """直接从 OFD 的 XML 结构提取文本"""
        pages = []
        full_text_parts = []

        with zipfile.ZipFile(io.BytesIO(ofd_bytes)) as zf:
            namelist = zf.namelist()
            page_files = sorted(
                [n for n in namelist if "/Pages/" in n and n.endswith(".xml")]
            )

            for idx, pf in enumerate(page_files):
                try:
                    content = zf.read(pf).decode("utf-8")
                    root = ET.fromstring(content)
                    text_parts = []

                    for elem in root.iter():
                        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                        if tag == "TextCode" and elem.text:
                            text_parts.append(elem.text)
                        elif elem.text and elem.text.strip() and tag not in ("Path", "Image"):
                            text = elem.text.strip()
                            if not text.replace(".", "").replace("-", "").isdigit():
                                if text not in text_parts:
                                    text_parts.append(text)

                    page_text = " ".join(text_parts)
                except Exception:
                    page_text = ""

                pages.append({
                    "page": idx + 1,
                    "text": page_text,
                    "char_count": len(page_text),
                })
                full_text_parts.append(page_text)

        return pages, full_text_parts

    def _extract_image_list(self, ofd_bytes: bytes) -> List[Dict[str, Any]]:
        """提取图片资源列表（不读取图片数据，仅元信息）"""
        result = []

        with zipfile.ZipFile(io.BytesIO(ofd_bytes)) as zf:
            for name in zf.namelist():
                lower_name = name.lower()
                if "/images/" in lower_name or "/image/" in lower_name:
                    ext = Path(name).suffix.lower().lstrip(".")
                    if ext in self._IMG_EXTS:
                        info = zf.getinfo(name)
                        result.append({
                            "filename": name,
                            "format": ext.upper(),
                            "size": info.file_size,
                        })

        return result