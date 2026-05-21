#!/usr/bin/env python3
"""
Trace Replay Script (Chatty 版本)

通过 Chatty 流式 API 回放 trace，与原始响应对比。
参考 chatty.py 的调用方式，使用 ChattyServiceClient.chat_workflow_stream。
"""

import argparse
import asyncio
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from kimi_python.AI_Platform.chatty.v1.service_connect import ChattyServiceClient
from kimi_python.AI_Platform.chatty.v1.request_pb2 import ChattyRequest, ChattyRequestOptions
from kimi_python.AI_Platform.chatty.v1 import message_pb2, tool_pb2
from kimi_python.AI_Platform.chatty.v1 import response_stream_pb2
from kimi_python.userctx.v1 import user_context_pb2
from google.protobuf.json_format import MessageToJson

# 与 AI_Platform-darkmatter auth.HeaderUserContext 一致，Chatty 从该 header 解析 userctxv1.UserContext
HEADER_USER_CTX = "X-Msh-User-Ctx"

# 从 replay 复用
from replay import (
    load_trace,
    extract_content,
    compare_responses,
    find_original_tool_results,
)

# Chatty 默认配置（优先读 .env）
CHATTY_BASE_URL = os.environ.get("CHATTY_REPLAY_TEST_BASE_URL", "https://chatty.dev.AI_Platform.team")
DEFAULT_WORKFLOW = 16  # WORKFLOW_K2D5

# 事件类型（与 response_stream_pb2.EventType 一致）
EVENT_TYPE_MODEL_TEXT = response_stream_pb2.EVENT_TYPE_MODEL_TEXT
EVENT_TYPE_MODEL_REASONING = response_stream_pb2.EVENT_TYPE_MODEL_REASONING
EVENT_TYPE_MODEL_END = response_stream_pb2.EVENT_TYPE_MODEL_END
EVENT_TYPE_TOOL_START = response_stream_pb2.EVENT_TYPE_TOOL_START
EVENT_TYPE_TOOL_END = response_stream_pb2.EVENT_TYPE_TOOL_END

# ---------- OpenTelemetry Trace 辅助 ----------

_trace_provider = TracerProvider(sampler=ALWAYS_ON)
_tracer = _trace_provider.get_tracer(__name__)
_trace_propagator = TraceContextTextMapPropagator()


def parse_tool_event(response) -> dict | None:
    """
    只解析 tool_start（关心 args）和 tool_end（关心 result）。
    返回 {"event": "tool_start", "name": str, "args": str} 或 {"event": "tool_end", "result": str, "is_error": bool}，否则 None。
    兼容：若 response 带 tool_start/tool_end 字段则优先按字段解析，不依赖 type 枚举（避免服务端事件类型不一致）。
    """
    has = getattr(response, "HasField", None)
    if not callable(has):
        return None
    if has("tool_start"):
        e = response.tool_start
        return {
            "event": "tool_start",
            "name": e.name or "",
            "args": e.args or "",
        }
    if has("tool_end"):
        e = response.tool_end
        return {
            "event": "tool_end",
            "result": e.result or "",
            "is_error": bool(e.is_error),
        }
    if not hasattr(response, "type"):
        return None
    t = response.type
    if t == EVENT_TYPE_TOOL_START and has("tool_start"):
        e = response.tool_start
        return {
            "event": "tool_start",
            "name": e.name or "",
            "args": e.args or "",
        }
    if t == EVENT_TYPE_TOOL_END and has("tool_end"):
        e = response.tool_end
        return {
            "event": "tool_end",
            "result": e.result or "",
            "is_error": bool(e.is_error),
        }
    return None


def format_tool_events_for_display(tool_events: list) -> str:
    """只展示 tool_start 的 args 和 tool_end 的 result。"""
    if not tool_events:
        return "(no tool events)"
    lines = []
    for i, ev in enumerate(tool_events):
        if ev.get("event") == "tool_start":
            name, args = ev.get("name", ""), ev.get("args", "")
            lines.append(f"  [{i+1}] tool_start  name={name}  args={args}")
        elif ev.get("event") == "tool_end":
            result, err = ev.get("result", ""), " [ERROR]" if ev.get("is_error") else ""
            lines.append(f"  [{i+1}] tool_end    result={result}{err}")
    return "\n".join(lines) if lines else "(no tool_start/tool_end)"


def format_ordered_stream_display(ordered_stream: list) -> str:
    """按流式到达顺序展示 content 与 tool 事件（不截断，便于查看完整 tool 等）。"""
    if not ordered_stream:
        return "(empty stream)"
    lines = []
    for i, item in enumerate(ordered_stream):
        if item.get("type") == "content":
            text = (item.get("text") or "").strip()
            if text:
                lines.append(f"  [{i+1}] [Content]: {text}")
        elif item.get("type") == "tool_event":
            ev = item.get("event") or {}
            if ev.get("event") == "tool_start":
                name, args = ev.get("name", ""), ev.get("args", "")
                lines.append(f"  [{i+1}] tool_start  name={name}  args={args}")
            elif ev.get("event") == "tool_end":
                result, err = ev.get("result", ""), " [ERROR]" if ev.get("is_error") else ""
                lines.append(f"  [{i+1}] tool_end    result={result}{err}")
    return "\n".join(lines) if lines else "(empty)"


def _openai_role_to_chatty(role: str) -> int:
    r = role.lower()
    if r == "system":
        return message_pb2.system
    if r == "user":
        return message_pb2.user
    if r == "assistant":
        return message_pb2.assistant
    if r == "tool":
        return message_pb2.tool
    return message_pb2.user


def _content_to_chatty_contents(content) -> list:
    """将 OpenAI 的 content（str 或 list）转为 Chatty ContentItem 列表。"""
    items = []
    if isinstance(content, str):
        if content.strip():
            items.append(message_pb2.ContentItem(text=content))
        return items
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                t = block.get("type")
                if t == "text" and block.get("text"):
                    items.append(message_pb2.ContentItem(text=block["text"]))
                elif t == "image_url":
                    # 简化：不转图片，仅占位
                    pass
            elif isinstance(block, str) and block.strip():
                items.append(message_pb2.ContentItem(text=block))
    return items


def _openai_tool_calls_to_chatty(tool_calls: list) -> list:
    """将 OpenAI tool_calls 转为 Chatty ToolCall 列表。"""
    out = []
    for i, tc in enumerate(tool_calls or []):
        func = tc.get("function", {})
        out.append(
            tool_pb2.ToolCall(
                id=tc.get("id", ""),
                index=i,
                type=tool_pb2.TOOL_TYPE_FUNCTION,
                function=tool_pb2.FunctionCall(
                    name=func.get("name", ""),
                    arguments=func.get("arguments", ""),
                ),
            )
        )
    return out


def build_user_ctx_headers(user_id: str, *, language: str = "zh-CN") -> dict[str, str]:
    """
    使用 kimi_python 的 UserContext proto 构建传给 Chatty 的 userCtx header。

    Chatty 侧 session 拦截器用 protojson 解析 X-Msh-User-Ctx -> userctxv1.UserContext，
    这里我们用 protobuf 官方的 JSON 序列化（与 proto3 JSON 规范兼容）来生成该值，
    避免手拼 JSON 时字段名/枚举值出错导致解析失败。
    """
    ctx = user_context_pb2.UserContext()
    ctx.user_id = user_id
    if language:
        ctx.language = language

    # MessageToJson 输出带缩进的 JSON，需要压缩为单行（HTTP header 不允许换行）
    raw_json = MessageToJson(ctx)
    header_value = json.dumps(json.loads(raw_json), separators=(",", ":"), ensure_ascii=False)
    return {HEADER_USER_CTX: header_value}


def openai_messages_to_chatty(messages: list) -> list:
    """将 OpenAI 格式的 messages 转为 Chatty Message 列表。"""
    chatty_messages = []
    for msg in messages:
        role = _openai_role_to_chatty(msg.get("role", "user"))
        content = msg.get("content")
        contents = _content_to_chatty_contents(content) if content else []
        # reasoning_content 单独作为 ContentItem
        if msg.get("reasoning_content"):
            contents.append(
                message_pb2.ContentItem(reasoning_content=msg["reasoning_content"])
            )
        if not contents and role != message_pb2.tool:
            contents = [message_pb2.ContentItem(text="")]
        m = message_pb2.Message(role=role, contents=contents)
        if msg.get("tool_calls"):
            m.tool_calls.extend(_openai_tool_calls_to_chatty(msg["tool_calls"]))
        if msg.get("tool_call_id"):
            m.tool_call_id = msg["tool_call_id"]
        chatty_messages.append(m)
    return chatty_messages


async def replay_request_chatty(
    request_data: dict,
    *,
    base_url: str = CHATTY_BASE_URL,
    workflow: int = DEFAULT_WORKFLOW,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
    enable_think: bool = False,
    enable_memory: bool = False,
) -> dict:
    """
    使用 Chatty 流式 API 回放单次请求，收集完整响应后返回与 replay 兼容的 response 结构。

    request_data: OpenAI 兼容的 request dict（model, messages, tools, max_tokens, temperature 等）
    user_id: 可选，传入后通过 X-Msh-User-Ctx 传给 Chatty，用于 memory 等需要用户身份的能力。
    返回: {"content": str, "reasoning_content": str, "tool_calls": [...], "finish_reason": str, "usage": ...}
    """
    messages = request_data.get("messages", [])
    chatty_messages = openai_messages_to_chatty(messages)

    options = ChattyRequestOptions()
    if chat_id:
        options.chat_id = chat_id
    options.search.enable = True
    if enable_memory:
        options.memory.enable_semantic = True
        options.memory.enable_episodic = True
    if enable_think:
        options.enable_think = True

    request = ChattyRequest(
        workflow=workflow,
        messages=chatty_messages,
        options=options,
    )

    headers = build_user_ctx_headers(user_id) if user_id else {}
    headers = dict(headers) if headers else {}

    client = ChattyServiceClient(base_url)
    full_content = ""
    full_reasoning = ""
    finish_reason = None
    usage = None
    tool_calls = []
    tool_events = []
    ordered_stream = []  # 按到达顺序：content 与 tool_event 交错
    content_buffer = ""

    def flush_content():
        nonlocal content_buffer
        if content_buffer:
            ordered_stream.append({"type": "content", "text": content_buffer})
            content_buffer = ""

    with _tracer.start_as_current_span("replay_request_chatty") as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
        _trace_propagator.inject(headers)

        try:
            stream = client.chat_workflow_stream(request, headers=headers)
            async for response in stream:
                if not hasattr(response, "type"):
                    continue
                event_type = response.type

                parsed = parse_tool_event(response)
                if parsed is not None:
                    flush_content()
                    tool_events.append(parsed)
                    ordered_stream.append({"type": "tool_event", "event": parsed})

                if event_type == EVENT_TYPE_MODEL_TEXT:
                    if hasattr(response, "model_text") and response.model_text.HasField("delta"):
                        delta = response.model_text.delta
                        if delta.content:
                            full_content += delta.content
                            content_buffer += delta.content

                elif event_type == EVENT_TYPE_MODEL_REASONING:
                    if hasattr(response, "model_reasoning") and response.model_reasoning.HasField("delta"):
                        delta = response.model_reasoning.delta
                        if delta.content:
                            full_reasoning += delta.content

                elif event_type == EVENT_TYPE_MODEL_END:
                    if hasattr(response, "model_end") and response.model_end.HasField("response"):
                        end_resp = response.model_end.response
                        if end_resp.finish_reason:
                            finish_reason = end_resp.finish_reason
                        if end_resp.HasField("usage"):
                            usage = {
                                "prompt_tokens": end_resp.usage.prompt_tokens,
                                "completion_tokens": end_resp.usage.completion_tokens,
                                "total_tokens": end_resp.usage.total_tokens,
                            }
                        if end_resp.HasField("message") and end_resp.message:
                            model_end_message = end_resp.message  # noqa: F841
                            for tc in end_resp.message.tool_calls:
                                func = tc.function if tc.HasField("function") else None
                                tool_calls.append({
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": func.name if func else "",
                                        "arguments": func.arguments if func else "",
                                    },
                                })
            flush_content()
        except Exception as e:
            span.record_exception(e)
            return {
                "content": full_content,
                "reasoning_content": full_reasoning,
                "tool_calls": tool_calls,
                "tool_events": tool_events,
                "ordered_stream": ordered_stream,
                "finish_reason": finish_reason or "error",
                "usage": usage,
                "error": str(e),
                "trace_id": trace_id,
            }

    return {
        "content": full_content,
        "reasoning_content": full_reasoning,
        "tool_calls": tool_calls,
        "tool_events": tool_events,
        "ordered_stream": ordered_stream,
        "finish_reason": finish_reason or "stop",
        "usage": usage,
        "trace_id": trace_id,
    }


def extract_content_chatty(response: dict) -> str:
    """从 Chatty 收集的 response 中提取可比较的文本（与 replay.extract_content 一致）。"""
    return extract_content(response)


def compare_responses_chatty(original: dict, replayed: dict) -> dict:
    """对比原始与 Chatty 回放响应。"""
    return compare_responses(original, replayed)


def get_conversation_order_trajectories(trace: dict) -> list[dict]:
    """
    基于 trace 中的 turn_index，返回按「实际对话顺序」排列的 trajectories。

    设计目标：
    - 用户看到的 Turn 0 = 对话中的「第一轮」；
    - Turn 1 = 第二轮，以此类推；
    - --list 展示的顺序、--turn 指定的索引，以及「逐个回放所有 turn」的顺序保持一致。

    注意：trace 内部的 turn_index 语义可能与用户期望不同，这里通过统一排序 +
    映射，提供一个对用户友好的顺序。
    当前实现假定：turn_index 越大，代表在对话中越早的一轮，因此按 turn_index
    降序排列即可得到从「第一轮」到「最后一轮」的顺序。
    如有需要，可根据实际 trace 规范调整排序规则。
    """
    trajectories = trace.get("model_trajectories", []) or []
    return sorted(trajectories, key=lambda t: t.get("turn_index", 0), reverse=True)


async def replay_turn_chatty(
    trace: dict,
    turn_index: int,
    step_index: Optional[int] = None,
    verbose: bool = True,
    base_url: str = CHATTY_BASE_URL,
    workflow: int = DEFAULT_WORKFLOW,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
    enable_think: bool = False,
    enable_memory: bool = False,
) -> list:
    """
    使用 Chatty 回放指定 turn（及可选的单步）。
    """
    trajectories = trace.get("model_trajectories", [])
    turn_trajectory = None
    for traj in trajectories:
        if traj.get("turn_index") == turn_index:
            turn_trajectory = traj
            break

    if not turn_trajectory:
        raise ValueError(f"Turn {turn_index} not found in trace")

    model_requests = turn_trajectory.get("model_requests", [])
    results = []
    cid = chat_id or trace.get("chat_id")

    for i, request_data in enumerate(model_requests):
        if step_index is not None and i != step_index:
            continue

        if verbose:
            print(f"\n{'='*60}")
            print(f"Turn {turn_index}, Step {i} (Chatty)")
            print("=" * 60)

        request = request_data.get("request", {})
        original_response = request_data.get("response", {})

        if verbose:
            messages = request.get("messages", [])
            print(f"Model: {request.get('model')}, Messages: {len(messages)}")
            if messages:
                last = messages[-1]
                role = last.get("role", "unknown")
                content = last.get("content", "")
                preview = (content[:100] + "...") if isinstance(content, str) and len(content) > 100 else str(content)[:100]
                print(f"Last message ({role}): {preview}")

        try:
            if verbose:
                print("\nReplaying via Chatty stream...")
            replayed_response = await replay_request_chatty(
                request,
                base_url=base_url,
                workflow=workflow,
                chat_id=cid,
                user_id=user_id,
                enable_think=enable_think,
                enable_memory=enable_memory,
            )

            comparison = compare_responses_chatty(original_response, replayed_response)
            comparison["turn_index"] = turn_index
            comparison["step_index"] = i
            comparison["request_model"] = request.get("model")
            comparison["replayed_via"] = "chatty"
            comparison["trace_id"] = replayed_response.get("trace_id")
            comparison["replayed_tool_events"] = replayed_response.get("tool_events") or []
            comparison["replayed_stream_order"] = replayed_response.get("ordered_stream") or []
            results.append(comparison)

            if verbose:
                tid = replayed_response.get("trace_id") or "N/A"
                print(f"\n  trace_id: {tid}")
                print("\n--- Original ---")
                print(comparison["original"])
                print("\n--- Replayed (Chatty, stream order) ---")
                print(format_ordered_stream_display(comparison.get("replayed_stream_order") or []))
                # 展示 model_end 里的 tool_calls 与流式 tool 事件数量（便于排查无 tool 显示问题）
                replayed_tool_calls = replayed_response.get("tool_calls") or []
                replayed_tool_events = replayed_response.get("tool_events") or []
                if replayed_tool_calls:
                    print("\n  Tool calls (model_end):")
                    for tc in replayed_tool_calls:
                        fn = tc.get("function") or {}
                        print(f"    - {fn.get('name', '')}({fn.get('arguments', '')})")
                print(f"  Tool events (stream): {len(replayed_tool_events)}")
                print(f"\n--- Match: {comparison['match']} ---")
        except Exception as e:
            if verbose:
                print(f"Error: {e}")
            results.append({
                "turn_index": turn_index,
                "step_index": i,
                "error": str(e),
            })

    return results


async def replay_from_step_chatty(
    trace_data: dict,
    turn_idx: int,
    step_idx: int,
    max_steps: int = 10,
    save_dir: str = "chatlet/replay_chatty",
    base_url: str = CHATTY_BASE_URL,
    workflow: int = DEFAULT_WORKFLOW,
    user_id: Optional[str] = None,
    enable_think: bool = False,
    enable_memory: bool = False,
) -> dict:
    """
    从指定 step 开始用 Chatty 回放完整对话（多轮 tool 调用）。
    """
    chat_id = trace_data.get("chat_id", "unknown")
    trajectories = trace_data.get("model_trajectories", [])

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

    original_steps = []
    for i, req in enumerate(model_requests):
        original_steps.append({
            "step_index": i,
            "response": req.get("response", {}),
            "request_model": req.get("request", {}).get("model"),
        })

    branch_request = model_requests[step_idx].get("request", {})
    current_messages = copy.deepcopy(branch_request.get("messages", []))
    replayed_steps = []
    replay_step_count = 0

    while replay_step_count < max_steps:
        try:
            request_data = {
                "model": branch_request.get("model"),
                "messages": current_messages,
            }
            response = await replay_request_chatty(
                request_data,
                base_url=base_url,
                workflow=workflow,
                chat_id=chat_id,
                user_id=user_id,
                enable_think=enable_think,
                enable_memory=enable_memory,
            )

            message = {
                "content": response.get("content") or None,
                "reasoning_content": response.get("reasoning_content") or None,
                "tool_calls": response.get("tool_calls") or [],
            }
            finish_reason = response.get("finish_reason")
            step_trace_id = response.get("trace_id")

            replayed_steps.append({
                "step_index": replay_step_count,
                "response": message,
                "finish_reason": finish_reason,
                "trace_id": step_trace_id,
            })

            replay_step_count += 1
            if finish_reason == "stop" or not message.get("tool_calls"):
                break

            assistant_msg = {
                "role": "assistant",
                "content": message.get("content") or None,
                "tool_calls": message.get("tool_calls"),
            }
            current_messages.append(assistant_msg)

            original_step_for_tool = step_idx + replay_step_count - 1
            tool_results = find_original_tool_results(model_requests, original_step_for_tool)
            if not tool_results:
                break
            current_messages.extend(tool_results)

        except Exception as e:
            replayed_steps.append({"step_index": replay_step_count, "error": str(e)})
            break

    save_path = Path(save_dir) / datetime.now().strftime("%Y-%m-%d")
    save_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{timestamp}_{chat_id}_branch_{turn_idx+1}-{step_idx+1}_chatty.json"
    filepath = save_path / filename
    result = {
        "chat_id": chat_id,
        "turn": turn_idx + 1,
        "branch_step": step_idx + 1,
        "timestamp": timestamp,
        "original_steps": original_steps,
        "replayed_steps": replayed_steps,
        "via": "chatty",
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return {
        "success": True,
        "original_steps": original_steps,
        "replayed_steps": replayed_steps,
        "branch_step_idx": step_idx,
        "saved_file": str(filepath),
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="使用 Chatty 流式 API 回放 trace（replay 的 Chatty 版本）"
    )
    parser.add_argument("trace_file", help="Trace JSON 文件路径")
    parser.add_argument("--turn", type=int, help="只回放指定 turn index")
    parser.add_argument("--step", type=int, help="只回放指定 step（需配合 --turn）")
    parser.add_argument("--output", "-o", help="将对比结果写入 JSON 文件")
    parser.add_argument("--quiet", "-q", action="store_true", help="少输出")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有 turn 和 step 数量")
    parser.add_argument("--workflow", type=int, default=DEFAULT_WORKFLOW, help=f"Chatty workflow id，默认 {DEFAULT_WORKFLOW}")
    parser.add_argument("--url", default=CHATTY_BASE_URL, help=f"Chatty 服务 URL，默认 {CHATTY_BASE_URL}")
    parser.add_argument("--user-id", dest="user_id", help="用户 ID，通过 X-Msh-User-Ctx 传给 Chatty，用于 memory 等能力")
    parser.add_argument("--think", action="store_true", help="开启 thinking 模式（默认 instruct / no think）")
    parser.add_argument("--memory", action="store_true", help="开启记忆能力（语义 + 情景记忆，默认关闭）")
    return parser.parse_args(), parser


async def main_async():
    args, parser = parse_args()
    trace = load_trace(args.trace_file)
    if not isinstance(trace, dict) or "model_trajectories" not in trace:
        print("Error: need a trace JSON (with model_trajectories), not a conversation JSON.", file=sys.stderr)
        print("Use a file from chatlet/trace/ (e.g. get_message.py --dev --trace <chat_id>).", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded trace: {trace.get('chat_id', 'unknown')} (Chatty replay)")

    trajectories = trace.get("model_trajectories", []) or []  # noqa: F841
    ordered_trajectories = get_conversation_order_trajectories(trace)

    if args.list:
        print("\nAvailable trajectories (conversation order):")
        # 用户可见的 Turn 索引：从 0 开始，按实际对话顺序递增；
        # 同时展示 trace 内部的 turn_index 便于排查。
        for i, traj in enumerate(ordered_trajectories):
            trace_turn_idx = traj.get("turn_index")
            num_requests = len(traj.get("model_requests", []))
            print(f"  Turn {i} (trace_turn={trace_turn_idx}): {num_requests} step(s)")
        return

    if args.step is not None and args.turn is None:
        parser.error("--step requires --turn")

    all_results = []
    verbose = not args.quiet

    # user_id 优先级：--user-id > .env > None
    # 不再自动反查原始用户 ID，避免影响线上用户
    user_id = getattr(args, "user_id", None)
    if not user_id:
        is_prod = "prod" in (args.url or "")
        env_key = "CHATTY_REPLAY_PROD_USER_ID" if is_prod else "CHATTY_REPLAY_TEST_USER_ID"
        user_id = os.environ.get(env_key)
        if user_id and verbose:
            print(f"Using user_id from .env ({env_key}): {user_id}")
    if not user_id and verbose:
        print("Warning: no user_id configured. Set CHATTY_REPLAY_TEST_USER_ID in .env or use --user-id")

    if args.turn is not None:
        # 用户指定的 --turn 是「对话顺序索引」，需要先映射回 trace 的 turn_index
        if args.turn < 0 or args.turn >= len(ordered_trajectories):
            parser.error(f"--turn {args.turn} out of range (0-{len(ordered_trajectories) - 1})")
        target_traj = ordered_trajectories[args.turn]
        trace_turn_index = target_traj.get("turn_index")

        results = await replay_turn_chatty(
            trace,
            trace_turn_index,
            args.step,
            verbose=verbose,
            base_url=args.url,
            workflow=args.workflow,
            chat_id=trace.get("chat_id"),
            user_id=user_id,
            enable_think=args.think,
            enable_memory=args.memory,
        )
        all_results.extend(results)
    else:
        # 未指定 --turn 时，按「对话顺序索引」从头到尾依次回放
        for i, traj in enumerate(ordered_trajectories):
            trace_turn_index = traj.get("turn_index")
            results = await replay_turn_chatty(
                trace,
                trace_turn_index,
                None,
                verbose=verbose,
                base_url=args.url,
                workflow=args.workflow,
                chat_id=trace.get("chat_id"),
                user_id=user_id,
                enable_think=args.think,
                enable_memory=args.memory,
            )
            all_results.extend(results)

    print(f"\n{'='*60}")
    print("SUMMARY (Chatty)")
    print("=" * 60)
    total = len(all_results)
    errors = sum(1 for r in all_results if "error" in r)
    matches = sum(1 for r in all_results if r.get("match", False))
    print(f"Total steps: {total}")
    print(f"Errors: {errors}")
    print(f"Matches: {matches}/{total - errors}" if total > errors else "Matches: N/A")

    # 确定输出路径：指定了 -o 就用 -o，否则默认保存到 replay_chatty_data/
    if args.output:
        out_path = Path(args.output)
    else:
        chat_id = trace.get("chat_id", "unknown")
        default_dir = Path("replay_chatty_data") / datetime.now().strftime("%Y-%m-%d")
        default_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%H%M%S")
        out_path = default_dir / f"{timestamp}_{chat_id}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "trace_file": args.trace_file,
            "chat_id": trace.get("chat_id"),
            "via": "chatty",
            "results": all_results,
            "summary": {"total": total, "errors": errors, "matches": matches},
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
