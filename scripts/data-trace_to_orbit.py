#!/usr/bin/env python3
"""
trace_to_orbit.py  从 get_message.py 的 trace JSON 构造 Platform 可用的 dataset + prompt

用法:
    # 基本用法（turn 0）
    python scripts/trace_to_orbit.py chatlet/trace/<chat_id>.json

    # 指定 turn
    python scripts/trace_to_orbit.py chatlet/trace/<chat_id>.json --turn 1

    # 指定 dataset 名 + 自定义 system prompt 文件（A/B 测试）
    python scripts/trace_to_orbit.py chatlet/trace/<chat_id>.json \
        --dataset "replay-xxx" \
        --system-prompt /path/to/new_sp.md

    # 指定 step（API 直打模式，不走 Platform）
    python scripts/trace_to_orbit.py chatlet/trace/<chat_id>.json --turn 0 --step 1

输出:
    - orbit_replay/<chat_id>/dataset.jsonl    Platform dataset 文件
    - 自动创建 Langfuse prompt（如不存在）
    - 打印 Platform run 命令
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def load_trace(trace_path: str) -> dict:
    with open(trace_path) as f:
        return json.load(f)


def extract_messages(trace: dict, turn: int, step: int | None = None) -> tuple[list[dict], list[dict], dict]:
    """从 trace 提取指定 turn(-step) 的 messages、tools、request meta。

    Returns:
        (messages, tools, request_meta)
    """
    trajectories = trace.get("model_trajectories", [])

    # 找到目标 turn
    target = None
    for traj in trajectories:
        if traj.get("turn_index") == turn:
            target = traj
            break

    if target is None:
        available = [t.get("turn_index") for t in trajectories]
        print(f" turn {turn} 不存在，可用: {available}")
        sys.exit(1)

    requests = target.get("model_requests", [])
    if not requests:
        print(f" turn {turn} 没有 model_requests")
        sys.exit(1)

    # step 级别：取特定 step 的 request
    if step is not None:
        if step >= len(requests):
            print(f" step {step} 超出范围（共 {len(requests)} 步）")
            sys.exit(1)
        req = requests[step]
    else:
        # turn 级别：取第一个 step（初始 messages）
        req = requests[0]

    request_data = req.get("request", {})
    messages = request_data.get("messages", [])
    tools = request_data.get("tools", [])
    meta = {
        "model": request_data.get("model", ""),
        "temperature": request_data.get("temperature"),
        "max_tokens": request_data.get("max_tokens"),
    }

    return messages, tools, meta


def messages_to_fields(messages: list[dict]) -> dict:
    """将 messages 数组拆为命名字段。

    固定结构：
      [0] system          → system_prompt
      [1] user/memory     → memory_space
      [2] user/memory     → user_knowledge
      [3] user/memory     → recent_conv
      [4] user            → user_message
      [5+] 多轮历史       → conversation_history (JSON)

    如果结构不匹配，回退到通用编号。
    """
    fields = {}

    # 分离 system
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    if system_msgs:
        fields["system_prompt"] = _get_content(system_msgs[0])

    # 分离 memory messages 和其他
    memory_msgs = []
    other_msgs = []
    for m in non_system:
        if m.get("name") == "memory":
            memory_msgs.append(m)
        else:
            other_msgs.append(m)

    # Memory messages 按内容特征命名
    for i, m in enumerate(memory_msgs):
        content = _get_content(m)
        if "memory_space" in content[:50]:
            fields["memory_space"] = content
        elif "User Knowledge" in content[:50]:
            fields["user_knowledge"] = content
        elif "Recent Conversation" in content[:50]:
            fields["recent_conv"] = content
        else:
            fields[f"memory_{i}"] = content

    # 最后一条非 memory user message = 当前 user query
    if other_msgs:
        last_user = other_msgs[-1]
        fields["user_message"] = _get_content(last_user)

        # 中间的 = 多轮历史（assistant/user 交替）
        if len(other_msgs) > 1:
            history = []
            for m in other_msgs[:-1]:
                history.append({
                    "role": m.get("role"),
                    "content": _get_content(m),
                })
            fields["conversation_history"] = json.dumps(history, ensure_ascii=False)

    return fields


def _get_content(msg: dict) -> str:
    """提取 message content，处理 string 和 list 两种格式。"""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def create_prompt_if_needed(prompt_name: str, fields: dict, orbit_cli: str) -> bool:
    """检查 Langfuse prompt 是否存在，不存在则创建。"""
    # 检查是否存在
    result = subprocess.run(
        ["node", orbit_cli, "prompts", "--versions", prompt_name],
        capture_output=True, text=True,
        cwd=str(Path(orbit_cli).parent),
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        if data.get("versions"):
            print(f" Prompt '{prompt_name}' 已存在")
            return True

    # 构造 prompt messages
    prompt_messages = [
        {"role": "system", "content": "{{system_prompt}}"},
    ]

    if "memory_space" in fields:
        prompt_messages.append({"role": "user", "content": "{{memory_space}}"})
    if "user_knowledge" in fields:
        prompt_messages.append({"role": "user", "content": "{{user_knowledge}}"})
    if "recent_conv" in fields:
        prompt_messages.append({"role": "user", "content": "{{recent_conv}}"})
    if "conversation_history" in fields:
        prompt_messages.append({"role": "user", "content": "{{conversation_history}}"})

    prompt_messages.append({"role": "user", "content": "{{user_message}}"})

    # 通过 Platform API 创建
    import urllib.request
    token = os.environ.get("AuthGateway_ACCESS_TOKEN", "")
    base = os.environ.get("ORBIT_API_BASE", "https://platform.internal.ai.com")

    payload = json.dumps({
        "name": prompt_name,
        "type": "chat",
        "prompt": prompt_messages,
        "labels": ["latest", "production"],
        "config": {},
    }).encode()

    req = urllib.request.Request(
        f"{base}/api/prompts",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-AuthGateway-Access-Token": token,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f" Prompt '{prompt_name}' 已创建 (version {result.get('version', '?')})")
            return True
    except Exception as e:
        print(f" 创建 prompt 失败: {e}")
        return False


def find_orbit_cli() -> str:
    candidates = [
        Path(__file__).parent.parent.parent / "Platform" / "Platform.mjs",
        Path.home() / ".claude" / "skills" / "Platform" / "Platform.mjs",
        Path.home() / ".AI_Platform" / "skills" / "Platform" / "Platform.mjs",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    print("️ 找不到 Platform.mjs，prompt 创建和上传需要手动操作")
    return ""


def main():
    parser = argparse.ArgumentParser(description="Trace → Platform dataset + prompt")
    parser.add_argument("trace_file", help="get_message.py 输出的 trace JSON 文件")
    parser.add_argument("--turn", type=int, default=0, help="目标 turn（默认 0）")
    parser.add_argument("--step", type=int, default=None, help="目标 step（指定后为 API 直打模式）")
    parser.add_argument("--dataset", default=None, help="Platform dataset 名（默认 replay-<chat_id>）")
    parser.add_argument("--system-prompt", default=None, help="替换 system prompt 的文件路径（A/B 测试）")
    parser.add_argument("--output", "-o", default=None, help="输出目录（默认 orbit_replay/<chat_id>/）")
    parser.add_argument("--upload", action="store_true", help="自动上传到 Platform")
    args = parser.parse_args()

    # 1. 加载 trace
    trace = load_trace(args.trace_file)
    chat_id = trace.get("chat_id", Path(args.trace_file).stem)

    # 2. 提取 messages
    messages, tools, meta = extract_messages(trace, args.turn, args.step)
    print(f" Chat: {chat_id} | Turn: {args.turn} | Step: {args.step or 'all'}")
    print(f"   Model: {meta['model']} | Messages: {len(messages)} | Tools: {len(tools)}")

    # 3. 拆为命名字段
    fields = messages_to_fields(messages)

    # 4. 替换 system prompt（A/B 测试）
    if args.system_prompt:
        with open(args.system_prompt) as f:
            fields["system_prompt"] = f.read()
        print(f"    System prompt 替换为: {args.system_prompt}")

    # 5. 输出目录
    output_dir = Path(args.output or f"orbit_replay/{chat_id}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 6. 写 dataset JSONL
    dataset_name = args.dataset or f"replay-{chat_id[:16]}"

    dataset_item = {**fields}
    # metadata
    dataset_item["_meta_chat_id"] = chat_id
    dataset_item["_meta_turn"] = args.turn
    dataset_item["_meta_model"] = meta["model"]

    dataset_path = output_dir / "dataset.jsonl"
    with open(dataset_path, "w") as f:
        f.write(json.dumps(dataset_item, ensure_ascii=False) + "\n")

    print(f"\n Dataset: {dataset_path} (1 条)")

    # 7. 保存 tools（供参考）
    if tools:
        tools_path = output_dir / "tools.json"
        with open(tools_path, "w") as f:
            json.dump(tools, f, ensure_ascii=False, indent=2)
        print(f" Tools: {tools_path} ({len(tools)} 个)")

    # 8. Prompt + Upload
    orbit_cli = find_orbit_cli()
    prompt_name = f"replay-{chat_id[:16]}"

    if orbit_cli:
        # 取消代理
        for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
            os.environ.pop(key, None)

        input_fields = [k for k in fields.keys()]
        meta_fields = [k for k in dataset_item.keys() if k.startswith("_meta_")]

        create_prompt_if_needed(prompt_name, fields, orbit_cli)

        if args.upload:
            field_mapping = json.dumps({
                "inputFields": input_fields,
                "metadataFields": meta_fields,
            })
            subprocess.run(
                ["node", orbit_cli, "upload", str(dataset_path.resolve()),
                 "--dataset", dataset_name,
                 "--field-mapping", field_mapping],
                cwd=str(Path(orbit_cli).parent),
            )
            print(f" 已上传到 Platform dataset: {dataset_name}")

    # 9. 打印后续命令
    print("\n 后续命令:")
    if args.step is not None:
        print(f"   [API 直打模式] step={args.step}，不走 Platform，直接调模型 API")
        print(f"   数据在 {dataset_path}，用 fields['system_prompt'] + fields['user_message'] 拼 request")
    else:
        print("   # 上传（如未 --upload）")
        print(f"   node Platform.mjs upload {dataset_path} --dataset \"{dataset_name}\"")
        print("")
        print("   # Platform run（用原始 SP）")
        print(f"   node Platform.mjs run --preset kimi_chat --dataset \"{dataset_name}\" --prompt {prompt_name} --prompt-label production --dry-run")
        print("")
        print("   # Platform run（换 SP 做 A/B）")
        print("   # 先创建新 prompt，再 --prompt <new-prompt-name>")


if __name__ == "__main__":
    main()
