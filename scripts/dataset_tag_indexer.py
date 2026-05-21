#!/usr/bin/env python3
"""
Platform 数据集 Tag 索引器 - 快速查找数据集

用法:
    python3 dataset_tag_indexer.py --build      # 构建/更新索引
    python3 dataset_tag_indexer.py --find 专项   # 查找指定 tag
    python3 dataset_tag_indexer.py --list-tags  # 列出所有 tags
"""

import subprocess
import json
import sys
import os
from pathlib import Path
from collections import defaultdict

INDEX_FILE = Path("/tmp/orbit_dataset_tag_index.json")


def get_orbit_path() -> str:
    """定位 Platform CLI 路径

    查找顺序:
    1. 脚本所在目录的兄弟 Platform/ (即 skills/Platform/)
    2. ~/.AI_Platform/skills/Platform/
    """
    # 基于脚本自身位置查找，避免 CWD 依赖
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)  # scripts/ -> project root

    candidates = [
        os.path.join(project_root, "skills", "Platform"),  # skills/Platform/ (or symlink)
        os.path.expanduser("~/.AI_Platform/skills/Platform"),
    ]

    for path in candidates:
        resolved = os.path.realpath(path)  # resolve symlinks
        if os.path.isfile(os.path.join(resolved, "Platform.mjs")):
            return resolved

    print("错误：无法找到 Platform CLI（已检查 skills/Platform/ 和 ~/.AI_Platform/skills/Platform/）")
    sys.exit(1)


def run_orbit_datasets(page=1):
    """运行 Platform datasets 命令"""
    token = os.environ.get('AuthGateway_ACCESS_TOKEN')
    if not token:
        print("错误: AuthGateway_ACCESS_TOKEN 环境变量未设置")
        sys.exit(1)

    try:
        result = subprocess.run(
            ['node', 'Platform.mjs', 'datasets', '--page', str(page)],
            capture_output=True, text=True, timeout=30,
            cwd=get_orbit_path(),
            env={**os.environ, 'AuthGateway_ACCESS_TOKEN': token}
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except Exception as e:
        print(f"请求错误: {e}")
        return None


def build_index():
    """构建完整的 tag 索引"""
    print("正在构建数据集 tag 索引...")

    tag_index = defaultdict(list)
    seen_ids = set()
    total_datasets = 0

    for page in range(1, 100):
        print(f"  获取第 {page} 页...", end='\r')

        data = run_orbit_datasets(page)
        if not data:
            break

        datasets = data.get('datasets', [])
        if not datasets:
            break

        for d in datasets:
            did = d.get('id')
            if did in seen_ids:
                continue
            seen_ids.add(did)
            total_datasets += 1

            dataset_info = {
                'name': d.get('name', ''),
                'id': did,
                'description': d.get('description', '')
            }

            # 关键：从 metadata.tags 提取
            metadata = d.get('metadata', {})
            if metadata:
                tags = metadata.get('tags', [])
                for tag in tags:
                    tag_index[tag].append(dataset_info)

        meta = data.get('meta', {})
        if page >= meta.get('totalPages', 1):
            break

    # 保存索引
    index_data = {
        'total_datasets': total_datasets,
        'tag_count': len(tag_index),
        'tags': dict(tag_index)
    }

    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)

    print("\n 索引构建完成！")
    print(f"   总数据集: {total_datasets}")
    print(f"   Tag 种类: {len(tag_index)}")
    print(f"   索引文件: {INDEX_FILE}")


def find_by_tag(tag):
    """根据 tag 查找数据集"""
    if not INDEX_FILE.exists():
        print("索引不存在，请先运行: python3 dataset_tag_indexer.py --build")
        sys.exit(1)

    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        index = json.load(f)

    tag_data = index.get('tags', {})

    if tag not in tag_data:
        print(f"没有找到 tag 为 '{tag}' 的数据集")
        return

    results = tag_data[tag]
    results.sort(key=lambda x: x.get('name', ''))

    print(f" 找到 {len(results)} 个 tag 为 '{tag}' 的数据集：\n")
    print(f"{'数据集名称':<45} {'ID':<30}")
    print("=" * 80)

    for d in results:
        name = d.get('name', 'N/A')[:42]
        did = d.get('id', 'N/A')[:27]
        print(f"{name:<45} {did:<30}")

    print("=" * 80)
    print(f"\n总计: {len(results)} 个数据集")


def list_tags():
    """列出所有可用的 tags"""
    if not INDEX_FILE.exists():
        print("索引不存在，请先运行: python3 dataset_tag_indexer.py --build")
        sys.exit(1)

    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        index = json.load(f)

    tag_data = index.get('tags', {})

    print(f"总共有 {len(tag_data)} 个不同的 tags：\n")
    print(f"{'Tag':<25} {'数据集数量':<15}")
    print("=" * 45)

    sorted_tags = sorted(tag_data.items(), key=lambda x: len(x[1]), reverse=True)

    for tag, datasets in sorted_tags:
        print(f"{tag:<25} {len(datasets):<15}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Platform 数据集 Tag 索引工具")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true", help="构建/更新索引")
    group.add_argument("--find", metavar="TAG", help="查找指定 tag 的数据集")
    group.add_argument("--list-tags", action="store_true", help="列出所有 tags")
    args = parser.parse_args()

    if args.build:
        build_index()
    elif args.find:
        find_by_tag(args.find)
    elif args.list_tags:
        list_tags()


if __name__ == '__main__':
    main()
