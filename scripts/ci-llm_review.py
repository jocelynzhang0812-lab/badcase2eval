#!/usr/bin/env python3
"""ci-llm_review.py  用 LLM 检查 MR diff 中是否存在内容矛盾或冲突。

在 CI 中对 MR 的变更内容做智能审查：
- 新增内容是否与已有文档/代码矛盾
- 同一 MR 内不同文件的改动是否互相冲突
- 文档中的说明是否与代码实现不一致

v2 改进：除了 diff，还会读取变更文件的完整内容 + 被引用文件的内容，
       避免 LLM 因上下文不足而产生误报。

用法：
  # CI 中（自动取 MR diff）
  python scripts/ci-llm_review.py

  # 本地测试（指定 diff 文件）
  git diff main...HEAD > /tmp/diff.patch
  python scripts/ci-llm_review.py --diff /tmp/diff.patch

  # 只检查特定文件类型
  python scripts/ci-llm_review.py --include "*.md" --include "*.py"

环境变量：
  LLM_REVIEW_BASE_URL  LLM API 地址（默认内部直连 gpt-oss-120b-judge，无需 key）
  OPENAI_API_KEY  API Key（内部直连时不需要，走Internal_AI_Service时需要）
  CI_MERGE_REQUEST_DIFF_BASE_SHA  GitLab CI 自动设置
  CI_COMMIT_SHA  GitLab CI 自动设置
  CI_PROJECT_ID  GitLab CI 自动设置（发评论用）
  CI_MERGE_REQUEST_IID  GitLab CI 自动设置（发评论用）
  CI_JOB_TOKEN  GitLab CI 自动设置（发评论用）
  GITLAB_TOKEN  可选，自定义 token（优先于 CI_JOB_TOKEN）
"""

import argparse
import os
import re
import subprocess
import sys
import urllib.request
import json as _json

# ---------------------------------------------------------------------------
# LLM 调用（兼容Internal_AI_Service / OpenAI）
# ---------------------------------------------------------------------------

# 内部部署模型直连地址，无需 API Key
DEFAULT_BASE_URL = "https://gpt-oss-120b-judge.app.internal.company.com/v1"
DEFAULT_MODEL = "gpt-oss-120b-judge"


def call_llm(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL) -> str:
    """调用 LLM API，返回回复文本。"""
    try:
        from openai import OpenAI
    except ImportError:
        print(" 需要安装 openai: pip install openai", file=sys.stderr)
        sys.exit(1)

    # 优先用环境变量覆盖，否则走内部直连（无需 key）
    base_url = os.environ.get("LLM_REVIEW_BASE_URL", DEFAULT_BASE_URL)
    api_key = os.environ.get("OPENAI_API_KEY", "not-needed")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    msg = resp.choices[0].message
    # gpt-oss-120b-judge 用 reasoning_content 返回，兼容两种格式
    return msg.content or getattr(msg, 'reasoning_content', None) or ""


# ---------------------------------------------------------------------------
# Diff 获取
# ---------------------------------------------------------------------------

def get_diff_from_ci() -> str:
    """从 GitLab CI 环境变量获取 MR diff。"""
    base_sha = os.environ.get("CI_MERGE_REQUEST_DIFF_BASE_SHA")
    head_sha = os.environ.get("CI_COMMIT_SHA")

    if base_sha and head_sha:
        result = subprocess.run(
            ["git", "diff", f"{base_sha}...{head_sha}"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout

    # fallback: diff with origin/master
    subprocess.run(["git", "fetch", "origin", "master"], capture_output=True, timeout=30)
    result = subprocess.run(
        ["git", "diff", "origin/master...HEAD"],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout


def get_diff(diff_file: str | None = None) -> str:
    """获取 diff 内容。"""
    if diff_file:
        with open(diff_file) as f:
            return f.read()
    return get_diff_from_ci()


# ---------------------------------------------------------------------------
# Diff 过滤和截断
# ---------------------------------------------------------------------------

def extract_changed_files(diff: str) -> list[str]:
    """从 diff 中提取变更文件列表。"""
    files = []
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 4:
                filepath = parts[-1].lstrip("b/")
                files.append(filepath)
    return files


def filter_diff(diff: str, includes: list[str] | None = None) -> str:
    """按文件类型过滤 diff。"""
    if not includes:
        return diff

    import fnmatch
    filtered_chunks = []
    current_chunk = []
    current_file = None

    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git"):
            if current_chunk and current_file:
                if any(fnmatch.fnmatch(current_file, pat) for pat in includes):
                    filtered_chunks.extend(current_chunk)
            current_chunk = [line]
            parts = line.split()
            current_file = parts[-1].lstrip("b/") if len(parts) >= 4 else None
        else:
            current_chunk.append(line)

    if current_chunk and current_file:
        if any(fnmatch.fnmatch(current_file, pat) for pat in includes):
            filtered_chunks.extend(current_chunk)

    return "".join(filtered_chunks)


def truncate_text(text: str, max_chars: int, label: str = "内容") -> str:
    """截断过长的文本，保留头尾。"""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return (
        text[:half]
        + f"\n\n... [截断: {label}共 {len(text)} 字符，超过 {max_chars} 限制] ...\n\n"
        + text[-half:]
    )


# ---------------------------------------------------------------------------
# 文件上下文收集（v2 新增）
# ---------------------------------------------------------------------------

def read_file_at_head(filepath: str) -> str | None:
    """读取 HEAD 版本的文件内容。"""
    result = subprocess.run(
        ["git", "show", f"HEAD:{filepath}"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        return result.stdout
    return None


def extract_md_links(content: str, source_file: str) -> list[str]:
    """从 Markdown 内容中提取相对链接的文件路径。"""
    # 匹配 [text](relative/path.md) 和 [text](../path.md) 等
    link_pattern = re.compile(r'\[(?:[^\]]*)\]\(([^)]+)\)')
    links = []
    source_dir = os.path.dirname(source_file)

    for match in link_pattern.finditer(content):
        target = match.group(1)
        # 跳过 URL、锚点、图片等
        if target.startswith(('http://', 'https://', '#', 'mailto:')):
            continue
        # 去掉锚点部分
        target = target.split('#')[0]
        if not target:
            continue
        # 解析相对路径
        resolved = os.path.normpath(os.path.join(source_dir, target))
        if not resolved.startswith('..'):  # 不超出仓库根目录
            links.append(resolved)
    return links


def collect_file_context(
    diff: str,
    changed_files: list[str],
    max_total_chars: int = 80000,
) -> str:
    """收集变更文件的完整内容 + 被引用的关键文件。

    策略：
    1. 读取所有变更文件的 HEAD 版本（修改后的完整内容）
    2. 从变更文件中提取 Markdown 链接，读取被引用的文件
    3. 总字符数超限时优先保留变更文件，裁剪引用文件
    """
    sections = []
    used_chars = 0
    seen_files = set()

    # 第一优先级：变更文件的完整内容
    changed_contents = {}
    for filepath in changed_files:
        content = read_file_at_head(filepath)
        if content and filepath not in seen_files:
            changed_contents[filepath] = content
            seen_files.add(filepath)

    # 第二优先级：变更文件中引用的其他文件
    referenced_files = []
    for filepath, content in changed_contents.items():
        if filepath.endswith('.md'):
            links = extract_md_links(content, filepath)
            for link in links:
                if link not in seen_files and os.path.splitext(link)[1] in (
                    '.md', '.py', '.mjs', '.js', '.yml', '.yaml'
                ):
                    referenced_files.append(link)
                    seen_files.add(link)

    # 组装变更文件内容
    for filepath, content in changed_contents.items():
        budget = max_total_chars - used_chars
        if budget <= 0:
            break
        truncated = truncate_text(content, min(budget, 15000), filepath)
        section = f"###  {filepath}（变更文件，完整内容）\n```\n{truncated}\n```\n"
        sections.append(section)
        used_chars += len(section)

    # 组装引用文件内容（预算允许时）
    for filepath in referenced_files:
        budget = max_total_chars - used_chars
        if budget <= 2000:  # 剩余空间太小就停止
            break
        content = read_file_at_head(filepath)
        if not content:
            continue
        truncated = truncate_text(content, min(budget, 8000), filepath)
        section = f"###  {filepath}（被引用文件）\n```\n{truncated}\n```\n"
        sections.append(section)
        used_chars += len(section)

    if not sections:
        return ""

    return (
        "## 文件完整内容（用于交叉验证）\n\n"
        "以下是变更文件修改后的完整内容，以及它们引用的相关文件。\n"
        "**判断矛盾时请以这些完整内容为准，而非仅凭 diff 片段推测。**\n\n"
        + "\n".join(sections)
    )


# ---------------------------------------------------------------------------
# 仓库文件存在性检查（v2 新增）
# ---------------------------------------------------------------------------

def check_file_exists(filepath: str) -> bool:
    """检查文件在 HEAD 中是否存在。"""
    result = subprocess.run(
        ["git", "cat-file", "-t", f"HEAD:{filepath}"],
        capture_output=True, text=True, timeout=5
    )
    return result.returncode == 0


def build_file_tree(changed_files: list[str]) -> str:
    """生成仓库文件树摘要，帮助 LLM 了解哪些文件存在。"""
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        return ""

    all_files = result.stdout.strip().splitlines()
    # 只列出与变更文件同目录的文件 + 根目录文件
    relevant_dirs = {os.path.dirname(f) for f in changed_files}
    relevant_dirs.add("")  # 根目录

    tree_lines = []
    for f in sorted(all_files):
        fdir = os.path.dirname(f)
        if fdir in relevant_dirs:
            tree_lines.append(f)

    if not tree_lines:
        return ""

    return (
        "## 仓库文件列表（变更相关目录）\n\n"
        "以下文件在仓库中**确实存在**，未列出的文件**不存在**：\n\n```\n"
        + "\n".join(tree_lines)
        + "\n```\n"
    )


# ---------------------------------------------------------------------------
# 审查逻辑
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
你是一个代码和文档审查专家。你的任务是审查一个 MR (Merge Request) 的变更，检查以下问题：

1. **内容矛盾**：新增/修改的内容是否与同一仓库中已有的内容矛盾（例如文档 A 说用方法 X，文档 B 说用方法 Y）
2. **文档与代码不一致**：文档描述的接口、参数、用法是否与实际代码实现一致
3. **同一 MR 内冲突**：不同文件的改动是否互相矛盾（例如一个文件新增了参数，另一个文件删除了同一参数）
4. **遗漏更新**：改了代码但没更新相关文档，或改了文档但引用的代码路径/函数名已失效

## 重要：避免误报

你会收到三部分信息：
- **Diff**：本次变更的 diff
- **文件完整内容**：变更文件修改后的完整内容 + 被引用文件的内容
- **仓库文件列表**：确认哪些文件存在、哪些不存在

**审查纪律（必须严格遵守）：**
-  只报告你能从提供的完整文件内容中**明确验证**的问题
-  不要基于 diff 片段**推测**未提供文件的内容
-  不要报告"文件 X 可能还引用了 Y"要么你看到了完整内容能确认，要么就不报
-  不要报告文件不存在的问题请查看仓库文件列表确认
-  不要报告代码风格、格式问题（那是 linter 的工作）
-  不要报告正常的代码重构（旧代码被删除、新代码替代）
-  不要把"信息在不同文件中以不同粒度描述"当作矛盾只有**逻辑上互斥**才算矛盾
- 如果没有发现**确凿的**问题，直接说"未发现矛盾或冲突"。宁可漏报也不要误报。

用中文回复。

输出格式：
```
## 审查结果

### 发现的问题
| 文件 | 行号范围 | 问题描述 | 建议修复 |
|------|----------|----------|----------|
（逐条列出，每条必须注明你是从哪个完整文件中验证到这个矛盾的）

### 总结
（一句话总结：有/无矛盾冲突）
```"""


def review_diff(diff: str, file_context: str, file_tree: str) -> tuple[str, bool]:
    """
    审查 diff + 文件上下文，返回 (审查结果文本, 是否通过)。
    """
    user_parts = [f"## Diff\n\n```diff\n{diff}\n```"]
    if file_context:
        user_parts.append(file_context)
    if file_tree:
        user_parts.append(file_tree)

    user_prompt = "请审查以下 MR 变更：\n\n" + "\n\n---\n\n".join(user_parts)

    result = call_llm(SYSTEM_PROMPT, user_prompt)

    # 判断是否通过：没有发现问题 = 通过
    passed = any(keyword in result for keyword in [
        "未发现矛盾",
        "未发现冲突",
        "没有发现矛盾",
        "没有发现冲突",
        "无矛盾冲突",
        "无矛盾或冲突",
        "未发现明显的矛盾",
        "未发现明显的冲突",
        "未发现确凿的",
        "未发现确凿问题",
    ])

    return result, passed


# ---------------------------------------------------------------------------
# 发 MR 评论
# ---------------------------------------------------------------------------

def post_mr_comment(body: str) -> bool:
    """将审查结果发到 MR 评论区。返回是否成功。"""
    project_id = os.environ.get("CI_PROJECT_ID")
    mr_iid = os.environ.get("CI_MERGE_REQUEST_IID")
    gitlab_url = os.environ.get("CI_SERVER_URL", "https://internal.company.com")
    token = os.environ.get("GITLAB_TOKEN") or os.environ.get("CI_JOB_TOKEN")

    if not project_id or not mr_iid:
        print("ℹ️  非 MR 环境，跳过发评论")
        return False
    if not token:
        print("️  没有可用的 token，无法发 MR 评论")
        return False

    url = f"{gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes"
    data = _json.dumps({"body": body}).encode()

    # 优先用 GITLAB_TOKEN (Private-Token)，否则用 CI_JOB_TOKEN (Job-Token)
    if os.environ.get("GITLAB_TOKEN"):
        headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
    else:
        headers = {"JOB-TOKEN": token, "Content-Type": "application/json"}

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 201):
                print(f" 审查结果已发到 MR !{mr_iid} 评论区")
                return True
    except Exception as e:
        print(f"️  发 MR 评论失败: {e}")
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="用 LLM 检查 MR diff 中的内容矛盾和冲突"
    )
    parser.add_argument("--diff", default=None, help="diff 文件路径（默认从 CI 环境获取）")
    parser.add_argument("--include", action="append", help="只检查匹配的文件（如 *.md *.py），可多次指定")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM 模型名称")
    parser.add_argument("--max-diff-chars", type=int, default=60000, help="diff 最大字符数")
    parser.add_argument("--max-context-chars", type=int, default=80000, help="文件上下文最大字符数")
    parser.add_argument("--no-context", action="store_true", help="禁用文件上下文收集（回退到 v1 行为）")
    parser.add_argument("--strict", action="store_true", help="严格模式：发现问题时 exit 1")
    parser.add_argument("--no-comment", action="store_true", help="不发 MR 评论，只输出到日志")
    args = parser.parse_args()

    # 获取 diff
    diff = get_diff(args.diff)
    if not diff.strip():
        print(" 没有 diff 内容，跳过 LLM 审查")
        return

    # 过滤
    diff = filter_diff(diff, args.include)
    if not diff.strip():
        print(" 过滤后没有匹配的文件变更，跳过 LLM 审查")
        return

    # 提取变更文件列表
    changed_files = extract_changed_files(diff)
    print(f" 变更文件 ({len(changed_files)})：{', '.join(changed_files)}")

    # 截断 diff
    diff = truncate_text(diff, args.max_diff_chars, "diff")

    # 收集文件上下文（v2）
    file_context = ""
    file_tree = ""
    if not args.no_context:
        print(" 正在收集文件完整内容...")
        file_context = collect_file_context(diff, changed_files, args.max_context_chars)
        file_tree = build_file_tree(changed_files)
        ctx_chars = len(file_context) + len(file_tree)
        print(f"   文件上下文: {ctx_chars} 字符")

    total_chars = len(diff) + len(file_context) + len(file_tree)
    print(f" 正在用 LLM ({args.model}) 审查（总计 {total_chars} 字符）...")
    print()

    # 审查
    result, passed = review_diff(diff, file_context, file_tree)
    print(result)

    if passed:
        print("\n LLM 审查通过：未发现内容矛盾或冲突")
    else:
        print("\n️  LLM 发现了潜在问题，请人工确认")

    # 发 MR 评论
    if not args.no_comment:
        status = " 通过" if passed else "️ 发现潜在问题"
        comment = f" **LLM Review** ({status})\n\n{result}"
        post_mr_comment(comment)

    if not passed and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
