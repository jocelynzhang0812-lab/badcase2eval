#!/usr/bin/env python3
"""
Trace Replay Script

Replay trace data through X35 API and compare original vs new responses.
"""

import argparse
import json
import os
import time
import httpx
from pathlib import Path
from typing import Optional

# X35 API Configuration (千寻 OpenAI-compatible)
X35_BASE_URL = os.environ.get("X35_BASE_URL", "https://gateway.internal.ai.com/v1")
X35_API_KEY = os.environ.get("X35_API_KEY", "sk-b9CfyiKAeRZDyiKjwMVC7C3mVgIRVjoUKTCYy5w5AkCHVfu9")

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # 秒


def load_trace(trace_path: str) -> dict:
    """Load trace JSON file."""
    with open(trace_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def replay_request(request_data: dict, timeout: float = 120.0, max_retries: int = MAX_RETRIES) -> dict:
    """
    Replay a single request to X35 API with retry logic.

    Args:
        request_data: OpenAI-compatible request dict
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries for 429/5xx errors

    Returns:
        API response dict
    """
    # 移除不兼容的参数
    request_data.pop("temperature", None)
    request_data.pop("top_p", None)

    # 如果 assistant message 没有 reasoning_content，禁用 thinking
    has_reasoning = any(
        msg.get("reasoning_content")
        for msg in request_data.get("messages", [])
        if msg.get("role") == "assistant"
    )
    if not has_reasoning:
        request_data["thinking"] = {"type": "disabled"}

    # normalize: tool message 的 content 如果是 list，flatten 成 string
    for msg in request_data.get("messages", []):
        content = msg.get("content")
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("text"):
                    texts.append(block["text"])
                elif isinstance(block, str):
                    texts.append(block)
            msg["content"] = "\n".join(texts)

    last_error = None

    for attempt in range(max_retries):
        try:
            # 禁用代理，内网直连
            with httpx.Client(trust_env=False, timeout=timeout) as client:
                response = client.post(
                    f"{X35_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {X35_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=request_data
                )

            # 429 或 5xx 错误时重试
            if response.status_code == 429 or response.status_code >= 500:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                if attempt < max_retries - 1:
                    delay = RETRY_DELAY * (attempt + 1)  # 递增延迟
                    time.sleep(delay)
                    continue
                response.raise_for_status()

            response.raise_for_status()
            return response.json()

        except httpx.TimeoutException as e:
            last_error = f"Timeout: {e}"
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
                continue
            raise
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code}: {e.response.text[:500]}")
            raise
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
                continue
            raise

    raise Exception(f"Max retries exceeded. Last error: {last_error}")


def extract_content(response: dict) -> str:
    """Extract content from response for comparison."""
    if "choices" in response:
        # OpenAI format from new API call
        choice = response["choices"][0]
        message = choice.get("message", {})
        content = message.get("content", "")
        reasoning = message.get("reasoning_content", "")
        tool_calls = message.get("tool_calls", [])

        parts = []
        if reasoning:
            parts.append(f"[Reasoning]: {reasoning}")
        if content:
            parts.append(f"[Content]: {content}")
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                parts.append(f"[Tool Call]: {func.get('name', '')}({func.get('arguments', '')})")
        return "\n".join(parts) if parts else "(empty response)"
    else:
        # Original trace format
        content = response.get("content", "")
        reasoning = response.get("reasoning_content", "")
        tool_calls = response.get("tool_calls", [])

        parts = []
        if reasoning:
            parts.append(f"[Reasoning]: {reasoning}")
        if content:
            parts.append(f"[Content]: {content}")
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                parts.append(f"[Tool Call]: {func.get('name', '')}({func.get('arguments', '')})")
        return "\n".join(parts) if parts else "(empty response)"


def compare_responses(original: dict, replayed: dict) -> dict:
    """Compare original and replayed responses."""
    original_content = extract_content(original)
    replayed_content = extract_content(replayed)

    return {
        "match": original_content == replayed_content,
        "original": original_content,
        "replayed": replayed_content,
        "original_finish_reason": original.get("finish_reason"),
        "replayed_finish_reason": replayed.get("choices", [{}])[0].get("finish_reason") if "choices" in replayed else None,
    }


def extract_tool_results_from_messages(messages: list) -> list:
    """从 messages 中提取 tool role 的消息"""
    tool_results = []
    for msg in messages:
        if msg.get("role") == "tool":
            tool_results.append(msg)
    return tool_results


def find_original_tool_results(model_requests: list, current_step_idx: int) -> list:
    """
    从原始 trace 中找到当前 step 对应的 tool results

    tool results 在下一个 step 的 request.messages 中
    """
    next_step_idx = current_step_idx + 1
    if next_step_idx >= len(model_requests):
        return []

    next_request = model_requests[next_step_idx].get("request", {})
    messages = next_request.get("messages", [])
    return extract_tool_results_from_messages(messages)


def replay_from_step(trace_data: dict, turn_idx: int, step_idx: int,
                     max_steps: int = 10, save_dir: str = "chatlet/replay") -> dict:
    """
    从指定 step 开始 replay 完整对话

    Args:
        trace_data: 完整 trace
        turn_idx: Turn index (0-indexed)
        step_idx: 从哪个 step 开始分叉 (0-indexed)
        max_steps: 最大 replay 步数限制
        save_dir: 保存目录

    Returns:
        {
            "success": True/False,
            "original_steps": [...],      # 原始 turn 的所有 steps（response 结构）
            "replayed_steps": [...],      # replay 产生的 steps（response 结构）
            "branch_step_idx": step_idx,  # 分叉点
            "saved_file": "...",
            "error": "..."
        }
    """
    from datetime import datetime
    import copy

    chat_id = trace_data.get("chat_id", "unknown")
    trajectories = trace_data.get("model_trajectories", [])

    # 1. 找到对应的 turn
    turn_traj = None
    for traj in trajectories:
        if traj.get("turn_index") == turn_idx:
            turn_traj = traj
            break

    if not turn_traj:
        return {"success": False, "error": f"Turn {turn_idx} not found"}

    model_requests = turn_traj.get("model_requests", [])
    if step_idx >= len(model_requests):
        return {"success": False, "error": f"Step {step_idx} not found in turn {turn_idx}"}

    # 2. 提取原始 steps（所有 response）
    original_steps = []
    for i, req in enumerate(model_requests):
        original_steps.append({
            "step_index": i,
            "response": req.get("response", {}),
            "request_model": req.get("request", {}).get("model")
        })

    # 3. 准备 replay
    # 取分叉点 step 的 request 作为起点
    branch_request = model_requests[step_idx].get("request", {})
    current_messages = copy.deepcopy(branch_request.get("messages", []))
    model = branch_request.get("model")
    tools = branch_request.get("tools", [])
    max_tokens = branch_request.get("max_tokens")
    temperature = branch_request.get("temperature")

    # 检查原始 response 是否有 reasoning_content，用于推断是否需要禁用 thinking
    original_response = model_requests[step_idx].get("response", {})
    has_reasoning = bool(original_response.get("reasoning_content"))

    replayed_steps = []
    replay_step_count = 0

    # 4. 循环 replay
    while replay_step_count < max_steps:
        try:
            # 构造请求（复制原始请求的所有参数）
            request_data = {
                "model": model,
                "messages": current_messages
            }
            if tools:
                request_data["tools"] = tools
            if max_tokens is not None:
                request_data["max_tokens"] = max_tokens
            if temperature is not None:
                request_data["temperature"] = temperature

            # 如果原始 response 没有 reasoning_content，禁用 thinking
            if not has_reasoning:
                request_data["thinking"] = {"type": "disabled"}

            # 调用 API
            response = replay_request(request_data)

            # 提取 message
            if "choices" in response:
                message = response["choices"][0].get("message", {})
                finish_reason = response["choices"][0].get("finish_reason")
            else:
                message = response
                finish_reason = response.get("finish_reason")

            # 记录这一步
            replayed_steps.append({
                "step_index": replay_step_count,
                "response": message,
                "finish_reason": finish_reason,
                "replayed_model": response.get("model")
            })

            replay_step_count += 1

            # 检查是否结束
            if finish_reason == "stop" or not message.get("tool_calls"):
                break

            # 有 tool_calls，需要继续
            # 构造 assistant message（含 tool_calls）
            assistant_msg = {
                "role": "assistant",
                "content": message.get("content") or None
            }
            if message.get("tool_calls"):
                assistant_msg["tool_calls"] = message["tool_calls"]

            current_messages.append(assistant_msg)

            # 从原始 trace 找到对应的 tool results
            # 对应原始 trace 的 step = step_idx + replay_step_count - 1
            original_step_for_tool = step_idx + replay_step_count - 1
            tool_results = find_original_tool_results(model_requests, original_step_for_tool)

            if not tool_results:
                # 没有找到原始 tool results，只能停止
                break

            # 追加 tool results
            current_messages.extend(tool_results)

        except Exception as e:
            replayed_steps.append({
                "step_index": replay_step_count,
                "error": str(e)
            })
            break

    # 5. 保存结果
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H%M%S")
    save_path = Path(save_dir) / today
    save_path.mkdir(parents=True, exist_ok=True)

    filename = f"{timestamp}_{chat_id}_branch_{turn_idx+1}-{step_idx+1}.json"
    filepath = save_path / filename

    result = {
        "chat_id": chat_id,
        "turn": turn_idx + 1,
        "branch_step": step_idx + 1,
        "timestamp": timestamp,
        "original_steps": original_steps,
        "replayed_steps": replayed_steps
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return {
        "success": True,
        "original_steps": original_steps,
        "replayed_steps": replayed_steps,
        "branch_step_idx": step_idx,
        "saved_file": str(filepath)
    }


def replay_step_and_save(trace_data: dict, turn_idx: int, step_idx: int, save_dir: str = "chatlet/replay") -> dict:
    """
    Replay a single step and save result to file.

    Args:
        trace_data: Full trace data dict
        turn_idx: Turn index (0-indexed)
        step_idx: Step index (0-indexed)
        save_dir: Directory to save replay results

    Returns:
        dict with keys: success, match, original_content, replayed_content, error, saved_file
    """
    from datetime import datetime

    chat_id = trace_data.get("chat_id", "unknown")
    trajectories = trace_data.get("model_trajectories", [])

    # Find the turn
    turn_traj = None
    for traj in trajectories:
        if traj.get("turn_index") == turn_idx:
            turn_traj = traj
            break

    if not turn_traj:
        return {"success": False, "error": f"Turn {turn_idx} not found"}

    requests = turn_traj.get("model_requests", [])
    if step_idx >= len(requests):
        return {"success": False, "error": f"Step {step_idx} not found"}

    request_data = requests[step_idx]
    request = request_data.get("request", {})
    original_response = request_data.get("response", {})

    # Extract original content
    original_content = extract_content(original_response)

    try:
        # Replay
        replayed_response = replay_request(request)
        comparison = compare_responses(original_response, replayed_response)

        # Save to file (按日期组织)
        today = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%H%M%S")
        save_path = Path(save_dir) / today
        save_path.mkdir(parents=True, exist_ok=True)

        filename = f"{timestamp}_{chat_id}_{turn_idx+1}-{step_idx+1}.json"
        filepath = save_path / filename

        replay_result = {
            "chat_id": chat_id,
            "turn": turn_idx + 1,
            "step": step_idx + 1,
            "timestamp": timestamp,
            "match": comparison["match"],
            "request": request,  # 包含所有 messages 上下文
            "original_response": original_response,
            "replayed_response": replayed_response,
            "comparison": {
                "original_content": comparison["original"],
                "replayed_content": comparison["replayed"]
            }
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(replay_result, f, indent=2, ensure_ascii=False)

        # 提取最后几条非 system 消息用于展示 (包含 tool_calls)
        messages = request.get("messages", [])
        request_context = []
        for m in messages:
            if m.get("role") == "system":
                continue
            msg = {
                "role": m.get("role", ""),
                "content": m.get("content", "")
            }
            # 保留 assistant 的 tool_calls
            if m.get("tool_calls"):
                msg["tool_calls"] = m.get("tool_calls")
            request_context.append(msg)
        request_context = request_context[-5:]  # 最后 5 条

        return {
            "success": True,
            "match": comparison["match"],
            "original_response": original_response,  # 原始结构
            "replayed_response": replayed_response,  # 原始结构
            "request_messages": request_context,
            "saved_file": str(filepath)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "original_content": original_content
        }


def replay_turn(trace: dict, turn_index: int, step_index: Optional[int] = None, verbose: bool = True) -> list:
    """
    Replay a specific turn from the trace.

    Args:
        trace: Full trace dict
        turn_index: Index of turn to replay
        step_index: Optional specific step to replay (None = all steps)
        verbose: Print progress

    Returns:
        List of comparison results
    """
    trajectories = trace.get("model_trajectories", [])

    # Find the trajectory for this turn
    turn_trajectory = None
    for traj in trajectories:
        if traj.get("turn_index") == turn_index:
            turn_trajectory = traj
            break

    if not turn_trajectory:
        raise ValueError(f"Turn {turn_index} not found in trace")

    model_requests = turn_trajectory.get("model_requests", [])
    results = []

    for i, request_data in enumerate(model_requests):
        if step_index is not None and i != step_index:
            continue

        if verbose:
            print(f"\n{'='*60}")
            print(f"Turn {turn_index}, Step {i}")
            print('='*60)

        request = request_data.get("request", {})
        original_response = request_data.get("response", {})

        # Print request summary
        if verbose:
            messages = request.get("messages", [])
            print(f"Model: {request.get('model')}")
            print(f"Messages: {len(messages)}")
            if messages:
                last_msg = messages[-1]
                role = last_msg.get("role", "unknown")
                content = last_msg.get("content", "")
                if isinstance(content, str):
                    preview = content[:100] + "..." if len(content) > 100 else content
                elif isinstance(content, list):
                    preview = f"[{len(content)} content blocks]"
                else:
                    preview = str(content)[:100]
                print(f"Last message ({role}): {preview}")

        # Replay the request
        try:
            if verbose:
                print("\nReplaying request...")
            replayed_response = replay_request(request)

            # Compare
            comparison = compare_responses(original_response, replayed_response)
            comparison["turn_index"] = turn_index
            comparison["step_index"] = i
            comparison["request_model"] = request.get("model")
            comparison["replayed_model"] = replayed_response.get("model")

            results.append(comparison)

            if verbose:
                print("\n--- Original Response ---")
                print(comparison["original"][:500] + "..." if len(comparison["original"]) > 500 else comparison["original"])
                print("\n--- Replayed Response ---")
                print(comparison["replayed"][:500] + "..." if len(comparison["replayed"]) > 500 else comparison["replayed"])
                print(f"\n--- Match: {comparison['match']} ---")

        except Exception as e:
            if verbose:
                print(f"Error replaying request: {e}")
            results.append({
                "turn_index": turn_index,
                "step_index": i,
                "error": str(e)
            })

    return results


def main():
    parser = argparse.ArgumentParser(description="Replay trace data through X35 API")
    parser.add_argument("trace_file", help="Path to trace JSON file")
    parser.add_argument("--turn", type=int, help="Only replay specific turn index")
    parser.add_argument("--step", type=int, help="Only replay specific step (requires --turn)")
    parser.add_argument("--output", "-o", help="Save comparison results to JSON file")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode (minimal output)")
    parser.add_argument("--list", "-l", action="store_true", help="List available turns and steps")
    parser.add_argument("--inject", type=str, help="注入文件路径：将文件内容追加到 tool result 消息末尾（模拟 post-tool-use hook）")
    parser.add_argument("--model", type=str, help="覆盖 trace 中的模型名（如 AI_Platform-k2.5）")

    args = parser.parse_args()

    # Load trace
    trace = load_trace(args.trace_file)
    print(f"Loaded trace: {trace.get('chat_id', 'unknown')}")

    trajectories = trace.get("model_trajectories", [])

    # List mode
    if args.list:
        print("\nAvailable trajectories:")
        for traj in trajectories:
            turn_idx = traj.get("turn_index")
            segment_id = traj.get("segment_id", "unknown")
            num_requests = len(traj.get("model_requests", []))
            print(f"  Turn {turn_idx}: {num_requests} step(s), segment={segment_id}")
        return

    # Validate args
    if args.step is not None and args.turn is None:
        parser.error("--step requires --turn")

    # 读取注入内容
    inject_text = None
    if args.inject:
        with open(args.inject, "r", encoding="utf-8") as f:
            inject_text = f.read()
        print(f"Inject loaded ({len(inject_text)} chars): {args.inject}")

    # 如果有注入，替换 trace 中 tool result 里的 <SYSTEM_REMINDER> 块
    if inject_text:
        import copy
        import re
        # deep copy 避免污染原始 trace
        trajectories = copy.deepcopy(trajectories)
        trace["model_trajectories"] = trajectories
        sr_pattern = re.compile(r'<SYSTEM_REMINDER>.*?</SYSTEM_REMINDER>', re.DOTALL)
        for traj in trajectories:
            for req_data in traj.get("model_requests", []):
                for msg in req_data.get("request", {}).get("messages", []):
                    if msg.get("role") == "tool":
                        content = msg.get("content")
                        if isinstance(content, list):
                            found = False
                            for block in content:
                                if isinstance(block, dict) and block.get("text"):
                                    if sr_pattern.search(block["text"]):
                                        block["text"] = sr_pattern.sub(inject_text.strip(), block["text"])
                                        found = True
                            if not found:
                                # 没有现有 SYSTEM_REMINDER，追加到最后一个 text block
                                for block in reversed(content):
                                    if isinstance(block, dict) and block.get("text"):
                                        block["text"] = block["text"] + "\n" + inject_text.strip()
                                        break
                        elif isinstance(content, str) and content:
                            if sr_pattern.search(content):
                                msg["content"] = sr_pattern.sub(inject_text.strip(), content)
                            else:
                                msg["content"] = content + "\n" + inject_text

    # 如果指定了 --model，覆盖所有 request 的模型名
    if args.model:
        for traj in trajectories:
            for req_data in traj.get("model_requests", []):
                req = req_data.get("request", {})
                req["model"] = args.model
        print(f"Model overridden to: {args.model}")

    # Collect results
    all_results = []
    verbose = not args.quiet

    if args.turn is not None:
        # Replay specific turn
        results = replay_turn(trace, args.turn, args.step, verbose=verbose)
        all_results.extend(results)
    else:
        # Replay all turns
        for traj in trajectories:
            turn_idx = traj.get("turn_index")
            results = replay_turn(trace, turn_idx, verbose=verbose)
            all_results.extend(results)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print('='*60)

    total = len(all_results)
    errors = sum(1 for r in all_results if "error" in r)
    matches = sum(1 for r in all_results if r.get("match", False))

    print(f"Total steps: {total}")
    print(f"Errors: {errors}")
    print(f"Matches: {matches}/{total - errors}")

    # Save output
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "trace_file": args.trace_file,
                "chat_id": trace.get("chat_id"),
                "results": all_results,
                "summary": {
                    "total": total,
                    "errors": errors,
                    "matches": matches
                }
            }, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
