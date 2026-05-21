#!/usr/bin/env python3
"""
benchmark_registry.py  Benchmark 注册表管理

每个 benchmark 的配置记一次，以后一键复用。跑完自动记录分数历史。

用法:
    # 列出所有已注册的 benchmark
    python scripts/benchmark_registry.py list

    # 查看某个 benchmark 的配置
    python scripts/benchmark_registry.py show search-badcase-118

    # 用已有配置跑评测（自动读配置 → dry-run → 确认 → 跑）
    python scripts/benchmark_registry.py run search-badcase-118

    # 注册新 benchmark
    python scripts/benchmark_registry.py register --name "my-bmk" --dataset "my-dataset" --preset kimi_chat

    # 记录一次跑评测的结果
    python scripts/benchmark_registry.py record search-badcase-118 --batch-id 69528 --score 78.5
"""

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

# ---------- 配置 ----------

BENCHMARKS_DIR = Path(__file__).parent.parent / "benchmarks"

for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(k, None)


# ---------- YAML 读写（兼容没装 pyyaml）----------

def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        if yaml:
            return yaml.safe_load(f)
        # 简单解析
        content = f.read()
        result = {}
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if val == "[]":
                    result[key] = []
                elif val == "null":
                    result[key] = None
                elif val == "true":
                    result[key] = True
                elif val == "false":
                    result[key] = False
                elif val.isdigit():
                    result[key] = int(val)
                else:
                    result[key] = val
        return result


def save_yaml(path, data):
    with open(path, "w", encoding="utf-8") as f:
        if yaml:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        else:
            for key, val in data.items():
                if isinstance(val, list) and not val:
                    f.write(f"{key}: []\n")
                elif isinstance(val, list):
                    f.write(f"{key}:\n")
                    for item in val:
                        if isinstance(item, dict):
                            f.write(f"  - {json.dumps(item, ensure_ascii=False)}\n")
                        else:
                            f.write(f"  - {item}\n")
                elif val is None:
                    f.write(f"{key}: null\n")
                elif isinstance(val, bool):
                    f.write(f"{key}: {'true' if val else 'false'}\n")
                else:
                    f.write(f"{key}: {val}\n")


# ---------- 命令 ----------

def cmd_list(args):
    """列出所有已注册的 benchmark"""
    if not BENCHMARKS_DIR.exists():
        print(" benchmarks/ 目录不存在")
        return

    files = sorted(BENCHMARKS_DIR.glob("*.yaml"))
    if not files:
        print(" 没有已注册的 benchmark")
        return

    print(f" 已注册 {len(files)} 个 benchmark:\n")
    for f in files:
        data = load_yaml(f)
        name = data.get("name", f.stem)
        dataset = data.get("dataset", "?")
        preset = data.get("preset", "?")
        owner = data.get("owner", "?")
        history = data.get("history", [])
        last_score = ""
        if history and isinstance(history, list) and len(history) > 0:
            last = history[-1]
            if isinstance(last, dict):
                last_score = f"最新: {last.get('score', '?')} ({last.get('date', '?')})"

        print(f"   {f.stem}")
        print(f"     {name} | dataset: {dataset} | preset: {preset} | owner: {owner}")
        if last_score:
            print(f"     {last_score}")
        print()


def cmd_show(args):
    """查看某个 benchmark 的配置"""
    path = BENCHMARKS_DIR / f"{args.benchmark}.yaml"
    if not path.exists():
        print(f" 找不到 benchmark: {args.benchmark}")
        print(f"   可用的: {', '.join(f.stem for f in BENCHMARKS_DIR.glob('*.yaml'))}")
        return

    data = load_yaml(path)
    print(f" {data.get('name', args.benchmark)}\n")
    for key, val in data.items():
        if key == "history":
            print(f"\n 历史记录 ({len(val) if isinstance(val, list) else 0} 次):")
            if isinstance(val, list):
                for item in val[-5:]:
                    if isinstance(item, dict):
                        print(f"  {item.get('date', '?')} | batch: {item.get('batch_id', '?')} | model: {item.get('model', '?')} | score: {item.get('score', '?')}")
        else:
            print(f"  {key}: {val}")


def cmd_run(args):
    """用已有配置跑评测"""
    path = BENCHMARKS_DIR / f"{args.benchmark}.yaml"
    if not path.exists():
        print(f" 找不到 benchmark: {args.benchmark}")
        return

    data = load_yaml(path)
    print(f" 跑评测: {data.get('name', args.benchmark)}")
    print(f"   Dataset: {data.get('dataset')}")
    print(f"   Preset: {data.get('preset')}")
    print(f"   Thinking: {data.get('thinking', True)}")
    print()

    # 找 Platform CLI
    orbit_cli = None
    for candidate in [
        Path(__file__).parent.parent / "skills" / "Platform" / "Platform.mjs",
        Path.home() / ".AI_Platform" / "skills" / "Platform" / "Platform.mjs",
        Path.home() / ".kitty",
    ]:
        if candidate.is_file():
            orbit_cli = str(candidate)
            break
        if candidate.is_dir():
            for p in candidate.rglob("Platform.mjs"):
                orbit_cli = str(p)
                break
            if orbit_cli:
                break

    if not orbit_cli:
        print(" 找不到 Platform CLI")
        return

    # 构建命令
    cmd = ["node", orbit_cli, "run",
           "--preset", data.get("preset", "kimi_chat"),
           "--dataset", data.get("dataset", "")]

    if data.get("thinking") is False:
        cmd += ["--thinking", "0"]

    # Dry-run
    print(" Dry-run...")
    result = subprocess.run(cmd + ["--dry-run"],
                          capture_output=True, text=True,
                          cwd=str(Path(orbit_cli).parent))
    print(result.stdout[:500] if result.stdout else result.stderr[:500])

    if not args.yes:
        confirm = input("\n确认跑？[y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print("️ 已取消")
            return

    # 正式跑
    print("\n 正式跑...")
    result = subprocess.run(cmd, capture_output=True, text=True,
                          cwd=str(Path(orbit_cli).parent))
    print(result.stdout[:500] if result.stdout else result.stderr[:500])


def cmd_register(args):
    """注册新 benchmark"""
    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)

    slug = args.name.lower().replace(" ", "-").replace("_", "-")
    path = BENCHMARKS_DIR / f"{slug}.yaml"

    data = {
        "name": args.name,
        "dataset": args.dataset,
        "preset": args.preset or "kimi_chat",
        "prompt": args.prompt or "AI_Platform-k2d5-0304",
        "judge_preset": args.judge_preset or "judge_opus_4_6",
        "judge_prompt": None,
        "score_configs": [],
        "thinking": True,
        "concurrent": 5,
        "owner": args.owner or "",
        "description": args.description or "",
        "history": [],
    }

    save_yaml(path, data)
    print(f" 已注册: {path}")
    print(f"   编辑配置: {path}")


def cmd_record(args):
    """记录一次评测结果"""
    path = BENCHMARKS_DIR / f"{args.benchmark}.yaml"
    if not path.exists():
        print(f" 找不到 benchmark: {args.benchmark}")
        return

    data = load_yaml(path)
    if not isinstance(data.get("history"), list):
        data["history"] = []

    record = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "batch_id": args.batch_id,
        "model": args.model or data.get("preset", "?"),
        "score": args.score,
    }
    data["history"].append(record)
    save_yaml(path, data)
    print(f" 已记录: score={args.score}, batch={args.batch_id}")


# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(description="Benchmark 注册表管理")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="列出所有 benchmark")

    show = sub.add_parser("show", help="查看 benchmark 配置")
    show.add_argument("benchmark")

    run = sub.add_parser("run", help="用已有配置跑评测")
    run.add_argument("benchmark")
    run.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    reg = sub.add_parser("register", help="注册新 benchmark")
    reg.add_argument("--name", required=True)
    reg.add_argument("--dataset", required=True)
    reg.add_argument("--preset", default="kimi_chat")
    reg.add_argument("--prompt", default=None)
    reg.add_argument("--judge-preset", default=None)
    reg.add_argument("--owner", default=None)
    reg.add_argument("--description", default=None)

    rec = sub.add_parser("record", help="记录评测结果")
    rec.add_argument("benchmark")
    rec.add_argument("--batch-id", required=True, type=int)
    rec.add_argument("--score", required=True, type=float)
    rec.add_argument("--model", default=None)

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "register":
        cmd_register(args)
    elif args.command == "record":
        cmd_record(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
