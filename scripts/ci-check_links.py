#!/usr/bin/env python3
"""ci-check_links.py  检查 Markdown 文件中的内部链接是否有效。

扫描所有 .md 文件中的相对链接 [text](path)，验证目标文件是否存在。
不检查外部 URL（http/https），只检查本地相对路径。

用法：
  python scripts/ci-check_links.py                    # 检查整个项目
  python scripts/ci-check_links.py references/ SKILL.md  # 只检查指定路径
"""

import re
import sys
from pathlib import Path

LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
# 忽略的链接模式
IGNORE_PREFIXES = ('http://', 'https://', 'mailto:', '#', '{{')
# 忽略的示例/占位链接
IGNORE_EXACT = {'URL', 'file.png', 'path', 'example.md', 'your-file.md'}


def find_md_files(paths: list[str]) -> list[Path]:
    """找到所有 .md 文件。"""
    result = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix == '.md':
            result.append(path)
        elif path.is_dir():
            result.extend(path.rglob('*.md'))
    return sorted(set(result))


def check_file(md_file: Path) -> list[tuple[int, str, str]]:
    """检查单个 md 文件中的内部链接，返回 (行号, 链接, 原因) 列表。"""
    broken = []
    try:
        lines = md_file.read_text(encoding='utf-8').splitlines()
    except Exception:
        return broken

    base_dir = md_file.parent

    for line_no, line in enumerate(lines, 1):
        for match in LINK_PATTERN.finditer(line):
            link = match.group(2).strip()

            # 跳过外部链接、锚点、模板变量
            if any(link.startswith(prefix) for prefix in IGNORE_PREFIXES):
                continue

            # 跳过文档中的示例/占位链接
            if link in IGNORE_EXACT:
                continue

            # 去掉锚点部分 file.md#section -> file.md
            clean_link = link.split('#')[0]
            if not clean_link:
                continue  # 纯锚点链接 (#section)

            target = base_dir / clean_link
            if not target.exists():
                broken.append((line_no, link, "文件不存在"))

    return broken


def main():
    paths = sys.argv[1:] if len(sys.argv) > 1 else ['.']
    md_files = find_md_files(paths)

    if not md_files:
        print("未找到 .md 文件")
        return

    total_links = 0
    total_broken = 0
    all_broken = []

    for md_file in md_files:
        broken = check_file(md_file)
        if broken:
            all_broken.append((md_file, broken))
            total_broken += len(broken)

    # 统计总链接数
    for md_file in md_files:
        try:
            content = md_file.read_text(encoding='utf-8')
            for match in LINK_PATTERN.finditer(content):
                link = match.group(2).strip()
                if not any(link.startswith(p) for p in IGNORE_PREFIXES):
                    clean = link.split('#')[0]
                    if clean:
                        total_links += 1
        except Exception:
            pass

    # 输出结果
    if all_broken:
        print(f" 发现 {total_broken} 个坏链接（共检查 {total_links} 个内部链接，{len(md_files)} 个文件）\n")
        for md_file, broken in all_broken:
            print(f" {md_file}")
            for line_no, link, reason in broken:
                print(f"   L{line_no}: [{link}]  {reason}")
            print()
        sys.exit(1)
    else:
        print(f" 所有内部链接有效（{total_links} 个链接，{len(md_files)} 个文件）")


if __name__ == "__main__":
    main()
