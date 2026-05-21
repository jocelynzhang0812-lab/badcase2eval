#!/usr/bin/env python3
"""
run_eval.py  交互式评测全流程（使用 Platform CLI）

从数据准备到跑评测到拿结果，一条命令行搞定。
所有 Platform 操作通过 Platform CLI (node Platform.mjs) 执行，不直接调 REST API。

用法:
    # 交互模式
    python scripts/run_eval.py

    # 参数模式（Agent 调用）
    python scripts/run_eval.py \
        --file dataset.jsonl \
        --dataset-name "search-v1" \
        --input-fields query,rubric \
        --preset kimi_chat \
        --auto-judge \
        -y

环境变量:
    AuthGateway_ACCESS_TOKEN  Platform 认证
    ORBIT_CLI_PATH  Platform.mjs 路径（自动搜索 skills/Platform/Platform.mjs）
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------- Platform CLI ----------

def find_orbit_cli() -> str:
    """查找 Platform.mjs 路径"""
    # 1. 环境变量
    env_path = os.environ.get("ORBIT_CLI_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    # 2. 常见路径搜索
    candidates = [
        Path(__file__).parent.parent / "skills" / "Platform" / "Platform.mjs",  # 相对于 scripts/
        Path.home() / ".AI_Platform" / "skills" / "Platform" / "Platform.mjs",
        Path.home() / ".kitty" / "workers",  # 搜索 kitty workers
    ]

    for c in candidates:
        if c.is_file():
            return str(c)
        if c.is_dir():
            # 搜索子目录
            for p in c.rglob("Platform.mjs"):
                return str(p)

    print(" 找不到 Platform.mjs，请设置 ORBIT_CLI_PATH 环境变量")
    sys.exit(1)


ORBIT_CLI = None  # 延迟初始化


def Platform(cmd: str, *args, capture=True, check=True) -> dict | str:
    """调用 Platform CLI，返回 JSON 或文本"""
    global ORBIT_CLI
    if ORBIT_CLI is None:
        ORBIT_CLI = find_orbit_cli()

    orbit_dir = str(Path(ORBIT_CLI).parent)
    full_cmd = ["node", ORBIT_CLI, cmd] + list(args)

    result = subprocess.run(
        full_cmd,
        capture_output=capture,
        text=True,
        cwd=orbit_dir,
        timeout=300,
    )

    if check and result.returncode != 0:
        stderr = result.stderr[:500] if result.stderr else ""
        print(f"️ Platform {cmd} 失败: {stderr}")

    output = result.stdout.strip()
    if not output:
        return {}

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output


# ---------- 交互工具 ----------

def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        print("\n️ 已取消")
        sys.exit(0)


def ask_choice(prompt: str, options: list[str], default: int = 1) -> int:
    print(prompt)
    for i, opt in enumerate(options, 1):
        marker = "→" if i == default else " "
        print(f"  {marker} [{i}] {opt}")
    val = ask("选择", str(default))
    try:
        idx = int(val)
        if 1 <= idx <= len(options):
            return idx
    except ValueError:
        pass
    return default


def ask_yn(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    val = ask(f"{prompt} {suffix}").lower()
    if not val:
        return default
    return val in ("y", "yes")


# ---------- Step 0: AKSK 预检 ----------

AKSK_CHECK_URL = os.environ.get("ORBIT_API_BASE", "https://platform.internal.ai.com") + "/api/aksk"

EXPECTED_AKSK_KEYS = [
    ("OPENAI_API_KEY",        "Internal_AI_Service API key（跑模型用）",               True),
    ("ANTHROPIC_API_KEY",     "Internal_AI_Service API key（kimi_chat/kimi_agent 必需）",  True),
    ("AuthGateway_ACCESS_TOKEN", "Platform 认证 token",                       True),
    ("SEARCH_TOKEN",          "搜索 token（搜索评测用）",               False),
    ("DATASOURCE_KEY",        "数据源 key（数据源评测用）",             False),
]


def fetch_orbit_aksk_keys() -> set[str]:
    """Fetch existing AKSK key names from Platform API."""
    import urllib.request
    import urllib.error
    token = os.environ.get("AuthGateway_ACCESS_TOKEN", "")
    req = urllib.request.Request(
        AKSK_CHECK_URL,
        headers={"X-AuthGateway-Access-Token": token},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        items = data if isinstance(data, list) else data.get("items", [])
        return {item.get("key", "") for item in items if item.get("key")}
    except Exception as e:
        print(f"  ️  无法获取 AKSK 列表: {e}")
        return set()


def step_check_aksk(args) -> bool:
    """检查 Platform AKSK 配置是否完整。返回 True 表示可以继续。"""
    print(" Step 0: 检查 AKSK 配置...")
    existing = fetch_orbit_aksk_keys()
    if not existing:
        print("  ️  无法读取 Platform AKSK，跳过检查")
        return True

    missing_required = []
    missing_optional = []

    for key_name, desc, required in EXPECTED_AKSK_KEYS:
        if key_name in existing:
            print(f"   {key_name}")
        elif required:
            print(f"   {key_name}  {desc}")
            missing_required.append(key_name)
        else:
            print(f"  ️  {key_name}  {desc}（可选）")
            missing_optional.append(key_name)

    if missing_required:
        print(f"\n   缺少 {len(missing_required)} 个必需的 key: {', '.join(missing_required)}")
        print("   配置方法:")
        print("     1. 填入 .env 文件后运行: python scripts/rollout-setup_aksk.py")
        print("     2. 或在 Internal Evaluation Platform手动添加: https://platform.internal.ai.com/settings/aksk")
        print("     3. Key 获取方式见 README.md\n")
        if not args.yes and not ask_yn("继续执行？（可能导致运行失败）", default=False):
            return False
    elif missing_optional:
        print(f"\n   {len(missing_optional)} 个可选 key 未配置（部分评测场景需要）")
    else:
        print("\n   所有 AKSK 已配置")

    print()
    return True


# ---------- Step 1: 数据来源 ----------

def step_data_source(args) -> str:
    """获取数据文件路径"""
    if args.file:
        print(f" 数据文件: {args.file}")
        return args.file

    choice = ask_choice("\n Step 1: 数据来源", [
        "本地 CSV/JSONL 文件",
        "已有 Platform Dataset（跳过上传）",
    ])

    if choice == 1:
        return ask("文件路径")
    else:
        args.skip_upload = True
        args.dataset_name = ask("Dataset 名称")
        return None


# ---------- Step 2: 上传 ----------

def step_upload(file_path: str, args) -> str:
    """用 Platform CLI 上传数据集"""
    if getattr(args, "skip_upload", False):
        return args.dataset_name

    dataset_name = args.dataset_name or ask(
        "\n Step 2: Dataset 名称",
        f"eval-{datetime.now().strftime('%m%d-%H%M')}"
    )

    # 构建 upload 命令
    upload_args = [file_path, "--dataset", dataset_name]

    if args.field_mapping:
        upload_args += ["--field-mapping", args.field_mapping]
    elif args.input_fields:
        # 自动构建 field-mapping JSON
        input_fields = [f.strip() for f in args.input_fields.split(",")]
        metadata_fields = [f.strip() for f in args.metadata_fields.split(",")] if args.metadata_fields else []
        mapping = {"inputFields": input_fields}
        if metadata_fields:
            mapping["metadataFields"] = metadata_fields
        upload_args += ["--field-mapping", json.dumps(mapping)]

    # Dry-run
    print(f"\n 上传 Dataset: {dataset_name}")
    dry = Platform("upload", *upload_args, "--dry-run")
    if isinstance(dry, dict):
        items = dry.get("items", dry.get("itemCount", "?"))
        print(f"  预览: {items} 条数据")

    if not args.yes and not ask_yn("确认上传？"):
        print("️ 已取消")
        sys.exit(0)

    # 正式上传
    result = Platform("upload", *upload_args)
    if isinstance(result, dict) and result.get("success"):
        print(f"   上传成功: {result.get('itemCount', '?')} 条")
    else:
        print(f"  结果: {result}")

    return dataset_name


# ---------- Step 3: 配置并跑 Rollout ----------

def step_run(dataset_name: str, args) -> int | None:
    """用 Platform CLI 创建 Rollout"""
    # 获取 presets
    if not args.preset:
        presets_data = Platform("presets")
        presets = presets_data.get("presets", []) if isinstance(presets_data, dict) else []
        if presets:
            options = [f"{p.get('id')} ({p.get('label', '')})" for p in presets]
            idx = ask_choice("\n️ Step 3: Preset", options)
            args.preset = presets[idx - 1].get("id")
        else:
            args.preset = ask("Preset", "kimi_chat")

    # 构建 run 命令
    run_args = ["--preset", args.preset, "--dataset", dataset_name]

    if args.model:
        run_args += ["--model", args.model]
    if args.thinking is not None:
        run_args += ["--thinking", str(args.thinking)]
    if args.temperature:
        run_args += ["--temperature", str(args.temperature)]

    # Dry-run
    print("\n Step 3: Rollout")
    print(f"  Preset: {args.preset}")
    print(f"  Dataset: {dataset_name}")

    dry = Platform("run", *run_args, "--dry-run")
    if isinstance(dry, dict):
        payload = dry.get("payload", dry)
        batch_config = payload.get("batch", {}).get("config", {})
        llm = batch_config.get("llm", {})
        prompt = batch_config.get("prompt", {})
        print(f"  Model: {llm.get('model', '?')}")
        print(f"  Prompt: {prompt.get('systemPromptName', '?')}")
        print(f"  Temperature: {llm.get('temperature', '?')}")
        print(f"  Thinking: {llm.get('thinking', '?')}")
        tasks = dry.get("taskCount", payload.get("tasks", {}).get("items", []))
        print(f"  Tasks: {len(tasks) if isinstance(tasks, list) else tasks}")

    if not args.yes and not ask_yn("\n确认跑？"):
        print("️ 已取消")
        return None

    # 正式跑
    result = Platform("run", *run_args)
    if isinstance(result, dict):
        batch_id = result.get("batchId")
        task_count = result.get("taskCount", "?")
        print("\n   Rollout 已提交！")
        print(f"     Batch ID: {batch_id}")
        print(f"     Tasks: {task_count}")
        return batch_id
    else:
        print(f"  结果: {result}")
        return None


# ---------- Step 4: 监控 ----------

def step_monitor(batch_id: int, args):
    """用 Platform CLI 监控进度"""
    if not ask_yn(f"\n 监控 Batch {batch_id} 进度？"):
        return

    while True:
        desc = Platform("describe", "--batch", str(batch_id))
        if isinstance(desc, dict):
            status = desc.get("status", "unknown")
            total = desc.get("totalTasks", 0)
            succeeded = desc.get("succeededTasks", 0)
            failed = desc.get("failedTasks", 0)
            running = desc.get("runningTasks", 0)
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] {succeeded}/{total} 完成, {running} 运行中, {failed} 失败, 状态: {status}")

            if status in ("completed", "failed", "cancelled"):
                break
        else:
            print(f"  {desc}")

        time.sleep(30)

    # 查分数
    print("\n 查看分数...")
    scores = Platform("scores", "--batch", str(batch_id))
    if isinstance(scores, dict):
        rows = scores.get("rows", scores.get("scores", []))
        if rows:
            for row in rows:
                name = row.get("name", "?")
                avg = row.get("avg")
                count = row.get("count", 0)
                dist = row.get("distribution", {})
                if dist:
                    print(f"  {name}: {dist} (共 {count} 条)")
                elif avg is not None:
                    print(f"  {name}: avg={avg:.2f} (共 {count} 条)")
        else:
            print("  暂无分数（可能需要先跑 Judge）")
    else:
        print(f"  {scores}")

    # 导出
    if ask_yn("导出结果 JSONL？"):
        Platform("export", "--batch", str(batch_id), "--output", f"batch_{batch_id}.jsonl")
        print("   导出完成")


# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(description="交互式评测全流程（Platform CLI）")
    parser.add_argument("--file", default=None, help="数据文件 (CSV/JSONL)")
    parser.add_argument("--dataset-name", default=None)
    parser.add_argument("--input-fields", default=None, help="Input 字段（逗号分隔）")
    parser.add_argument("--metadata-fields", default=None, help="Metadata 字段（逗号分隔）")
    parser.add_argument("--field-mapping", default=None, help="完整的 field-mapping JSON")
    parser.add_argument("--preset", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--thinking", type=int, default=None, help="Thinking budget (0=禁用)")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--auto-judge", action="store_true")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过确认")
    args = parser.parse_args()

    if not os.environ.get("AuthGateway_ACCESS_TOKEN"):
        print(" 请设置 AuthGateway_ACCESS_TOKEN")
        sys.exit(1)

    print(" Eval Skill  交互式评测（Platform CLI）\n")

    # Step 0: AKSK 预检
    if not step_check_aksk(args):
        sys.exit(1)

    # Step 1: 数据
    file_path = step_data_source(args)

    # Step 2: 上传
    if file_path:
        dataset_name = step_upload(file_path, args)
    else:
        dataset_name = args.dataset_name

    # Step 3: 跑 Rollout
    batch_id = step_run(dataset_name, args)

    # Step 4: 监控
    if batch_id:
        step_monitor(batch_id, args)


if __name__ == "__main__":
    main()
