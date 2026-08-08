"""
压缩包处理服务 - 支持多种压缩格式
==================================
支持格式:
    - .zip (Python 内置)
    - .tar, .tar.gz, .tar.bz2, .tar.xz (Python 内置 tarfile)
    - .rar (需要 rarfile 库)
    - .7z (需要 py7zr 库)
"""

import os
import re
import shutil
import zipfile
import tarfile
from typing import List, Optional, Tuple
from pathlib import Path
from loguru import logger

# 压缩文件扩展名到处理方法的映射
ARCHIVE_EXTENSIONS = {
    'zip': 'zip',
    'rar': 'rar',
    '7z': '7z',
    'tar': 'tar',
    'tgz': 'tar',
    'gz': 'tar',       # .tar.gz
    'bz2': 'tar',      # .tar.bz2
    'xz': 'tar',       # .tar.xz
}

# 完整的扩展名列表（用于前端 accept 属性）
SUPPORTED_ARCHIVE_EXTS = ['zip', 'rar', '7z', 'tar', 'tgz', 'gz', 'bz2', 'xz']


def detect_archive_type(filename: str) -> Optional[str]:
    """
    检测文件的压缩类型
    
    Args:
        filename: 文件名
        
    Returns:
        压缩类型: 'zip', 'rar', '7z', 'tar' 或 None
    """
    lower_name = filename.lower()
    
    # 按优先级检测 (避免 .gz 被误判)
    if lower_name.endswith('.zip'):
        return 'zip'
    elif lower_name.endswith('.rar'):
        return 'rar'
    elif lower_name.endswith('.7z'):
        return '7z'
    elif lower_name.endswith('.tar') or lower_name.endswith('.tar.gz') or \
         lower_name.endswith('.tar.bz2') or lower_name.endswith('.tar.xz') or \
         lower_name.endswith('.tgz'):
        return 'tar'
    else:
        return None


def is_archive_file(filename: str) -> bool:
    """
    判断文件是否为支持的压缩包
    
    Args:
        filename: 文件名
        
    Returns:
        是否为压缩包
    """
    ext = get_main_extension(filename)
    return ext in ARCHIVE_EXTENSIONS


def get_main_extension(filename: str) -> str:
    """
    获取文件的主扩展名 (处理 .tar.gz 等复合扩展名)
    """
    lower_name = filename.lower()
    
    if lower_name.endswith('.tar.gz') or lower_name.endswith('.tgz'):
        return 'tgz'
    elif lower_name.endswith('.tar.bz2'):
        return 'bz2'
    elif lower_name.endswith('.tar.xz'):
        return 'xz'
    elif lower_name.endswith('.tar'):
        return 'tar'
    elif lower_name.endswith('.zip'):
        return 'zip'
    elif lower_name.endswith('.rar'):
        return 'rar'
    elif lower_name.endswith('.7z'):
        return '7z'
    else:
        # 普通扩展名
        _, ext = os.path.splitext(filename)
        return ext.lstrip('.').lower()


def extract_archive(archive_path: str, extract_to: str) -> Tuple[List[str], Optional[str]]:
    """
    解压压缩包到指定目录
    
    Args:
        archive_path: 压缩包文件路径
        extract_to: 解压目标目录
        
    Returns:
        (解压出的文件路径列表, 错误信息)
    """
    archive_type = detect_archive_type(os.path.basename(archive_path))
    
    if archive_type is None:
        return [], "不支持的压缩格式"
    
    try:
        if archive_type == 'zip':
            return _extract_zip(archive_path, extract_to)
        elif archive_type == 'tar':
            return _extract_tar(archive_path, extract_to)
        elif archive_type == 'rar':
            return _extract_rar(archive_path, extract_to)
        elif archive_type == '7z':
            return _extract_7z(archive_path, extract_to)
        else:
            return [], f"未知压缩类型: {archive_type}"
    except Exception as e:
        logger.error(f"解压失败: {e}")
        return [], str(e)


def _sanitize_path(name: str, base_dir: str) -> Optional[str]:
    """
    安全检查解压路径，防止路径穿越攻击
    
    Args:
        name: 压缩包内的文件名
        base_dir: 基础目录
        
    Returns:
        安全的完整路径，若不安全返回 None
    """
    # 跳过目录
    if name.endswith('/') or name.endswith('\\'):
        return None
    
    # 清理路径中的危险字符
    clean_name = name.replace('\\', '/')
    
    # 检查是否包含路径穿越
    if '..' in clean_name.split('/'):
        logger.warning(f"跳过可疑路径 (包含 ..): {name}")
        return None
    
    # 构建安全路径
    full_path = os.path.abspath(os.path.join(base_dir, clean_name))
    base_abs = os.path.abspath(base_dir)
    
    if not full_path.startswith(base_abs + os.sep) and full_path != base_abs:
        logger.warning(f"跳过可疑路径 (路径穿越): {name}")
        return None
    
    return full_path


def _extract_zip(archive_path: str, extract_to: str) -> Tuple[List[str], Optional[str]]:
    """
    解压 ZIP 文件
    """
    extracted_files = []
    
    with zipfile.ZipFile(archive_path, 'r') as zf:
        for info in zf.infolist():
            # 跳过目录
            if info.is_dir():
                continue
            
            # 安全检查
            safe_path = _sanitize_path(info.filename, extract_to)
            if safe_path is None:
                continue
            
            # 创建目录
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            
            # 解压文件
            with zf.open(info) as src, open(safe_path, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            
            extracted_files.append(safe_path)
    
    logger.info(f"ZIP 解压完成: {len(extracted_files)} 个文件")
    return extracted_files, None


def _extract_tar(archive_path: str, extract_to: str) -> Tuple[List[str], Optional[str]]:
    """
    解压 TAR 文件 (支持 .tar, .tar.gz, .tar.bz2, .tar.xz)
    """
    extracted_files = []
    
    # 自动检测压缩方式
    with tarfile.open(archive_path, 'r:*') as tf:
        for member in tf.getmembers():
            # 跳过目录
            if not member.isfile():
                continue
            
            # 安全检查
            safe_path = _sanitize_path(member.name, extract_to)
            if safe_path is None:
                continue
            
            # 创建目录
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            
            # 解压文件
            with tf.extractfile(member) as src:
                if src is not None:
                    with open(safe_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    extracted_files.append(safe_path)
    
    logger.info(f"TAR 解压完成: {len(extracted_files)} 个文件")
    return extracted_files, None


def _extract_rar(archive_path: str, extract_to: str) -> Tuple[List[str], Optional[str]]:
    """
    解压 RAR 文件
    需要安装 rarfile 库: pip install rarfile
    系统需要安装 unrar 命令行工具
    """
    try:
        import rarfile
    except ImportError:
        return [], "RAR 格式需要安装 rarfile 库: pip install rarfile\n另外系统需安装 unrar: sudo apt-get install unrar"
    
    extracted_files = []
    
    try:
        with rarfile.RarFile(archive_path, 'r') as rf:
            for info in rf.infolist():
                # 跳过目录
                if info.isdir():
                    continue
                
                # 安全检查
                safe_path = _sanitize_path(info.filename, extract_to)
                if safe_path is None:
                    continue
                
                # 创建目录
                os.makedirs(os.path.dirname(safe_path), exist_ok=True)
                
                # 解压文件
                with rf.open(info) as src, open(safe_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                
                extracted_files.append(safe_path)
        
        logger.info(f"RAR 解压完成: {len(extracted_files)} 个文件")
        return extracted_files, None
    except rarfile.RarCannotExec as e:
        return [], f"RAR 解压需要系统安装 unrar 命令: sudo apt-get install unrar\n错误: {e}"
    except Exception as e:
        return [], f"RAR 解压失败: {e}"


def _extract_7z(archive_path: str, extract_to: str) -> Tuple[List[str], Optional[str]]:
    """
    解压 7Z 文件
    需要安装 py7zr 库: pip install py7zr
    """
    try:
        import py7zr
    except ImportError:
        return [], "7Z 格式需要安装 py7zr 库: pip install py7zr"
    
    extracted_files = []
    
    try:
        with py7zr.SevenZipFile(archive_path, 'r') as sz:
            # py7zr 会自动提取所有文件
            sz.extractall(path=extract_to)
            
            # 找到所有解压出的文件
            for root, dirs, files in os.walk(extract_to):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    # 安全检查
                    rel_path = os.path.relpath(file_path, extract_to)
                    safe_path = _sanitize_path(rel_path, extract_to)
                    if safe_path and os.path.isfile(file_path):
                        extracted_files.append(file_path)
        
        logger.info(f"7Z 解压完成: {len(extracted_files)} 个文件")
        return extracted_files, None
    except Exception as e:
        return [], f"7Z 解压失败: {e}"


def filter_importable_files(extracted_files: List[str], supported_formats: dict) -> List[str]:
    """
    从解压文件中筛选出可导入的文件
    
    Args:
        extracted_files: 解压出的所有文件路径
        supported_formats: 支持的文件格式字典
        
    Returns:
        可导入的文件路径列表
    """
    importable = []
    
    for file_path in extracted_files:
        if not os.path.isfile(file_path):
            continue
        
        ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        if ext in supported_formats:
            importable.append(file_path)
    
    return importable


def get_archive_info(archive_path: str) -> Optional[dict]:
    """
    获取压缩包信息（不实际解压）
    
    Args:
        archive_path: 压缩包路径
        
    Returns:
        压缩包信息字典
    """
    archive_type = detect_archive_type(os.path.basename(archive_path))
    if archive_type is None:
        return None
    
    info = {
        'type': archive_type,
        'filename': os.path.basename(archive_path),
        'size': os.path.getsize(archive_path) if os.path.exists(archive_path) else 0,
        'file_count': 0,
    }
    
    try:
        if archive_type == 'zip':
            with zipfile.ZipFile(archive_path, 'r') as zf:
                info['file_count'] = len([f for f in zf.infolist() if not f.is_dir()])
        elif archive_type == 'tar':
            with tarfile.open(archive_path, 'r:*') as tf:
                info['file_count'] = len([m for m in tf.getmembers() if m.isfile()])
        elif archive_type == 'rar':
            try:
                import rarfile
                with rarfile.RarFile(archive_path, 'r') as rf:
                    info['file_count'] = len([f for f in rf.infolist() if not f.isdir()])
            except ImportError:
                info['file_count'] = -1  # 未知
        elif archive_type == '7z':
            try:
                import py7zr
                with py7zr.SevenZipFile(archive_path, 'r') as sz:
                    info['file_count'] = len(sz.getnames())
            except ImportError:
                info['file_count'] = -1  # 未知
    except Exception as e:
        info['error'] = str(e)
    
    return info
