#!/usr/bin/env python3
"""
知识库系统 - 日志清理与维护脚本
================================
功能:
  1. 清理超过配额的旧日志
  2. 压缩归档旧日志
  3. 显示日志目录统计信息

使用方法:
  python scripts/clean_logs.py              # 显示统计
  python scripts/clean_logs.py --clean      # 执行清理
  python scripts/clean_logs.py --clean --dry-run  # 预览清理效果
  python scripts/clean_logs.py --size 1G    # 指定配额
"""

import os
import sys
import time
import gzip
import shutil
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# 项目根目录
PROJECT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_DIR / "data" / "logs"

# 默认配置
DEFAULT_MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
DEFAULT_RETENTION_DAYS = 30  # 默认保留天数
DRY_RUN = False


def human_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def get_dir_size(path: Path) -> int:
    """计算目录总大小"""
    total = 0
    for f in path.rglob('*'):
        if f.is_file():
            total += f.stat().st_size
    return total


def get_log_stats():
    """获取日志统计信息"""
    if not LOG_DIR.exists():
        print(f"日志目录不存在: {LOG_DIR}")
        return

    print(f"\n{'='*60}")
    print(f"  日志目录统计: {LOG_DIR}")
    print(f"{'='*60}")

    total_size = 0
    file_count = 0
    log_files = []

    for f in sorted(LOG_DIR.iterdir()):
        if f.is_file():
            size = f.stat().st_size
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            total_size += size
            file_count += 1
            log_files.append((f, size, mtime))

            age_days = (datetime.now() - mtime).days
            flag = " 🆕" if age_days < 1 else ""
            if age_days > DEFAULT_RETENTION_DAYS:
                flag = " ⚠"

            print(f"  {f.name:<40} {human_size(size):>10}  {age_days:>3d}天前  {mtime.strftime('%Y-%m-%d %H:%M')}{flag}")

    print(f"{'='*60}")
    print(f"  文件总数: {file_count}")
    print(f"  总大小:   {human_size(total_size)}")
    print(f"  配额限制: {human_size(DEFAULT_MAX_SIZE)}")
    print(f"  使用率:   {total_size / DEFAULT_MAX_SIZE * 100:.1f}%")
    print(f"{'='*60}\n")

    return log_files


def compress_old_logs(log_files: list, max_age_days: int = 7):
    """压缩旧日志文件"""
    compressed = 0
    for f, size, mtime in log_files:
        age_days = (datetime.now() - mtime).days
        if age_days > max_age_days and not f.name.endswith('.gz') and not f.name.endswith('.log'):
            continue
        if f.suffix == '.log' and age_days > max_age_days:
            gz_path = f.with_suffix('.log.gz')
            if DRY_RUN:
                print(f"  [DRY] 压缩: {f.name} -> {gz_path.name}")
            else:
                with open(f, 'rb') as f_in:
                    with gzip.open(gz_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                f.unlink()
                print(f"  [压缩] {f.name} -> {gz_path.name} ({human_size(size)})")
            compressed += 1

    if compressed:
        print(f"\n  压缩完成: {compressed} 个文件\n")


def cleanup_old_logs(max_size: int = DEFAULT_MAX_SIZE, target_ratio: float = 0.7):
    """清理超过配额的日志文件"""
    log_files = get_log_stats()
    if not log_files:
        return

    total_size = sum(size for _, size, _ in log_files)

    if total_size <= max_size:
        print(f"✅ 日志大小 {human_size(total_size)} 在配额 {human_size(max_size)} 内，无需清理")
        return

    target_size = int(max_size * target_ratio)
    need_to_free = total_size - target_size

    print(f"\n⚠ 日志超出配额!")
    print(f"  当前大小: {human_size(total_size)}")
    print(f"  超出:     {human_size(need_to_free)}")
    print(f"  目标大小: {human_size(target_size)}")
    print()

    # 按修改时间排序 (最旧的在前)
    log_files.sort(key=lambda x: x[2])

    freed = 0
    deleted = 0

    for f, size, mtime in log_files:
        if freed >= need_to_free:
            break

        age_days = (datetime.now() - mtime).days

        if DRY_RUN:
            print(f"  [DRY] 将删除: {f.name} ({human_size(size)}, {age_days}天前)")
        else:
            try:
                f.unlink()
                freed += size
                deleted += 1
                print(f"  [删除] {f.name} ({human_size(size)}, {age_days}天前)")
            except OSError as e:
                print(f"  [错误] 删除失败 {f.name}: {e}")

    if DRY_RUN:
        print(f"\n  [DRY-RUN] 将释放 {human_size(freed)}, 将删除 {deleted} 个文件")
    else:
        print(f"\n✅ 清理完成: 释放 {human_size(freed)}, 删除 {deleted} 个文件")

    # 显示清理后的状态
    remaining_files = list(LOG_DIR.iterdir()) if LOG_DIR.exists() else []
    remaining_size = sum(f.stat().st_size for f in remaining_files if f.is_file())
    print(f"  剩余文件数: {len(remaining_files)}")
    print(f"  剩余大小:   {human_size(remaining_size)}")


def main():
    parser = argparse.ArgumentParser(
        description='知识库日志清理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  %(prog)s                     # 显示日志统计
  %(prog)s --clean             # 清理超出配额的日志
  %(prog)s --clean --dry-run   # 预览清理效果
  %(prog)s --clean --size 1G   # 指定配额为 1GB
        '''
    )
    parser.add_argument('--clean', action='store_true', help='执行清理')
    parser.add_argument('--compress', action='store_true', help='压缩旧日志')
    parser.add_argument('--dry-run', action='store_true', help='预览模式')
    parser.add_argument('--size', type=str, default=None, help='配额大小 (如 500M, 1G, 2G)')

    args = parser.parse_args()
    global DRY_RUN, DEFAULT_MAX_SIZE

    DRY_RUN = args.dry_run

    if args.size:
        # 解析大小字符串
        size_str = args.size.upper()
        multipliers = {'B': 1, 'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
        for suffix, mult in multipliers.items():
            if size_str.endswith(suffix):
                DEFAULT_MAX_SIZE = int(float(size_str[:-1]) * mult)
                break
        else:
            DEFAULT_MAX_SIZE = int(float(size_str))

    # 创建日志目录
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if args.clean or args.compress:
        log_files = get_log_stats()
        if args.compress and log_files:
            print("\n" + "="*60)
            print("  压缩旧日志 (>7天)")
            print("="*60)
            compress_old_logs(log_files, max_age_days=7)

        if args.clean:
            cleanup_old_logs(max_size=DEFAULT_MAX_SIZE)
    else:
        get_log_stats()


if __name__ == '__main__':
    main()
