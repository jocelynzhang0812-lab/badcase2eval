#!/usr/bin/env python3
"""
获取 chatlet 的对话和 trace 数据

用法:
    python get_message.py --dev --trace <chat_id>        # 保存完整 trace
    python get_message.py --dev --conversation <chat_id> # 保存对话
    python get_message.py --dev --trace --conversation <chat_id>  # 两个都保存
"""

from pathlib import Path
import httpx
import argparse
import json
import os
import time
import asyncio

CHATLET_TEST_BASE_URL = "https://chatlet.dev.AI_Platform.team"
CHATLET_PROD_BASE_URL = "https://internal.company.com"

FILE_DOWNLOAD = False

def resolve_chat_id(input_str: str) -> str:
    """支持 chat_id / share_id / share link，统一转为 chat_id"""
    import re
    # share link: https://www.AI_Platform.com/share/<share_id>
    m = re.search(r'/share/([0-9a-f-]+)', input_str)
    if m:
        share_id = m.group(1)
        print(f" 检测到 share link，share_id: {share_id}")
        return _share_id_to_chat_id(share_id)
    # 如果看起来像 UUID 但不是 chat_id 格式（share_id 也是 UUID），先尝试当 chat_id 用
    # 如果失败再当 share_id 转
    return input_str


def _share_id_to_chat_id(share_id: str) -> str:
    """调用 chatlet reflect API 将 share_id 转为 chat_id"""
    url = f"{BASE_URL}/api/chats:reflect?share_id={share_id}"
    response = get_with_retry(url)
    if response:
        data = response.json()
        chat_id = data.get("chatId", "")
        if chat_id:
            print(f" share_id → chat_id: {chat_id}")
            return chat_id
    print(f" share_id {share_id} 转换失败，尝试直接当 chat_id 使用")
    return share_id
HEADERS = {
    "X-AuthGateway-Access-Token": os.environ.get("AuthGateway_ACCESS_TOKEN", "")
}

# 禁用代理，内网直连
HTTP_CLIENT = httpx.Client(trust_env=False, timeout=600)

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 1.0

# 当前使用的环境
BASE_URL = CHATLET_TEST_BASE_URL
VERBOSE = False


def get_with_retry(url: str) -> httpx.Response | None:
    """带重试的 GET 请求"""
    for attempt in range(MAX_RETRIES):
        try:
            response = HTTP_CLIENT.get(url, headers=HEADERS)
            if response.status_code == 200:
                return response
            if VERBOSE:
                print(f"  ️ 请求失败 (attempt {attempt+1}/{MAX_RETRIES}): {response.status_code}")
                print(f"      {response.text[:200]}")
        except Exception as e:
            if VERBOSE:
                print(f"  ️ 请求异常 (attempt {attempt+1}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    return None


def get_chat_user_id(chat_id: str) -> str | None:
    """从 chat API 获取 userId"""
    url = f"{BASE_URL}/api/v2/chats/{chat_id}"
    response = get_with_retry(url)
    if not response:
        return None
    try:
        data = response.json()
        return data.get("chat", {}).get("meta", {}).get("userId")
    except Exception:
        return None


def get_message_ids(chat_id: str) -> list | None:
    """获取 chat 中所有 assistant 消息的 segment_id（自动分页）"""
    assistant_messages = []
    page_token = None

    while True:
        url = f"{BASE_URL}/api/v2/chats/{chat_id}/messages"
        if page_token:
            url += f"?pageToken={page_token}"
        response = get_with_retry(url)
        if not response:
            if not assistant_messages:
                print(f" 获取消息列表失败 (重试 {MAX_RETRIES} 次后)")
                return None
            break

        data = response.json()
        entries = data.get('messageEntries', [])
        if not entries:
            break

        for entry in entries:
            msg = entry.get('message', {})
            meta = msg.get('meta', {})
            if meta.get('role') == 'assistant':
                assistant_messages.append({
                    "segment_id": meta.get('id'),
                })
            if meta.get('role') == 'user' and FILE_DOWNLOAD:
                download_file(meta.get('id'))

        next_token = data.get('nextPageToken')
        if not next_token:
            break
        page_token = next_token

    # API 返回倒序（最新在前），翻转为正序（Turn 0 = 最早）
    assistant_messages.reverse()
    for i, msg in enumerate(assistant_messages):
        msg["turn_index"] = i

    return assistant_messages if assistant_messages else None

def download_file(segment_id: str) -> None:
    """下载用户上传的file"""
    url = f"{BASE_URL}/api/v2/chats/-/messages/{segment_id}"
    response = get_with_retry(url)
    if not response:
        print(f"   获取 segment 信息失败 (重试 {MAX_RETRIES} 次后)")
        return None

    data = response.json()
    message = data.get("message")
    if message is None:
        print("当前 Msg 为空")
        return None

    files = message.get("files")
    if files is None or not files:
        print("当前 Msg 无附件")
        return None

    # 存在附件，开始下载
    chat_id = message.get("meta", {}).get("chatId", "unknown")
    save_dir = Path("chatlet/files") / chat_id
    save_dir.mkdir(parents=True, exist_ok=True)

    # 收集下载任务
    file_tasks = []
    for file_info in files:
        meta = file_info.get("meta", {})
        blob = file_info.get("blob", {})

        fileid = file_info.get("id", "unknown")
        filename = meta.get("name", "unknown")
        sign_url = blob.get("signUrl", "")

        if not sign_url:
            print(f"  ️ 文件 {fileid} 无下载链接")
            continue
        
        file_tasks.append({
            "sign_url": sign_url,
            "fileid": fileid,
            "filename": filename,
            "save_dir": save_dir,
        })

    if not file_tasks:
        return

    asyncio.run(_download_all_async(file_tasks))
    return None

async def _download_all_async(file_tasks: list[dict]) -> None:
    """并发下载所有文件"""
    async with httpx.AsyncClient(trust_env=False, timeout=600) as client:
        coros = [_download_single_file(client, task) for task in file_tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)

    success = 0
    for task, result in zip(file_tasks, results):
        if isinstance(result, Exception):
            print(f"   {task['fileid']}: {result}")
        elif result:
            success += 1

    print(f" 共下载 {success}/{len(file_tasks)} 个文件")

async def _download_single_file(client: httpx.AsyncClient, task: dict) -> str | None:
    """单个文件异步下载"""
    fileid = task["fileid"]
    filename = task["filename"]
    sign_url = task["sign_url"]
    file_path = task["save_dir"] / filename

    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.get(sign_url, follow_redirects=True)
            resp.raise_for_status()

            with open(file_path, "wb") as f:
                f.write(resp.content)

            print(f"   已保存: {file_path}, fileId: {fileid}")
            return str(file_path)

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"   下载失败 (重试 {MAX_RETRIES} 次后): {fileid} - {e}")
                raise

def get_trace_data(segment_id: str) -> dict | None:
    """获取单个 segment 的 trace 数据"""
    # Step 1: 获取 traceSemanticUrl
    url = f"{BASE_URL}/api/v2/chats/-/messages/{segment_id}"
    response = get_with_retry(url)
    if not response:
        print(f"   获取 segment 信息失败 (重试 {MAX_RETRIES} 次后)")
        return None

    data = response.json()
    trace_url = data.get('traceSemanticUrl')
    if not trace_url:
        print("   traceSemanticUrl 不存在")
        return None

    # Step 2: 获取 trace 详情
    response = get_with_retry(BASE_URL + trace_url)
    if not response:
        print(f"   获取 trace 数据失败 (重试 {MAX_RETRIES} 次后)")
        return None

    trace_data = response.json()

    # Step 3: 解析 model requests
    model_requests = []
    for workflow in trace_data.get('workflows', []):
        workflow_name = workflow.get('meta', {}).get('name', '')
        if 'OSS' in workflow_name:
            continue

        for pipeline in workflow.get('pipelines', []):
            # 兼容两种结构: k2d5 用 steps, k2 用 modelRequests
            items = pipeline.get('steps') or pipeline.get('modelRequests') or []
            for item in items:
                if 'request' not in item:
                    continue

                request_data = item['request']
                model = request_data.get('model', '')
                if 'gpt-oss' in model:
                    continue

                model_requests.append({
                    "request": request_data,
                    "response": item.get('response', {})
                })

    return model_requests


def _content_to_str(content) -> str:
    """将 content 转为字符串（处理 list 类型的多模态内容）"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # OpenAI 多模态格式: [{"type": "text", "text": "..."}, ...]
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts)
    return str(content) if content else ""


# Memory 块识别前缀
MEMORY_PREFIXES = [
    "# memory_space",
    "# User Knowledge Memories",
    "# Recent Conversation Content",
]


def _is_memory_message(content: str) -> str | None:
    """检测是否为 Memory 消息，返回类型名或 None"""
    if not content:
        return None
    for prefix in MEMORY_PREFIXES:
        if content.strip().startswith(prefix):
            if "memory_space" in prefix:
                return "memory_space"
            elif "User Knowledge" in prefix:
                return "user_knowledge"
            elif "Recent Conversation" in prefix:
                return "recent_conversation"
    return None


def extract_memory_and_conversation(trace_result: dict) -> tuple[dict, list]:
    """
    从 trace 结果中分离 Memory 块和实际对话

    Returns:
        (memory_dict, conversations)
        - memory_dict: {"memory_space": "...", "user_knowledge": "...", "recent_conversation": "..."}
        - conversations: [{"role": "user", "content": "..."}, ...]
    """
    memory = {}
    conversations = []
    seen = set()

    for traj in trace_result.get('model_trajectories', []):
        model_requests = traj.get('model_requests', [])
        if not model_requests:
            continue

        # 从第一个 request 的 messages 中提取
        first_req = model_requests[0]
        messages = first_req.get('request', {}).get('messages', [])

        for msg in messages:
            role = msg.get('role', '')
            content = _content_to_str(msg.get('content', ''))

            if role == 'user' and content:
                # 检查是否为 Memory 消息
                mem_type = _is_memory_message(content)
                if mem_type:
                    if mem_type not in memory:
                        memory[mem_type] = content
                else:
                    # 实际对话
                    key = ('user', content[:100])
                    if key not in seen:
                        seen.add(key)
                        conversations.append({'role': 'user', 'content': content})

        # 从最后一个 response 提取 assistant 回复
        last_req = model_requests[-1]
        assistant_content = _content_to_str(last_req.get('response', {}).get('content', ''))
        if assistant_content:
            key = ('assistant', assistant_content[:100])
            if key not in seen:
                seen.add(key)
                conversations.append({'role': 'assistant', 'content': assistant_content})

    return memory, conversations


def extract_turns_with_steps(trace_result: dict) -> tuple[dict, list]:
    """
    提取 Turn-Step 嵌套结构

    Returns:
        (memory_dict, turns_list)
        - memory_dict: {"memory_space": "...", ...}
        - turns_list: [
            {
                "turn_index": 0,
                "user_input": "试试...",
                "steps": [
                    {
                        "step_index": 0,
                        "tool_calls": [{"name": "ipython", "arguments": "..."}],
                        "content": "试 rembg..."
                    },
                    ...
                ]
            },
            ...
        ]
    """
    memory = {}
    turns = []

    for traj in trace_result.get('model_trajectories', []):
        turn_index = traj.get('turn_index', 0)
        model_requests = traj.get('model_requests', [])
        if not model_requests:
            continue

        # 从第一个 request 的 messages 中提取 user 输入
        first_req = model_requests[0]
        messages = first_req.get('request', {}).get('messages', [])

        user_input = None
        # 正向遍历收集 memory，记录最后一个非 memory 的 user 消息
        for msg in messages:
            role = msg.get('role', '')
            content = _content_to_str(msg.get('content', ''))

            if role == 'user' and content:
                mem_type = _is_memory_message(content)
                if mem_type:
                    # Memory 消息
                    if mem_type not in memory:
                        memory[mem_type] = content
                else:
                    # 真正的 user 输入（后面的会覆盖前面的，保留最后一个）
                    user_input = content

        # 提取每个 step 的 response
        steps = []
        for step_idx, req in enumerate(model_requests):
            response = req.get('response', {})

            # 提取 tool_calls
            tool_calls = []
            for tc in response.get('tool_calls', []):
                func = tc.get('function', {})
                tool_calls.append({
                    'name': func.get('name', ''),
                    'arguments': func.get('arguments', '')
                })

            # 提取 content
            content = _content_to_str(response.get('content', ''))

            steps.append({
                'step_index': step_idx,
                'tool_calls': tool_calls,
                'content': content
            })

        turns.append({
            'turn_index': turn_index,
            'user_input': user_input,
            'steps': steps
        })

    # turn_index 越大越早，降序排列得到实际对话顺序
    turns.sort(key=lambda x: x.get('turn_index', 0), reverse=True)

    # 添加 display_num 用于显示（从 1 开始），保留原始 turn_index 用于 replay
    for i, turn in enumerate(turns):
        turn['display_num'] = i + 1

    return memory, turns


def extract_conversation(trace_result: dict) -> list:
    """从 trace 结果中提取 user/assistant 对话（按原始顺序）"""
    trajectories = trace_result.get('model_trajectories', [])
    if not trajectories:
        return []

    # 找最新的 turn（turn_index 最小的那个包含完整历史）
    latest_traj = min(trajectories, key=lambda t: t.get('turn_index', 0))
    model_requests = latest_traj.get('model_requests', [])
    if not model_requests:
        return []

    # 从 messages 按原始顺序提取 user/assistant
    messages = model_requests[0].get('request', {}).get('messages', [])
    conversations = []
    for msg in messages:
        role = msg.get('role', '')
        content = _content_to_str(msg.get('content', ''))
        if role in ('user', 'assistant') and content:
            # 跳过 memory 消息
            if not _is_memory_message(content):
                conversations.append({'role': role, 'content': content})

    # 补上最新 turn 的 response
    last_response = model_requests[-1].get('response', {})
    assistant_content = _content_to_str(last_response.get('content', ''))
    if assistant_content:
        conversations.append({'role': 'assistant', 'content': assistant_content})

    return conversations


def fetch_and_save_trace(chat_id: str, save_dir: str = "chatlet/trace") -> dict | None:
    """
    获取 trace 并保存到文件（按日期组织）

    Returns:
        trace_data dict (含 _saved_file 路径) or None
    """
    from datetime import datetime
    from pathlib import Path

    message_ids = get_message_ids(chat_id)
    if not message_ids:
        return None

    all_trajectories = []
    for msg in message_ids:
        model_requests = get_trace_data(msg['segment_id'])
        if model_requests:
            all_trajectories.append({
                'turn_index': msg['turn_index'],
                'segment_id': msg['segment_id'],
                'model_requests': model_requests
            })

    # 获取 user_id
    user_id = get_chat_user_id(chat_id)

    trace_data = {
        'chat_id': chat_id,
        'user_id': user_id,
        'message_ids': message_ids,
        'model_trajectories': all_trajectories
    }

    # 按日期创建文件夹: chatlet/trace/2025-01-21/
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H%M%S")
    save_path = Path(save_dir) / today
    save_path.mkdir(parents=True, exist_ok=True)

    filename = f"{timestamp}_{chat_id}.json"
    filepath = save_path / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2)

    trace_data['_saved_file'] = str(filepath)
    return trace_data


def print_trace_stats(result: dict):
    """打印 trace 统计信息"""
    trajectories = result.get('model_trajectories', [])

    total_turns = len(trajectories)
    total_steps = 0
    model = None
    tools_set = set()
    tool_calls_count = {}

    for traj in trajectories:
        requests = traj.get('model_requests', [])
        total_steps += len(requests)

        for req in requests:
            # 获取模型
            if not model:
                model = req.get('request', {}).get('model')

            # 获取工具集
            for tool in req.get('request', {}).get('tools', []):
                tools_set.add(tool.get('function', {}).get('name'))

            # 统计工具调用
            for tc in req.get('response', {}).get('tool_calls', []):
                name = tc.get('function', {}).get('name')
                tool_calls_count[name] = tool_calls_count.get(name, 0) + 1

    print("\n=== Trace Stats ===")
    print(f"Turns: {total_turns}")
    print(f"Steps: {total_steps}")
    print(f"Model: {model}")
    print(f"Tools: {sorted(tools_set)}")
    print(f"Calls: {tool_calls_count}")


def main():
    global BASE_URL

    parser = argparse.ArgumentParser(description='获取 chatlet 对话和 trace 数据')

    # 环境选择
    env_group = parser.add_mutually_exclusive_group()
    env_group.add_argument('--dev', action='store_true', default=True, help='测试环境 (默认)')
    env_group.add_argument('--prod', action='store_true', help='生产环境')

    # 输出模式
    parser.add_argument('--trace', action='store_true', help='保存到 chatlet/trace/')
    parser.add_argument('--conversation', action='store_true', help='保存到 chatlet/conversation/')
    parser.add_argument('--agent', action='store_true', help='额外保存 for_agent 版本（抹掉 SP 和 tool desc 以节省 context window）')
    parser.add_argument('-v', '--verbose', action='store_true', help='详细日志')
    parser.add_argument('chat_id', help='Chat ID, share_id, 或 share link (https://www.AI_Platform.com/share/...)')
    parser.add_argument('--download_file', action='store_true', help='选择是否要下载用户附件')

    args = parser.parse_args()

    # 设置 verbose
    global VERBOSE, FILE_DOWNLOAD
    VERBOSE = args.verbose
    FILE_DOWNLOAD = args.download_file

    # 设置环境
    if args.prod:
        BASE_URL = CHATLET_PROD_BASE_URL
        print(f" 生产环境: {BASE_URL}")
    else:
        BASE_URL = CHATLET_TEST_BASE_URL
        print(f" 测试环境: {BASE_URL}")
    # 解析输入（支持 share link / share_id / chat_id）
    chat_id = resolve_chat_id(args.chat_id)

    # 获取 message ids
    message_ids = get_message_ids(chat_id)
    if not message_ids:
        print(f" 未找到 chat_id {chat_id} 的消息")
        return

    print(f" 找到 {len(message_ids)} 条 assistant 消息")

    # 获取每个 segment 的 trace
    all_trajectories = []
    for msg in message_ids:
        segment_id = msg['segment_id']
        turn_index = msg['turn_index']
        print(f"  Turn {turn_index}: {segment_id}")

        model_requests = get_trace_data(segment_id)
        if model_requests:
            all_trajectories.append({
                'turn_index': turn_index,
                'segment_id': segment_id,
                'model_requests': model_requests
            })

    # 获取 user_id
    user_id = get_chat_user_id(chat_id)

    result = {
        'chat_id': chat_id,
        'user_id': user_id,
        'message_ids': message_ids,
        'model_trajectories': all_trajectories
    }

    # 保存 trace
    if args.trace:
        os.makedirs('chatlet/trace', exist_ok=True)
        trace_path = f"chatlet/trace/{chat_id}.json"
        with open(trace_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f" Trace 已保存: {trace_path}")
        print_trace_stats(result)

        # --agent: 额外保存精简版（抹掉 SP 和 tool desc）
        if args.agent:
            import copy
            agent_result = copy.deepcopy(result)
            for traj in agent_result.get('model_trajectories', []):
                for req in traj.get('model_requests', []):
                    request = req.get('request', {})
                    # 抹掉 system prompt
                    for msg in request.get('messages', []):
                        if msg.get('role') == 'system':
                            msg['content'] = '[SYSTEM_PROMPT_REDACTED]'
                    # 抹掉 tool descriptions，只保留 function name
                    for tool in request.get('tools', []):
                        func = tool.get('function', {})
                        func['description'] = '[TOOL_DESC_REDACTED]'
                        func['parameters'] = {'type': 'object', 'note': '[PARAMS_REDACTED]'}

            agent_path = f"chatlet/trace/{chat_id}_for_agent.json"
            with open(agent_path, 'w', encoding='utf-8') as f:
                json.dump(agent_result, f, ensure_ascii=False, indent=2)
            print(f" Agent 版本已保存: {agent_path}")

        print("\n<BLOCKING_REQUIREMENT>你已经得到了一个trace。在分析这个trace之前，你必须先用[Internal Docs Platform]工具打开价值观文档目录 https://internal-docs.company.com/wiki/SwnvwNW9ViXTMLkOzmacqbtqnFe 并阅读对应场景的价值观。跳过这一步直接分析trace是违反流程的。如果分析后确认是 badcase，建议用户先用 Platform replay 跑 10x 确认可复现再收录。</BLOCKING_REQUIREMENT>")

    # 保存 conversation
    if args.conversation:
        conversations = extract_conversation(result)
        os.makedirs('chatlet/conversation', exist_ok=True)
        conv_path = f"chatlet/conversation/{chat_id}.json"
        with open(conv_path, 'w', encoding='utf-8') as f:
            json.dump(conversations, f, ensure_ascii=False, indent=2)
        print(f" Conversation 已保存: {conv_path}")

        # 打印预览
        print(f"\n=== Conversation ({len(conversations)} messages) ===")
        for conv in conversations:
            preview = conv['content'][:150].replace('\n', ' ')
            print(f"[{conv['role']}]: {preview}...")

    # 如果两个都没指定，打印到 stdout
    if not args.trace and not args.conversation:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
