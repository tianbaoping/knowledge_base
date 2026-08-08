import os
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="下载嵌入模型到本地")
    parser.add_argument(
        "--model",
        default="BAAI/bge-small-zh-v1.5",
        help="模型名称 (默认: BAAI/bge-small-zh-v1.5)",
    )
    parser.add_argument(
        "--save-dir",
        default=None,
        help="保存目录 (默认: 项目根目录/models/)",
    )
    args = parser.parse_args()

    if args.save_dir:
        save_path = args.save_dir
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        save_path = os.path.join(base_dir, "models", args.model.replace("/", "_"))

    print(f"模型名称: {args.model}")
    print(f"保存路径: {save_path}")
    print()

    try:
        os.environ.setdefault("HF_HUB_OFFLINE", "0")
        from sentence_transformers import SentenceTransformer

        print("正在下载模型...")
        model = SentenceTransformer(args.model, trust_remote_code=True)

        os.makedirs(save_path, exist_ok=True)
        model.save(save_path)

        file_count = len(os.listdir(save_path))
        print(f"\n✓ 模型下载成功!")
        print(f"  路径: {save_path}")
        print(f"  文件数: {file_count}")

        print(f"\n{'='*50}")
        print(f"使用方法:")
        print(f"  方式1: 设置环境变量后启动")
        print(f"    Windows:")
        print(f"      $env:MODEL_LOCAL_PATH = '{save_path}'")
        print(f"      python -m app.main")
        print(f"    Linux/macOS:")
        print(f"      export MODEL_LOCAL_PATH='{save_path}'")
        print(f"      python -m app.main")
        print(f"\n  方式2: 修改 app/config.py 中的 MODEL_LOCAL_PATH")
        print(f"    MODEL_LOCAL_PATH = '{save_path}'")
        print(f"{'='*50}")

    except Exception as e:
        print(f"\n✗ 模型下载失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()