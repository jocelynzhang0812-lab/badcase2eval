#!/usr/bin/env python3
"""
Batch Chatty 脚本

从指定 dataset（如 batch/bench.csv）读取样本，组装成 message，
调用 Chatty 流式 API。所有 Chatty 调用逻辑自包含，不依赖 replay_chatty.py。
"""

import argparse
import asyncio
import csv
import json
import os
import sys
import uuid
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

# ---------- 常量 ----------

HEADER_USER_CTX = "X-Msh-User-Ctx"
CHATTY_BASE_URL = os.environ.get("CHATTY_REPLAY_TEST_BASE_URL", "https://chatty.dev.AI_Platform.team")
DEFAULT_WORKFLOW = 16  # WORKFLOW_K2D5

EVENT_TYPE_MODEL_TEXT = response_stream_pb2.EVENT_TYPE_MODEL_TEXT
EVENT_TYPE_MODEL_REASONING = response_stream_pb2.EVENT_TYPE_MODEL_REASONING
EVENT_TYPE_MODEL_END = response_stream_pb2.EVENT_TYPE_MODEL_END
EVENT_TYPE_TOOL_START = response_stream_pb2.EVENT_TYPE_TOOL_START
EVENT_TYPE_TOOL_END = response_stream_pb2.EVENT_TYPE_TOOL_END
EVENT_TYPE_SEARCH_IN_PROGRESS = response_stream_pb2.EVENT_TYPE_SEARCH_IN_PROGRESS
EVENT_TYPE_SEARCH_START = response_stream_pb2.EVENT_TYPE_SEARCH_START
EVENT_TYPE_SEARCH_END = response_stream_pb2.EVENT_TYPE_SEARCH_END

# ---------- OpenTelemetry Trace 辅助 ----------

_trace_provider = TracerProvider(sampler=ALWAYS_ON)
_tracer = _trace_provider.get_tracer(__name__)
_trace_propagator = TraceContextTextMapPropagator()

# ---------- protobuf → dict 序列化辅助 ----------


def _content_item_to_dict(item) -> dict:
    """将 ContentItem 转为可 JSON 序列化的 dict。"""
    text = getattr(item, "text", None) or ""
    d: dict = {"text": text}
    if getattr(item, "reasoning_content", None):
        d["reasoning_content"] = item.reasoning_content
    try:
        has = getattr(item, "HasField", None)
        if has and callable(has):
            if has("image") and getattr(item, "image", None):
                d["image"] = {"file_id": getattr(item.image, "file_id", ""), "url": getattr(item.image, "url", "")}
            if has("file") and getattr(item, "file", None):
                d["file"] = {"file_id": getattr(item.file, "file_id", "")}
    except Exception:
        pass
    return d


def _tool_content_to_dict(tc) -> dict:
    """将 ToolContent 转为可 JSON 序列化的 dict（web search 展示内容常用）。"""
    text = getattr(tc, "text", None) or ""
    d: dict = {"text": text}
    try:
        has = getattr(tc, "HasField", None)
        if has and callable(has) and has("resource_link"):
            rl = getattr(tc, "resource_link", None)
            if rl is not None:
                d["resource_link"] = {
                    "url": getattr(rl, "url", "") or "",
                    "title": getattr(rl, "title", "") or "",
                }
    except Exception:
        pass
    return d


def _message_to_dict(msg) -> dict:
    """将 Message 转为可 JSON 序列化的 dict（role, contents, tool_calls）。"""
    if msg is None:
        return {}
    role = getattr(msg, "role", None)
    out: dict = {
        "role": int(role) if role is not None else 0,
        "contents": [],
        "tool_calls": [],
    }
    try:
        if getattr(msg, "contents", None):
            out["contents"] = [_content_item_to_dict(c) for c in msg.contents]
    except Exception:
        pass
    try:
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                has = getattr(tc, "HasField", None)
                func = tc.function if (has and callable(has) and has("function")) else None
                out["tool_calls"].append({
                    "id": getattr(tc, "id", "") or "",
                    "type": "function",
                    "function": {
                        "name": (getattr(func, "name", "") or "") if func else "",
                        "arguments": (getattr(func, "arguments", "") or "") if func else "",
                    },
                })
    except Exception:
        pass
    return out


def _tool_end_to_dict(e) -> dict:
    """将 tool_end 事件转为可 JSON 序列化的 dict。"""
    out: dict = {
        "type": "tool_end",
        "tool_call_id": getattr(e, "tool_call_id", "") or "",
        "result": e.result or "",
        "is_error": bool(e.is_error),
    }
    try:
        out["display_contents"] = [_tool_content_to_dict(c) for c in e.display_contents] if getattr(e, "display_contents", None) else []
    except Exception:
        out["display_contents"] = []
    try:
        out["result_parts"] = [_content_item_to_dict(p) for p in e.result_parts] if getattr(e, "result_parts", None) else []
    except Exception:
        out["result_parts"] = []
    return out


# ---------- OpenAI messages → Chatty protobuf ----------


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
            elif isinstance(block, str) and block.strip():
                items.append(message_pb2.ContentItem(text=block))
    return items


def _openai_tool_calls_to_chatty(tool_calls: list) -> list:
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


def _openai_messages_to_chatty(messages: list) -> list:
    chatty_messages = []
    for msg in messages:
        role = _openai_role_to_chatty(msg.get("role", "user"))
        content = msg.get("content")
        contents = _content_to_chatty_contents(content) if content else []
        if msg.get("reasoning_content"):
            contents.append(message_pb2.ContentItem(reasoning_content=msg["reasoning_content"]))
        if not contents and role != message_pb2.tool:
            contents = [message_pb2.ContentItem(text="")]
        m = message_pb2.Message(role=role, contents=contents)
        if msg.get("tool_calls"):
            m.tool_calls.extend(_openai_tool_calls_to_chatty(msg["tool_calls"]))
        if msg.get("tool_call_id"):
            m.tool_call_id = msg["tool_call_id"]
        chatty_messages.append(m)
    return chatty_messages


def _build_user_ctx_headers(user_id: str, *, language: str = "zh-CN") -> dict[str, str]:
    ctx = user_context_pb2.UserContext()
    ctx.user_id = user_id
    if language:
        ctx.language = language
    raw_json = MessageToJson(ctx)
    header_value = json.dumps(json.loads(raw_json), separators=(",", ":"), ensure_ascii=False)
    return {HEADER_USER_CTX: header_value}


# ---------- Chatty 流式调用（收集 model_end / tool_end 有序列表） ----------


async def call_chatty_stream(
    messages: list[dict],
    *,
    base_url: str = CHATTY_BASE_URL,
    workflow: int = DEFAULT_WORKFLOW,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
    enable_think: bool = False,
    enable_memory: bool = False,
    enable_search: bool = True,
    timeout_ms: Optional[int] = None,
) -> dict:
    """
    调用 Chatty 流式 API，收集完整响应。
    返回 {"output": [...], "error": str|None}。
    output 为按到达顺序排列的 model_end、tool_end 事件列表。
    """
    chatty_messages = _openai_messages_to_chatty(messages)

    options = ChattyRequestOptions()
    if chat_id:
        options.chat_id = chat_id
    options.search.enable = enable_search
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

    headers = _build_user_ctx_headers(user_id) if user_id else {}
    headers = dict(headers) if headers else {}

    client = ChattyServiceClient(base_url, timeout_ms=timeout_ms)
    output: list[dict] = []  # 按顺序的 model_end / tool_end

    with _tracer.start_as_current_span("call_chatty_stream") as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
        _trace_propagator.inject(headers)

        try:
            stream = client.chat_workflow_stream(request, headers=headers)
            async for response in stream:
                if not hasattr(response, "type"):
                    continue
                event_type = response.type

                # ---------- tool_end ----------
                has = getattr(response, "HasField", None)
                if callable(has) and has("tool_end"):
                    output.append(_tool_end_to_dict(response.tool_end))
                    continue

                # ---------- model_end ----------
                if event_type == EVENT_TYPE_MODEL_END:
                    if hasattr(response, "model_end") and response.model_end.HasField("response"):
                        end_resp = response.model_end.response
                        finish_reason = end_resp.finish_reason or None
                        usage = None
                        if end_resp.HasField("usage"):
                            usage = {
                                "prompt_tokens": end_resp.usage.prompt_tokens,
                                "completion_tokens": end_resp.usage.completion_tokens,
                                "total_tokens": end_resp.usage.total_tokens,
                            }
                        message_dict = {}
                        if end_resp.HasField("message") and end_resp.message:
                            message_dict = _message_to_dict(end_resp.message)
                        output.append({
                            "type": "model_end",
                            "finish_reason": finish_reason,
                            "usage": usage,
                            "message": message_dict,
                        })

        except Exception as e:
            span.record_exception(e)
            return {"output": output, "error": str(e), "trace_id": trace_id}

    return {"output": output, "error": None, "trace_id": trace_id}


# ---------- Dataset 加载 ----------


def normalize_dataset_path(path: str) -> Path:
    """支持 batch/bench.csv 或 @batch/bench.csv 等形式，去掉首字符 @。"""
    p = path.strip()
    if p.startswith("@"):
        p = p[1:]
    return Path(p)


def load_dataset(dataset_path: Path, query_column: str = "query") -> list[dict]:
    """
    从 CSV 加载 dataset。每行一个样本。
    - 若首行是表头且含 query 列（或 prompt/message 等），则用该列作为用户消息；
    - 否则认为无表头，第一列作为用户消息。
    返回 list[dict]，每项至少含 "content"（用户消息），可选 "system"。
    """
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    rows: list[dict] = []
    with open(dataset_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        raw_rows = list(reader)

    if not raw_rows:
        return []

    first = raw_rows[0]
    has_header = (
        len(first) >= 1
        and first[0].strip().lower() in ("prompt", "query", "message", "content", "user", "input")
    )
    if not has_header and len(first) >= 1:
        header_candidates = [c.strip().lower() for c in first]
        if query_column.lower() in header_candidates:
            has_header = True

    if has_header:
        header = [c.strip() for c in first]
        data_rows = raw_rows[1:]
        content_col = 0 if header[0].lower() == query_column.lower() else None
        if content_col is None:
            for name in ("query", "prompt", "message", "content", "user", "input"):
                if name in [h.lower() for h in header]:
                    idx = next(i for i, h in enumerate(header) if h.lower() == name)
                    content_col = idx
                    break
        if content_col is None:
            content_col = 0
        system_col = None
        for i, h in enumerate(header):
            if h.strip().lower() == "system":
                system_col = i
                break

        for row in data_rows:
            if len(row) <= content_col:
                continue
            content = row[content_col].strip()
            if not content:
                continue
            item: dict = {"content": content}
            if system_col is not None and len(row) > system_col and row[system_col].strip():
                item["system"] = row[system_col].strip()
            rows.append(item)
    else:
        for row in raw_rows:
            if not row:
                continue
            content = (row[0] or "").strip()
            if not content:
                continue
            rows.append({"content": content})

    return rows


def build_messages(sample: dict) -> list[dict]:
    """将 dataset 的一行组装成 OpenAI 格式 messages。"""
    messages: list[dict] = []
    if sample.get("system"):
        messages.append({"role": "system", "content": sample["system"]})
    messages.append({"role": "user", "content": sample["content"]})
    return messages


def default_output_dir(dataset_path: Path) -> Path:
    return dataset_path.parent / f"{dataset_path.stem}_chatty"


# ---------- 单条 / 批量执行 ----------


async def run_one(
    index: int,
    sample: dict,
    *,
    base_url: str = CHATTY_BASE_URL,
    workflow: int = DEFAULT_WORKFLOW,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
    enable_think: bool = False,
    enable_memory: bool = False,
    enable_search: bool = True,
    timeout_ms: Optional[int] = None,
) -> dict:
    """对单条样本调用 Chatty，返回 {index, query, output, error}。"""
    messages = build_messages(sample)
    query = sample["content"]

    # 每条请求随机生成 chat_id（除非外部显式指定）
    if not chat_id:
        chat_id = str(uuid.uuid4())

    try:
        resp = await call_chatty_stream(
            messages,
            base_url=base_url,
            workflow=workflow,
            chat_id=chat_id,
            user_id=user_id,
            enable_think=enable_think,
            enable_memory=enable_memory,
            enable_search=enable_search,
            timeout_ms=timeout_ms,
        )
        return {
            "index": index,
            "query": query,
            "chat_id": chat_id,
            "output": resp.get("output", []),
            "error": resp.get("error"),
            "trace_id": resp.get("trace_id"),
        }
    except Exception as e:
        return {
            "index": index,
            "query": query,
            "chat_id": chat_id,
            "output": [],
            "error": str(e),
            "trace_id": None,
        }


async def run_batch(
    dataset_path: Path,
    *,
    base_url: str = CHATTY_BASE_URL,
    workflow: int = DEFAULT_WORKFLOW,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
    enable_think: bool = False,
    enable_memory: bool = False,
    enable_search: bool = True,
    output: Optional[Path] = None,
    verbose: bool = True,
    concurrency: int = 10,
    try_run: bool = False,
    timeout_ms: Optional[int] = None,
    limit: int = 0,
) -> list[dict]:
    """加载 dataset，并发调用 Chatty，汇总结果并写文件。"""
    concurrency = min(concurrency, 10)  # 最多 10 并发

    samples = load_dataset(dataset_path)
    if not samples:
        print("No samples in dataset.", file=sys.stderr)
        return []

    if try_run:
        samples = samples[:1]
        if verbose:
            print(f"Try mode: only 1 sample from {dataset_path}")
    elif limit and limit > 0:
        samples = samples[:limit]

    if verbose:
        print(f"Dataset: {dataset_path}, samples: {len(samples)}, concurrency: {concurrency}")

    out_dir = Path(output) if output else default_output_dir(dataset_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(concurrency)
    total = len(samples)
    done_count = 0
    ok_count = 0
    fail_count = 0
    results: list[dict] = []

    async def run_and_save(i: int, sample: dict) -> dict:
        nonlocal done_count, ok_count, fail_count
        async with sem:
            r = await run_one(
                i,
                sample,
                base_url=base_url,
                workflow=workflow,
                chat_id=chat_id,
                user_id=user_id,
                enable_think=enable_think,
                enable_memory=enable_memory,
                enable_search=enable_search,
                timeout_ms=timeout_ms,
            )
        # 立即写文件
        path = out_dir / f"{r['index']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)
        done_count += 1
        is_ok = not r.get("error")
        if is_ok:
            ok_count += 1
        else:
            fail_count += 1
        if verbose:
            query = r.get("query") or ""
            preview = (query[:60] + "") if len(query) > 60 else query
            ok = "OK" if is_ok else "FAIL"
            tid = r.get("trace_id") or "N/A"
            print(f"[{done_count}/{total}] #{r['index']} {preview} | {ok} | trace_id={tid} | {path}", flush=True)
        return r

    tasks = [run_and_save(i, s) for i, s in enumerate(samples)]
    results = list(await asyncio.gather(*tasks, return_exceptions=False))

    if verbose:
        print(f"Done: {out_dir}/ ({ok_count} ok, {fail_count} fail, {total} total)")

    return results


# ---------- CLI ----------


def parse_args():
    parser = argparse.ArgumentParser(
        description="从 dataset CSV 组装 message 并调用 Chatty"
    )
    parser.add_argument("dataset", help="Dataset 路径，如 batch/data.csv 或 @batch/data.csv")
    parser.add_argument("--output", "-o", help="结果输出目录")
    parser.add_argument("--quiet", "-q", action="store_true", help="少输出")
    parser.add_argument("--try", dest="try_run", action="store_true", help="试跑模式：只跑第一条")
    parser.add_argument("--concurrency", "-j", type=int, default=10, help="最大并发数（默认 10）")
    parser.add_argument("--workflow", type=int, default=DEFAULT_WORKFLOW, help=f"Chatty workflow id（默认 {DEFAULT_WORKFLOW}）")
    parser.add_argument("--url", default=CHATTY_BASE_URL, help="Chatty 服务 URL")
    parser.add_argument("--chat-id", dest="chat_id", help="Chat ID")
    parser.add_argument("--user-id", dest="user_id", help="用户 ID（X-Msh-User-Ctx）")
    parser.add_argument("--think", action="store_true", help="开启 thinking 模式")
    parser.add_argument("--memory", action="store_true", help="开启记忆能力")
    parser.add_argument("--no-search", dest="enable_search", action="store_false", help="关闭搜索（默认开启）")
    parser.add_argument("--timeout", type=int, default=600000, help="单次请求超时（毫秒，默认 600000 = 10 分钟）")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（默认 0 = 全部）")
    return parser.parse_args()


async def main_async():
    args = parse_args()
    dataset_path = normalize_dataset_path(args.dataset)

    user_id = getattr(args, "user_id", None)
    if not user_id:
        user_id = os.environ.get("CHATTY_REPLAY_TEST_USER_ID")

    await run_batch(
        dataset_path,
        base_url=args.url,
        workflow=args.workflow,
        chat_id=getattr(args, "chat_id", None),
        user_id=user_id,
        enable_think=args.think,
        enable_memory=args.memory,
        enable_search=getattr(args, "enable_search", True),
        output=Path(args.output) if args.output else None,
        verbose=not args.quiet,
        concurrency=args.concurrency,
        try_run=getattr(args, "try_run", False),
        timeout_ms=args.timeout,
        limit=args.limit,
    )


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
