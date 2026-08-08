"""
OFD 服务 - 中国版式文档解析服务

提供 OFD 文档解析能力：
  - 文本提取
  - 图片提取
  - 转 PDF/图片
  - 元数据解析
"""
from .ofd_parser import OFDParser, OFDParseResult

__all__ = ["OFDParser", "OFDParseResult"]