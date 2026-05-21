import httpx
import os
import json
import sys
import time
import datetime
import logging
import requests
import pandas as pd
from pathlib import Path

from typing import List

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_CONFIG_DIR = REPO_ROOT / "scripts"
if str(RUNTIME_CONFIG_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_CONFIG_DIR))

from runtime_config import get_AuthGateway_service_config

# 延迟导入 openai（只在需要模型调用时才导入）
_openai_imported = False
OpenAI = None

def _ensure_openai():
    global _openai_imported, OpenAI
    if not _openai_imported:
        from openai import OpenAI as _OpenAI
        OpenAI = _OpenAI
        _openai_imported = True

# 配置日志
logger = logging.getLogger(__name__)

CHATLET_CONFIG = get_AuthGateway_service_config(__file__, "chatlet")


class KimiInternalTools:
    """Internal_Tool 内部工具类，提供获取对话轨迹和文件的能力"""
    
    # API 配置
    CHATLET_BASE_URL = CHATLET_CONFIG["base_url"]
    CHATLET_HEADERS = {
        "accept": "application/json",
        "X-AuthGateway-Access-Token": CHATLET_CONFIG["access_token"]
    }
    Internal_Tool_FILES_API_URL = "http://172.24.128.60:8180/download_Internal_Tool_folder"
    # NAS 挂载路径
    Internal_Tool_FILES_ROOT_PATH = os.environ.get('Internal_Tool_FILES_ROOT_PATH', '/qa/qa/Internal_Tool_files')
    
    # 需要截断的工具参数映射
    SHORTEN_ARGS_MAPPING = {
        "mshtools-write_file": ['content'],
        "mshtools-read_file": ['content'],
        "mshtools-slides_generator": ['content'],
        "mshtools-todo_write": ['todos'],
        "mshtools-todo_read": ['todos'],
        "mshtools-generate_image": ['description'],
        "mshtools-ipython": ['code'],
        "mshtools-shell": ['command'],
        
    }
    
    # 工具定义 (OpenAI function calling 格式)
    TOOL_DEFINITIONS = [
        {
            "type": "function",
            "function": {
                "name": "get_compact_trajectory",
                "description": "获取 Internal_Tool (OK Computer) 聊天的完整对话轨迹。返回用户查询和模型响应的紧凑格式，包括工具调用信息。用于分析和调试 Agent 行为。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {
                            "type": "string",
                            "description": "Internal_Tool 聊天 ID，格式如: 19afbc49-6df2-8e5b-8000-092d2b6a481a"
                        }
                    },
                    "required": ["chat_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_Internal_Tool_files",
                "description": "获取 Internal_Tool (OK Computer) 聊天产出的文件列表。返回用户在 /mnt/Internal_Toolomputer/output/ 目录下能看到的所有文件信息，包括文件名、路径、大小和扩展名。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {
                            "type": "string",
                            "description": "Internal_Tool 聊天 ID，格式如: 19afbc49-6df2-8e5b-8000-092d2b6a481a"
                        }
                    },
                    "required": ["chat_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_analysis_file",
                "description": "将分析结果写入文件。会在 sessions/{chat_id}/ 目录下创建指定文件名的文件，用于保存结构化的分析结果、评估报告等。支持 JSON、YAML、Markdown 等格式。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {
                            "type": "string",
                            "description": "Internal_Tool 聊天 ID，用于创建对应的目录"
                        },
                        "filename": {
                            "type": "string",
                            "description": "文件名，如: analysis.json, report.md, evaluation.yaml"
                        },
                        "content": {
                            "type": "string",
                            "description": "要写入的文件内容"
                        }
                    },
                    "required": ["chat_id", "filename", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_analysis_file",
                "description": "读取之前保存的分析文件。从 sessions/{chat_id}/ 目录下读取指定文件的内容。可用于读取历史分析结果进行对比或继续分析。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {
                            "type": "string",
                            "description": "Internal_Tool 聊天 ID"
                        },
                        "filename": {
                            "type": "string",
                            "description": "要读取的文件名。如果不指定，返回该 chat_id 目录下的文件列表"
                        }
                    },
                    "required": ["chat_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_output_file",
                "description": "检查 Internal_Tool 产出文件的内容。可以读取完整文件内容，或在文件中搜索关键词。文件路径会自动从 /mnt/Internal_Toolomputer/ 转换为本地路径。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {
                            "type": "string",
                            "description": "Internal_Tool 聊天 ID，格式如: 19afbc49-6df2-8e5b-8000-092d2b6a481a"
                        },
                        "full_path": {
                            "type": "string",
                            "description": "文件的完整路径，如: /mnt/Internal_Toolomputer/output/result.txt。路径会自动转换为本地路径。"
                        },
                        "keyword": {
                            "type": "string",
                            "description": "要在文件中搜索的关键词（可选）。如果指定，将返回包含该关键词的行及其上下文。"
                        },
                        "context_lines": {
                            "type": "integer",
                            "description": "搜索关键词时，返回匹配行前后的上下文行数（默认为3）"
                        }
                    },
                    "required": ["chat_id", "full_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "debug_link",
                "description": "调试 OK Computer 产出给用户的链接。检查链接是否可以正常访问，返回 HTTP 状态码、响应内容、错误信息等。支持检测重定向、SSL 证书问题、超时等常见问题。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "要调试的 URL 链接"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "请求超时时间（秒），默认为 10"
                        },
                        "follow_redirects": {
                            "type": "boolean",
                            "description": "是否跟随重定向，默认为 True"
                        },
                        "show_content": {
                            "type": "boolean",
                            "description": "是否返回响应内容（可能很长），默认为 True"
                        },
                        "max_content_length": {
                            "type": "integer",
                            "description": "返回内容的最大长度（字符），默认为 5000"
                        }
                    },
                    "required": ["url"]
                }
            }
        }
    ]
    
    # Session 文件存储根目录
    SESSIONS_ROOT_PATH = "/qa/qa/agent_debugger/sessions"
    
    @classmethod
    def get_tool_definitions(cls) -> List[dict]:
        """获取所有工具定义
        
        Returns:
            工具定义列表，可直接用于 OpenAI API 的 tools 参数
        """
        return cls.TOOL_DEFINITIONS
    
    @classmethod
    def get_chat_content(cls, chat_id: str, env: str = 'PROD') -> pd.DataFrame:
        """获取聊天内容
        
        Args:
            chat_id: 聊天 ID
            env: 环境 (默认 PROD)
            
        Returns:
            包含聊天消息的 DataFrame，失败返回 None
        """
        if not chat_id:
            return None
        
        try:
            fetch_chat_messages_url = f"{cls.CHATLET_BASE_URL}/api/v2/chats/{chat_id}/messages"
            chat_messages_response = requests.get(
                fetch_chat_messages_url, 
                headers=cls.CHATLET_HEADERS, 
                timeout=120
            )
            if chat_messages_response.status_code != 200:
                logger.error(f"获取聊天内容失败，状态码: {chat_messages_response.status_code}")
                return None
            
            chat_messages = chat_messages_response.json()
            if not chat_messages.get('messageEntries', []):
                logger.warning(f"聊天记录为空: {chat_id}")
                return None
            
            chat_response_df = pd.DataFrame(chat_messages['messageEntries'])
            chat_response_df['id'] = chat_response_df['message'].apply(lambda x: x['meta'].get('id', ''))
            chat_response_df['role'] = chat_response_df['message'].apply(lambda x: x['meta'].get('role', ''))
            chat_response_df['platform'] = chat_response_df['message'].apply(lambda x: x['meta'].get('platform', ''))
            chat_response_df['chatId'] = chat_response_df['message'].apply(lambda x: x['meta'].get('chatId', ''))
            chat_response_df['parentId'] = chat_response_df['message'].apply(lambda x: x['meta'].get('parentId', ''))
            chat_response_df['depth'] = chat_response_df['message'].apply(lambda x: x['meta'].get('depth', ''))
            return chat_response_df
            
        except requests.exceptions.RequestException as e:
            logger.error(f"请求异常: {e}")
            return None
    
    @classmethod
    def get_segment_content(cls, segment_id: str, env: str = 'PROD') -> dict:
        """获取单个消息段落的内容
        
        Args:
            segment_id: 消息段落 ID
            env: 环境 (默认 PROD)
            
        Returns:
            消息段落的 JSON 数据，失败返回 None
        """
        if not segment_id:
            return None
        
        try:
            fetch_trace_url = f"{cls.CHATLET_BASE_URL}/api/v2/chats/-/messages/{segment_id}"
            trace_response = requests.get(
                fetch_trace_url, 
                headers=cls.CHATLET_HEADERS, 
                timeout=30
            )
            if trace_response.status_code != 200:
                logger.error(f"获取消息段落失败，状态码: {trace_response.status_code}")
                return None
            
            return trace_response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"请求异常: {e}")
            return None
    
    @classmethod
    def get_user_turn_trajectory(cls, segment_id: str, env: str = "PROD", turn_id: int = 0, shorten_length: int = 30) -> List[str]:
        """获取用户单轮对话的紧凑轨迹
        
        Args:
            segment_id: 消息段落 ID
            env: 环境 (默认 PROD)
            turn_id: 轮次 ID
            shorten_length: 截断长度 (默认 30)
            
        Returns:
            紧凑轨迹列表
        """
        compact_traj = []
        step_idx = 0

        data_request = cls.get_segment_content(segment_id=segment_id, env=env)
        if not data_request:
            return compact_traj

        # 获取用户消息
        try:
            user_message = data_request.get('message', {}).get('message', {}).get('blocks', [])[0].get('text', {}).get('content', '')
        except (IndexError, KeyError):
            user_message = ''
        
        user_line = f"[user_query][turn_{turn_id}] {user_message}\n"
        compact_traj.append(user_line)
        
        # 获取 blocks 中的 multiStage/stage/exception 信息
        try:
            blocks = data_request.get('message', {}).get('message', {}).get('blocks', [])
            for block in blocks:
                # block 结构是 {"id": "...", "multiStage": {...}} 或 {"id": "...", "stage": {...}}
                if 'multiStage' in block:
                    multi_stage = block.get('multiStage', {})
                    stages = multi_stage.get('stages', [])
                    if stages:
                        stage_names = [s.get('name', 'unknown') for s in stages]
                        compact_traj.append(f"[multiStage] Stages: {stage_names}\n")
                elif 'stage' in block:
                    stage = block.get('stage', {})
                    stage_name = stage.get('name', 'unknown')
                    stage_status = stage.get('status', 'unknown')
                    compact_traj.append(f"[stage] Name: {stage_name}, Status: {stage_status}\n")
                elif 'exception' in block:
                    exc = block.get('exception', {})
                    error = exc.get('error', {})
                    reason = error.get('reason', 'unknown')
                    compact_traj.append(f"[Exception] {reason}\n")
        except (IndexError, KeyError):
            pass

        # 获取模型请求轨迹
        traceSemanticUrl = data_request.get('traceSemanticUrl', '')
        if not traceSemanticUrl:
            return compact_traj
            
        full_url = cls.CHATLET_BASE_URL + traceSemanticUrl
        
        try:
            response = requests.get(full_url, headers=cls.CHATLET_HEADERS, timeout=30)
            if response.status_code != 200:
                logger.error(f"获取轨迹失败，状态码: {response.status_code}")
                return compact_traj
            
            model_requests_response = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"请求轨迹异常: {e}")
            return compact_traj

        # 解析工作流
        for workflow in model_requests_response.get('workflows', []):
            pipelines = workflow.get('pipelines', [])
            for pipeline in pipelines:
                model_requests = pipeline.get('steps', [])
                for model_request in model_requests:
                    
                    # 处理错误
                    if 'error' in model_request.get('meta', {}):
                        error_msg = model_request['meta']['error']
                        if 'context canceled' in error_msg:
                            action_line = "[Exception] 用户停止回复了\n"
                        elif 'exceed tool call max rounds' in error_msg.lower():
                            action_line = f"[Exception] 工具调用次数超限: {error_msg}\n"
                        elif 'timeout' in error_msg.lower():
                            action_line = f"[Exception] 请求超时: {error_msg}\n"
                        elif 'rate limit' in error_msg.lower():
                            action_line = f"[Exception] 速率限制: {error_msg}\n"
                        else:
                            action_line = f"[Exception] {error_msg}\n"
                        compact_traj.append(action_line)
                        continue

                    request = model_request.get('request', {})
                    model = request.get('model', {})
                    if model == 'opensource-gpt-oss-20b-chat':
                        continue
                    
                    action_line = ''

                    response_data = model_request.get('response', {})
                    response_content = response_data.get('content', '')
                    reasoning_content = response_data.get('reasoning_content', '')  # 提取推理内容
                    usage = response_data.get('usage', {})  # 修复拼写错误: u·sage -> usage

                    step_idx += 1
                    
                    # 如果有 reasoning_content，先输出
                    if reasoning_content:
                        action_line += f"[model_reasoning][turn_{turn_id}][step_{step_idx}] {reasoning_content}\n\n"
                    
                    action_line += f"[model_resp][turn_{turn_id}][step_{step_idx}] {response_content}\n\n"
                    response_tools = response_data.get('tool_calls', [])
                    
                    for response_tool in response_tools:
                        tool_call_id = response_tool.get('id', '')
                        tool_call_function = response_tool.get('function', {})
                        tool_call_function_name = tool_call_function.get('name', '')
                        action_line += f"[tool_call] Tool Name: {tool_call_function_name} , Tool Call ID: {tool_call_id} ,"

                        tool_call_function_args = tool_call_function.get('arguments', {})
                        try:
                            tool_call_function_args = json.loads(tool_call_function_args)
                        except Exception as e:
                            tool_call_function_args = {"raw_arguments": tool_call_function_args, "note": f"Failed to parse arguments as JSON: {e}"}

                        # 截断过长的参数
                        shorten_arg_keys = cls.SHORTEN_ARGS_MAPPING.get(tool_call_function_name, [])
                        for key in shorten_arg_keys:
                            if key in tool_call_function_args:
                                full_content = tool_call_function_args[key]
                                if len(str(full_content)) > shorten_length:
                                    tool_call_function_args[key] = f'{str(full_content)[0:shorten_length]}...[truncated]'
                                else:
                                    tool_call_function_args[key] = full_content

                        action_line += f"Tool Args: {tool_call_function_args}\n\n"
                    
                    # 处理工具返回结果
                    tool_results = response_data.get('tool_results', [])
                    for tool_result in tool_results:
                        tool_call_id = tool_result.get('tool_call_id', '')
                        tool_result_content = tool_result.get('content', '')
                        tool_result_status = tool_result.get('status', 'unknown')
                        
                        # 截断过长的结果
                        if isinstance(tool_result_content, str) and len(tool_result_content) > shorten_length * 2:
                            tool_result_content = f'{tool_result_content[0:shorten_length*2]}...[truncated]'
                        
                        action_line += f"[tool_result] Tool Call ID: {tool_call_id}, Status: {tool_result_status}, Content: {tool_result_content}\n\n"
                    
                    action_line += f"[model_usage] {usage}\n"
                    compact_traj.append(action_line)

        return compact_traj
    
    @classmethod
    def get_compact_trajectory(cls, chat_id: str, env: str = 'PROD') -> List[str]:
        """获取完整对话的紧凑轨迹
        
        Args:
            chat_id: 聊天 ID
            env: 环境 (默认 PROD)
            
        Returns:
            完整对话的紧凑轨迹列表
        """
        chat_response = cls.get_chat_content(chat_id=chat_id, env=env)
        if chat_response is None:
            return []
        
        whole_traj = []
        
        # 处理 user 消息（用户输入和模型响应）
        chat_user_messages = chat_response[chat_response['role'] == 'user'].sort_values(by='depth', ascending=True)
        turn_id = 0
        for index, row in chat_user_messages.iterrows():
            segment_id = row['id']
            logger.info(f"Processing segment_id: {segment_id}")
            turn_id += 1
            model_requests_traj = cls.get_user_turn_trajectory(segment_id=segment_id, env=env, turn_id=turn_id)
            whole_traj.extend(model_requests_traj)
        
        # 处理 assistant 消息（获取 multiStage/stage/exception/tool 信息）
        chat_assistant_messages = chat_response[chat_response['role'] == 'assistant']
        for index, row in chat_assistant_messages.iterrows():
            segment_id = row['id']
            data_request = cls.get_segment_content(segment_id=segment_id, env=env)
            if data_request:
                # 提取 multiStage/stage/exception/tool 信息
                blocks = data_request.get('message', {}).get('message', {}).get('blocks', [])
                for block in blocks:
                    if 'multiStage' in block:
                        multi_stage = block.get('multiStage', {})
                        stages = multi_stage.get('stages', [])
                        if stages:
                            stage_names = [s.get('name', 'unknown') for s in stages]
                            whole_traj.append(f"[multiStage] Stages: {stage_names}\n")
                    elif 'stage' in block:
                        stage = block.get('stage', {})
                        stage_name = stage.get('name', 'unknown')
                        stage_status = stage.get('status', 'unknown')
                        whole_traj.append(f"[stage] Name: {stage_name}, Status: {stage_status}\n")
                    elif 'exception' in block:
                        exc = block.get('exception', {})
                        error = exc.get('error', {})
                        reason = error.get('reason', 'unknown')
                        whole_traj.append(f"[Exception] {reason}\n")
                    elif 'tool' in block:
                        # 提取 tool result
                        tool = block.get('tool', {})
                        tool_name = tool.get('name', 'unknown')
                        tool_call_id = tool.get('toolCallId', 'unknown')
                        contents = tool.get('contents', [])
                        is_error = tool.get('isError', False)
                        status = tool.get('status', 'unknown')
                        
                        # 构建 content 摘要
                        content_text = ''
                        if contents:
                            for c in contents:
                                if 'text' in c:
                                    content_text += c['text'][:100]  # 只取前100字符
                        
                        error_mark = " " if is_error else ""
                        whole_traj.append(f"[{error_mark}tool_result] {tool_name} (ID: {tool_call_id}), Status: {status}, Content: {content_text[:80]}...\n")
        
        return whole_traj
    
    @classmethod
    def check_fetched_files(cls, chat_id: str) -> dict:
        """检查本地是否已存在 Internal_Tool 文件
        
        Args:
            chat_id: 聊天 ID
            
        Returns:
            如果存在返回 {"local_path": ...}，否则返回 None
        """
        # FIX: 确保本地缓存目录存在
        try:
            Path(cls.Internal_Tool_FILES_ROOT_PATH).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"无法创建缓存目录: {e}")
            return None
            
        fetched_chat_ids = [
            name for name in os.listdir(cls.Internal_Tool_FILES_ROOT_PATH) 
            if os.path.isdir(os.path.join(cls.Internal_Tool_FILES_ROOT_PATH, name))
        ]
        if chat_id in fetched_chat_ids:
            return {"local_path": os.path.join(cls.Internal_Tool_FILES_ROOT_PATH, chat_id)}
        return None
    
    @classmethod
    def query_Internal_Tool_files(cls, chat_id: str, max_retries: int = 3) -> dict:
        """查询 Internal_Tool 文件（如果本地不存在则从远程下载）
        
        Args:
            chat_id: 聊天 ID
            max_retries: 最大重试次数（默认3次）
            
        Returns:
            包含 local_path 的字典，失败返回 None
        """
        # 先检查本地
        file_path = cls.check_fetched_files(chat_id)
        if file_path:
            logger.info(f"文件已存在于本地: {file_path['local_path']}")
            return file_path
        
        # 从远程下载（带重试）
        headers = {
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }
        
        payload = {"chat_id": chat_id}
        
        # FIX: 增加超时到 600 秒，并添加重试机制
        timeout = 600
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"尝试 {attempt}/{max_retries}: 从远程下载 Internal_Tool 文件: {chat_id}")
                response = requests.post(
                    cls.Internal_Tool_FILES_API_URL,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=timeout
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"下载成功: {result}")
                return result
                
            except requests.exceptions.Timeout:
                logger.warning(f"尝试 {attempt} 超时 ({timeout}秒)")
                if attempt == max_retries:
                    logger.error(f"所有 {max_retries} 次重试都超时")
                    return None
                # 指数退避等待
                wait_time = min(2 ** attempt, 30)  # 最大等待30秒
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"请求失败: {e}")
                return None
            except Exception as e:
                logger.error(f"发生错误: {e}")
                return None
        
        return None
    
    @classmethod
    def read_directory_files(cls, local_path: str, chat_id: str = '') -> List[dict]:
        """读取本地目录中的文件列表
        
        Args:
            local_path: 本地路径
            chat_id: 聊天 ID (用于路径替换)
            
        Returns:
            文件信息列表
        """
        if not os.path.exists(local_path):
            logger.error(f"路径不存在: {local_path}")
            return []
        
        if not os.path.isdir(local_path):
            logger.error(f"路径不是目录: {local_path}")
            return []
        
        try:
            files_info = []
            for root, dirs, files in os.walk(local_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_stat = os.stat(file_path)
                    relative_path = os.path.relpath(file_path, local_path)
                    
                    # 替换路径前缀为 /mnt/Internal_Toolomputer/
                    if chat_id:
                        full_path = file_path.replace(f'/qa/qa/Internal_Tool_files/{chat_id}/', '/mnt/Internal_Toolomputer/')
                    else:
                        full_path = file_path
                    
                    files_info.append({
                        'name': file,
                        'relative_path': relative_path,
                        'full_path': full_path,
                        'size': file_stat.st_size,
                        'extension': Path(file).suffix
                    })
            
            return sorted(files_info, key=lambda x: x['relative_path'])
            
        except Exception as e:
            logger.error(f"读取目录失败: {e}")
            return []
    
    @classmethod
    def get_Internal_Tool_files(cls, chat_id: str) -> List[dict]:
        """获取 Internal_Tool 文件列表
        
        Args:
            chat_id: 聊天 ID
            
        Returns:
            文件信息列表
        """
        # 首先检查本地缓存（优先使用本地缓存）
        local_cache_path = os.path.join(cls.Internal_Tool_FILES_ROOT_PATH, chat_id)
        if os.path.exists(local_cache_path):
            logger.info(f"使用本地缓存: {local_cache_path}")
            return cls.read_directory_files(local_cache_path, chat_id=chat_id)
        
        # 本地不存在，尝试从远程下载
        Internal_Tool_files_path = cls.query_Internal_Tool_files(chat_id=chat_id)
        if not Internal_Tool_files_path:
            return []
        
        api_path = Internal_Tool_files_path.get('local_path', '')
        if not api_path:
            return []
        
        # 如果 API 返回的路径存在（在同一台机器上），直接使用
        if os.path.exists(api_path):
            return cls.read_directory_files(api_path, chat_id=chat_id)
        
        # API 返回的路径是服务器端路径，本地无法直接访问
        # 检查是否已同步到本地缓存路径
        if os.path.exists(local_cache_path):
            return cls.read_directory_files(local_cache_path, chat_id=chat_id)
        
        logger.warning(f"文件尚未同步到本地: {chat_id}")
        logger.info("请使用 sync_nas_files.py 手动同步文件")
        return []
    
    @classmethod
    def write_analysis_file(cls, chat_id: str, filename: str, content: str) -> dict:
        """将分析结果写入文件
        
        Args:
            chat_id: 聊天 ID，用于创建对应目录
            filename: 文件名
            content: 文件内容
            
        Returns:
            {"success": bool, "path": str, "message": str}
        """
        if not chat_id:
            return {"success": False, "path": "", "message": "缺少 chat_id 参数"}
        
        if not filename:
            return {"success": False, "path": "", "message": "缺少 filename 参数"}
        
        try:
            # 创建 chat_id 目录
            session_dir = Path(cls.SESSIONS_ROOT_PATH) / chat_id
            session_dir.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            file_path = session_dir / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 写入元数据
            meta_file = session_dir / "_meta.json"
            meta = {}
            if meta_file.exists():
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                except Exception:
                    pass
            
            meta["chat_id"] = chat_id
            meta["last_updated"] = datetime.datetime.now().isoformat()
            if "files" not in meta:
                meta["files"] = []
            if filename not in meta["files"]:
                meta["files"].append(filename)
            
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            
            logger.info(f"写入分析文件成功: {file_path}")
            return {
                "success": True, 
                "path": str(file_path), 
                "message": f"文件已保存到 {file_path}"
            }
            
        except Exception as e:
            logger.error(f"写入分析文件失败: {e}", exc_info=True)
            return {"success": False, "path": "", "message": str(e)}
    
    @classmethod
    def read_analysis_file(cls, chat_id: str, filename: str = None) -> dict:
        """读取分析文件
        
        Args:
            chat_id: 聊天 ID
            filename: 文件名，如果不指定则返回目录下的文件列表
            
        Returns:
            {"success": bool, "content": str, "files": list, "message": str}
        """
        if not chat_id:
            return {"success": False, "content": "", "files": [], "message": "缺少 chat_id 参数"}
        
        try:
            session_dir = Path(cls.SESSIONS_ROOT_PATH) / chat_id
            
            if not session_dir.exists():
                return {
                    "success": False, 
                    "content": "", 
                    "files": [], 
                    "message": f"目录不存在: {session_dir}"
                }
            
            # 如果没有指定文件名，返回文件列表
            if not filename:
                files = []
                for f in session_dir.iterdir():
                    if f.is_file() and not f.name.startswith('_'):
                        files.append({
                            "name": f.name,
                            "size": f.stat().st_size,
                            "modified": datetime.datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                        })
                
                return {
                    "success": True,
                    "content": "",
                    "files": files,
                    "message": f"目录 {chat_id} 下共有 {len(files)} 个文件"
                }
            
            # 读取指定文件
            file_path = session_dir / filename
            if not file_path.exists():
                return {
                    "success": False,
                    "content": "",
                    "files": [],
                    "message": f"文件不存在: {file_path}"
                }
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            logger.info(f"读取分析文件成功: {file_path}")
            return {
                "success": True,
                "content": content,
                "files": [],
                "message": f"成功读取文件 {filename}"
            }
            
        except Exception as e:
            logger.error(f"读取分析文件失败: {e}", exc_info=True)
            return {"success": False, "content": "", "files": [], "message": str(e)}
    
    @classmethod
    def check_output_file(cls, chat_id: str, full_path: str, keyword: str = None, context_lines: int = 3) -> dict:
        """检查 Internal_Tool 产出文件的内容
        
        Args:
            chat_id: 聊天 ID
            full_path: 文件的完整路径（/mnt/Internal_Toolomputer/... 格式）
            keyword: 要搜索的关键词（可选）
            context_lines: 搜索时返回的上下文行数（默认为3）
            
        Returns:
            {"success": bool, "content": str, "matches": list, "message": str}
        """
        if not chat_id:
            return {"success": False, "content": "", "matches": [], "message": "缺少 chat_id 参数"}
        
        if not full_path:
            return {"success": False, "content": "", "matches": [], "message": "缺少 full_path 参数"}
        
        try:
            # 路径转换: /mnt/Internal_Toolomputer/ -> /qa/qa/Internal_Tool_files/{chat_id}/
            local_path = full_path.replace('/mnt/Internal_Toolomputer/', f'{cls.Internal_Tool_FILES_ROOT_PATH}/{chat_id}/')
            
            logger.info(f"路径转换: {full_path} -> {local_path}")
            
            # 检查文件是否存在
            if not os.path.exists(local_path):
                # 尝试先下载文件
                Internal_Tool_files_result = cls.query_Internal_Tool_files(chat_id=chat_id)
                if not Internal_Tool_files_result:
                    return {
                        "success": False,
                        "content": "",
                        "matches": [],
                        "message": f"无法获取 Internal_Tool 文件，chat_id: {chat_id}"
                    }
                
                # 再次检查文件
                if not os.path.exists(local_path):
                    return {
                        "success": False,
                        "content": "",
                        "matches": [],
                        "message": f"文件不存在: {local_path}"
                    }
            
            # 检查是否是目录
            if os.path.isdir(local_path):
                return {
                    "success": False,
                    "content": "",
                    "matches": [],
                    "message": f"路径是一个目录，不是文件: {local_path}"
                }
            
            # 获取文件大小
            file_size = os.path.getsize(local_path)
            file_ext = Path(local_path).suffix.lower()
            
            # 检查文件类型（二进制文件不读取内容）
            binary_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.pdf', 
                               '.zip', '.tar', '.gz', '.rar', '.7z', '.exe', '.dll',
                               '.so', '.dylib', '.bin', '.dat', '.mp3', '.mp4', '.avi',
                               '.mov', '.wav', '.flac', '.ppt', '.pptx', '.doc', '.docx',
                               '.xls', '.xlsx', '.pyc', '.class', '.o', '.obj'}
            
            if file_ext in binary_extensions:
                return {
                    "success": True,
                    "content": f"[二进制文件，大小: {file_size} bytes，类型: {file_ext}]",
                    "matches": [],
                    "message": f"这是一个二进制文件 ({file_ext})，无法显示文本内容",
                    "file_info": {
                        "path": local_path,
                        "size": file_size,
                        "extension": file_ext,
                        "is_binary": True
                    }
                }
            
            # 读取文件内容
            try:
                with open(local_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # 尝试其他编码
                try:
                    with open(local_path, 'r', encoding='gbk') as f:
                        content = f.read()
                except Exception:
                    return {
                        "success": True,
                        "content": f"[无法解码的文件，大小: {file_size} bytes]",
                        "matches": [],
                        "message": "文件编码无法识别，可能是二进制文件",
                        "file_info": {
                            "path": local_path,
                            "size": file_size,
                            "extension": file_ext,
                            "is_binary": True
                        }
                    }
            
            # 如果没有关键词，返回完整内容
            if not keyword:
                return {
                    "success": True,
                    "content": content,
                    "matches": [],
                    "message": f"成功读取文件，共 {len(content)} 字符，{len(content.splitlines())} 行",
                    "file_info": {
                        "path": local_path,
                        "size": file_size,
                        "extension": file_ext,
                        "is_binary": False,
                        "line_count": len(content.splitlines())
                    }
                }
            
            # 搜索关键词
            lines = content.splitlines()
            matches = []
            
            for i, line in enumerate(lines):
                if keyword.lower() in line.lower():
                    # 获取上下文
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    
                    context = []
                    for j in range(start, end):
                        prefix = ">>> " if j == i else "    "
                        context.append(f"{prefix}[{j+1}] {lines[j]}")
                    
                    matches.append({
                        "line_number": i + 1,
                        "line_content": line,
                        "context": "\n".join(context)
                    })
            
            if matches:
                # 构建匹配结果摘要
                match_summary = f"找到 {len(matches)} 处匹配:\n\n"
                for idx, match in enumerate(matches, 1):
                    match_summary += f"--- 匹配 {idx} (第 {match['line_number']} 行) ---\n"
                    match_summary += match["context"] + "\n\n"
                
                return {
                    "success": True,
                    "content": match_summary,
                    "matches": matches,
                    "message": f"在文件中找到 {len(matches)} 处包含关键词 '{keyword}' 的匹配",
                    "file_info": {
                        "path": local_path,
                        "size": file_size,
                        "extension": file_ext,
                        "is_binary": False,
                        "line_count": len(lines)
                    }
                }
            else:
                return {
                    "success": True,
                    "content": f"未找到关键词 '{keyword}'",
                    "matches": [],
                    "message": f"在文件中未找到关键词 '{keyword}'",
                    "file_info": {
                        "path": local_path,
                        "size": file_size,
                        "extension": file_ext,
                        "is_binary": False,
                        "line_count": len(lines)
                    }
                }
            
        except Exception as e:
            logger.error(f"检查产出文件失败: {e}", exc_info=True)
            return {"success": False, "content": "", "matches": [], "message": str(e)}
    
    @classmethod
    def debug_link(cls, url: str, timeout: int = 10, follow_redirects: bool = True, 
                   show_content: bool = True, max_content_length: int = 5000) -> dict:
        """调试链接，检查是否可以正常访问
        
        Args:
            url: 要调试的 URL
            timeout: 请求超时时间（秒）
            follow_redirects: 是否跟随重定向
            show_content: 是否返回响应内容
            max_content_length: 返回内容的最大长度
            
        Returns:
            {"success": bool, "status_code": int, "content": str, "error": str, "debug_info": dict}
        """
        if not url:
            return {
                "success": False,
                "status_code": None,
                "content": "",
                "error": "缺少 url 参数",
                "debug_info": {}
            }
        
        # 确保 URL 有协议前缀
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        debug_info = {
            "url": url,
            "timeout": timeout,
            "follow_redirects": follow_redirects,
            "request_time": datetime.datetime.now().isoformat(),
            "redirects": [],
            "headers": {},
            "ssl_info": None,
            "response_time_ms": None
        }
        
        try:
            from urllib.parse import urlparse
            
            # 验证 URL 格式
            parsed = urlparse(url)
            if not parsed.netloc:
                return {
                    "success": False,
                    "status_code": None,
                    "content": "",
                    "error": f"无效的 URL 格式: {url}",
                    "debug_info": debug_info
                }
            
            debug_info["parsed_url"] = {
                "scheme": parsed.scheme,
                "netloc": parsed.netloc,
                "path": parsed.path,
                "query": parsed.query
            }
            
            # 发起请求
            start_time = time.time()
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            }
            
            # 使用 Session 来追踪重定向
            session = requests.Session()
            
            if follow_redirects:
                response = session.get(
                    url, 
                    headers=headers, 
                    timeout=timeout, 
                    allow_redirects=True,
                    verify=True  # 验证 SSL
                )
                
                # 记录重定向历史
                if response.history:
                    for r in response.history:
                        debug_info["redirects"].append({
                            "url": r.url,
                            "status_code": r.status_code,
                            "reason": r.reason
                        })
            else:
                response = session.get(
                    url, 
                    headers=headers, 
                    timeout=timeout, 
                    allow_redirects=False,
                    verify=True
                )
            
            elapsed_time = (time.time() - start_time) * 1000
            debug_info["response_time_ms"] = round(elapsed_time, 2)
            
            # 记录响应头
            debug_info["headers"] = dict(response.headers)
            debug_info["final_url"] = response.url
            debug_info["encoding"] = response.encoding
            debug_info["content_type"] = response.headers.get('Content-Type', '')
            debug_info["content_length"] = response.headers.get('Content-Length', 'unknown')
            
            # 获取响应内容
            content = ""
            content_type = response.headers.get('Content-Type', '').lower()
            
            # 判断是否是文本类型
            is_text = any(t in content_type for t in ['text/', 'json', 'xml', 'javascript', 'html'])
            
            if show_content and is_text:
                try:
                    # 强制使用 UTF-8 编码
                    response.encoding = 'utf-8'
                    content = response.text
                    if len(content) > max_content_length:
                        content = content[:max_content_length] + f"\n\n... [内容已截断，共 {len(response.text)} 字符]"
                except Exception as e:
                    # 尝试其他编码
                    try:
                        content = response.content.decode('utf-8', errors='replace')
                        if len(content) > max_content_length:
                            content = content[:max_content_length] + "\n\n... [内容已截断]"
                    except Exception:
                        content = f"[无法解码内容: {e}]"
            elif not is_text:
                content = f"[二进制内容，类型: {content_type}，大小: {len(response.content)} bytes]"
            
            # 判断请求是否成功
            is_success = 200 <= response.status_code < 400
            
            # 构建结果摘要
            summary_lines = [
                f" URL: {url}",
                f" 状态码: {response.status_code} ({response.reason})",
                f"️ 响应时间: {debug_info['response_time_ms']}ms",
                f" Content-Type: {debug_info['content_type']}",
            ]
            
            if debug_info["redirects"]:
                summary_lines.append(f" 重定向次数: {len(debug_info['redirects'])}")
                summary_lines.append(f" 最终 URL: {response.url}")
            
            if response.status_code >= 400:
                summary_lines.append(f" 错误: HTTP {response.status_code}")
            
            summary = "\n".join(summary_lines)
            
            if show_content and content:
                summary += f"\n\n--- 响应内容 ---\n{content}"
            
            return {
                "success": is_success,
                "status_code": response.status_code,
                "content": summary,
                "error": "" if is_success else f"HTTP {response.status_code}: {response.reason}",
                "debug_info": debug_info
            }
            
        except requests.exceptions.SSLError as e:
            debug_info["ssl_info"] = str(e)
            logger.error(f"SSL 证书错误: {e}")
            
            # 尝试不验证 SSL 再请求一次获取更多信息
            try:
                response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, 
                                        timeout=timeout, verify=False, allow_redirects=follow_redirects)
                debug_info["ssl_bypass_status"] = response.status_code
                ssl_error_msg = f"SSL 证书验证失败，但跳过验证后可以访问 (状态码: {response.status_code})"
            except Exception:
                ssl_error_msg = "SSL 证书验证失败，即使跳过验证也无法访问"
            
            return {
                "success": False,
                "status_code": None,
                "content": f" SSL 证书错误\n\n{ssl_error_msg}\n\n详细错误: {str(e)}",
                "error": f"SSL Error: {str(e)}",
                "debug_info": debug_info
            }
            
        except requests.exceptions.Timeout as e:
            logger.error(f"请求超时: {e}")
            return {
                "success": False,
                "status_code": None,
                "content": f" 请求超时\n\n超时时间: {timeout} 秒\nURL: {url}",
                "error": f"Timeout: 请求超过 {timeout} 秒未响应",
                "debug_info": debug_info
            }
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"连接错误: {e}")
            error_str = str(e)
            
            # 分析具体错误类型
            if 'NameResolutionError' in error_str or 'getaddrinfo failed' in error_str:
                error_type = "DNS 解析失败 - 域名不存在或无法解析"
            elif 'Connection refused' in error_str:
                error_type = "连接被拒绝 - 目标服务器未监听该端口"
            elif 'Connection reset' in error_str:
                error_type = "连接被重置 - 服务器主动断开连接"
            elif 'Network is unreachable' in error_str:
                error_type = "网络不可达 - 无法路由到目标地址"
            else:
                error_type = "连接失败"
            
            return {
                "success": False,
                "status_code": None,
                "content": f" 连接错误\n\n错误类型: {error_type}\nURL: {url}\n\n详细信息: {error_str}",
                "error": f"Connection Error: {error_type}",
                "debug_info": debug_info
            }
            
        except requests.exceptions.TooManyRedirects as e:
            logger.error(f"重定向过多: {e}")
            return {
                "success": False,
                "status_code": None,
                "content": f" 重定向过多\n\n可能存在重定向循环\nURL: {url}",
                "error": "Too Many Redirects: 重定向次数超过限制",
                "debug_info": debug_info
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"请求异常: {e}")
            return {
                "success": False,
                "status_code": None,
                "content": f" 请求失败\n\nURL: {url}\n错误: {str(e)}",
                "error": str(e),
                "debug_info": debug_info
            }
            
        except Exception as e:
            logger.error(f"未知错误: {e}", exc_info=True)
            return {
                "success": False,
                "status_code": None,
                "content": f" 未知错误\n\nURL: {url}\n错误: {str(e)}",
                "error": str(e),
                "debug_info": debug_info
            }
    
    @classmethod
    def dispatch_tool(cls, tool_name: str, tool_args: dict, lang: str = "cn") -> dict:
        """分发工具调用
        
        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            lang: 语言
            
        Returns:
            {"status": "Success/Failed", "content": "...", "raw": ...}
        """
        try:
            if tool_name in ['get_compact_trajectory', 'GetCompactTrajectory']:
                chat_id = tool_args.get('chat_id', '')
                if not chat_id:
                    return {"status": "Failed", "content": "缺少 chat_id 参数", "raw": None}
                result = cls.get_compact_trajectory(chat_id=chat_id)
                return {"status": "Success", "content": '\n'.join(result), "raw": result}
            
            elif tool_name in ['get_Internal_Tool_files', 'GetInternal_ToolFiles']:
                chat_id = tool_args.get('chat_id', '')
                if not chat_id:
                    return {"status": "Failed", "content": "缺少 chat_id 参数", "raw": None}
                result = cls.get_Internal_Tool_files(chat_id=chat_id)
                return {"status": "Success", "content": json.dumps(result, ensure_ascii=False, indent=2), "raw": result}
            
            elif tool_name in ['write_analysis_file', 'WriteAnalysisFile']:
                chat_id = tool_args.get('chat_id', '')
                filename = tool_args.get('filename', '')
                content = tool_args.get('content', '')
                result = cls.write_analysis_file(chat_id=chat_id, filename=filename, content=content)
                if result["success"]:
                    return {"status": "Success", "content": result["message"], "raw": result}
                else:
                    return {"status": "Failed", "content": result["message"], "raw": result}
            
            elif tool_name in ['read_analysis_file', 'ReadAnalysisFile']:
                chat_id = tool_args.get('chat_id', '')
                filename = tool_args.get('filename', '')
                result = cls.read_analysis_file(chat_id=chat_id, filename=filename if filename else None)
                if result["success"]:
                    if result["content"]:
                        return {"status": "Success", "content": result["content"], "raw": result}
                    else:
                        # 返回文件列表
                        files_info = json.dumps(result["files"], ensure_ascii=False, indent=2)
                        return {"status": "Success", "content": f"目录下的文件列表:\n{files_info}", "raw": result}
                else:
                    return {"status": "Failed", "content": result["message"], "raw": result}
            
            elif tool_name in ['check_output_file', 'CheckOutputFile']:
                chat_id = tool_args.get('chat_id', '')
                full_path = tool_args.get('full_path', '')
                keyword = tool_args.get('keyword', None)
                context_lines = tool_args.get('context_lines', 3)
                result = cls.check_output_file(
                    chat_id=chat_id, 
                    full_path=full_path, 
                    keyword=keyword, 
                    context_lines=context_lines
                )
                if result["success"]:
                    return {"status": "Success", "content": result["content"], "raw": result}
                else:
                    return {"status": "Failed", "content": result["message"], "raw": result}
            
            elif tool_name in ['debug_link', 'DebugLink']:
                url = tool_args.get('url', '')
                timeout = tool_args.get('timeout', 10)
                follow_redirects = tool_args.get('follow_redirects', True)
                show_content = tool_args.get('show_content', True)
                max_content_length = tool_args.get('max_content_length', 5000)
                result = cls.debug_link(
                    url=url,
                    timeout=timeout,
                    follow_redirects=follow_redirects,
                    show_content=show_content,
                    max_content_length=max_content_length
                )
                if result["success"]:
                    return {"status": "Success", "content": result["content"], "raw": result}
                else:
                    return {"status": "Failed", "content": result["content"], "raw": result}
            
            else:
                return {"status": "Failed", "content": f"未知的工具: {tool_name}", "raw": None}
                
        except Exception as e:
            logger.error(f"工具执行失败: {e}", exc_info=True)
            return {"status": "Failed", "content": str(e), "raw": None}


class KimiModel:
    def __init__(self, base_url=None, project_name=None, model_name="AI_Platform-k2-0905-preview"):
        """初始化 Model
        
        Args:
            base_url: API 基础 URL
            project_name: 项目名称
        """
        self.AUTH_TOKEN = os.environ.get('OPENAI_API_KEY', '')
        if not self.AUTH_TOKEN:
            logger.warning('OPENAI_API_KEY 环境变量未设置，模型调用将失败')
        self.base_url = base_url or "https://internal.company.com/v1"
        self.model = model_name or "AI_Platform-k2-0905-preview"
        self.project_name = project_name
        
        # 记录初始化信息
        logger.info(f"KimiModel initialized with project_name='{project_name}'")

    def is_thinking_model(self):
        """检查是否是 thinking 模型"""
        return 'think' in self.model.lower()
    
    def request_model(self, request_body):
        """请求模型获取响应
        
        Returns:
            tuple: (content, tool_calls, reasoning_content)
                - content: 模型回复内容
                - tool_calls: 工具调用列表
                - reasoning_content: thinking 模型的推理内容（非 thinking 模型为 None）
        """
        _ensure_openai()  # 确保 OpenAI 已导入
        client = OpenAI(
            api_key=self.AUTH_TOKEN,
            base_url=self.base_url,
            http_client=httpx.Client(verify=False, timeout=10000)
        )
        try:
            resp = client.chat.completions.create (
                model=self.model,
                messages=request_body['messages'], 
                temperature=request_body['temperature'],
                max_tokens=32000,
                tools=request_body.get('tools', []),
                stream=False
            )
            
            message = resp.choices[0].message
            content = message.content
            tool_calls = message.tool_calls
            
            # 处理 thinking 模型的 reasoning_content
            reasoning_content = None
            if self.is_thinking_model():
                reasoning_content = getattr(message, 'reasoning_content', None)
            
            return content, tool_calls, reasoning_content
        finally:
            client.close()
    
    def request_model_stream(self, request_body):
        """请求模型获取流式响应
        
        Yields:
            dict: 各种事件类型
                - {"type": "reasoning", "delta": "..."} thinking 模型的推理内容
                - {"type": "content", "delta": "..."} 正常回复内容
                - {"type": "tool_calls", "tool_calls": [...]} 工具调用
                - {"type": "done", "content": "...", "reasoning_content": "..."} 完成
        """
        _ensure_openai()  # 确保 OpenAI 已导入
        client = OpenAI(
            api_key=self.AUTH_TOKEN,
            base_url=self.base_url,
            http_client=httpx.Client(verify=False, timeout=10000)
        )
        try:
            stream = client.chat.completions.create(
                model=self.model,
                messages=request_body['messages'], 
                temperature=request_body['temperature'],
                max_tokens=request_body.get('max_tokens', 32000),
                tools=request_body.get('tools', []),
                stream=True
            )
            
            full_content = ""
            full_reasoning = ""
            tool_calls_map = {}  # id -> {index, id, type, function: {name, arguments}}
            is_thinking = self.is_thinking_model()
            
            for chunk in stream:
                if not chunk.choices:
                    continue
                    
                delta = chunk.choices[0].delta
                
                # 处理 thinking 模型的 reasoning_content
                if is_thinking:
                    reasoning_delta = getattr(delta, 'reasoning_content', None)
                    if reasoning_delta:
                        full_reasoning += reasoning_delta
                        yield {"type": "reasoning", "delta": reasoning_delta}
                
                # 处理文本内容
                if delta.content:
                    full_content += delta.content
                    yield {"type": "content", "delta": delta.content}
                
                # 处理工具调用
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        tc_id = tc.id or list(tool_calls_map.keys())[-1] if tool_calls_map else None
                        
                        if tc.id:  # 新的工具调用
                            tool_calls_map[tc.id] = {
                                "index": tc.index,
                                "id": tc.id,
                                "type": tc.type or "function",
                                "function": {
                                    "name": tc.function.name if tc.function else "",
                                    "arguments": tc.function.arguments if tc.function else ""
                                }
                            }
                        elif tc_id and tc.function:  # 追加参数
                            if tc.function.arguments:
                                tool_calls_map[tc_id]["function"]["arguments"] += tc.function.arguments
                
                # 检查是否结束
                if chunk.choices[0].finish_reason:
                    break
            
            # 最终返回工具调用（如果有）
            if tool_calls_map:
                yield {
                    "type": "tool_calls", 
                    "tool_calls": list(tool_calls_map.values()), 
                    "content": full_content,
                    "reasoning_content": full_reasoning if is_thinking else None
                }
            else:
                yield {
                    "type": "done", 
                    "content": full_content,
                    "reasoning_content": full_reasoning if is_thinking else None
                }
                
        finally:
            client.close()

    def request_model_with_tools(self, request_body={}, lang="cn"):
        """请求 AI_Platform 模型并处理搜索工具调用
        
        Returns:
            tuple: (final_content, messages) 返回最终内容、消息列表和 span ID
        """
        import copy
        
        prompt = copy.deepcopy(request_body)
        if not isinstance(prompt, dict):
            raise ValueError("无效的提示格式。期望一个字典。")
        
        messages = prompt['messages']
        config = {'temperature': prompt.get('temperature', 0.6), 'tools': prompt.get('tools', []), 'max_tokens': prompt.get('max_tokens', 32000)}
        
        def _execute_tool(tool_call):
            """执行单个工具调用"""
            args = json.loads(tool_call.function.arguments)
            logger.info(f"执行工具: {tool_call.function.name}, 参数: {args}")
            
            try:
                start = time.time()
                
                result = KimiInternalTools.dispatch_tool(
                    tool_name=tool_call.function.name,
                    tool_args=args,
                    lang=lang
                )
                
                elapsed = (time.time() - start) * 1000
                logger.info(f"工具执行耗时: {elapsed:.2f}ms")
                
                # dispatch_tool 返回字典: {"status": ..., "content": ..., "raw": ...}
                flag = result.get("status") == "Success"
                tool_resp = result.get("content", "")
                
                logger.debug(f"Tool {tool_call.function.name} executed successfully, response length: {len(tool_resp)}")
                
            except Exception as e:
                logger.error(f"工具调用失败: {e}", exc_info=True)
                flag, tool_resp = False, str(e)
            
            return {"role": "tool", "tool_call_id": tool_call.id, "name": tool_call.function.name, "content": tool_resp, "_is_generated": True, "_succ_flag": flag }
        
        try:
            turn_content, tool_calls, reasoning = self.request_model(
                request_body={'messages': messages, **config}
            )
            final_content = turn_content or ""
            final_reasoning = reasoning or ""
            
            MAX_TURNS = 10
            for turn in range(MAX_TURNS):
                if not tool_calls:
                    break
                
                logger.debug(f"工具调用轮次 {turn + 1}: {len(tool_calls)} 个调用")
                
                # 添加助手消息
                messages.append({
                    "role": "assistant", "content": turn_content,
                    "tool_calls": [{"index": tc.index, "id": tc.id, "type": tc.type,
                                  "function": {"name": tc.function.name, 
                                             "arguments": tc.function.arguments}}
                                 for tc in tool_calls],
                    "_is_generated": True})
                
                # add tools_call info to final_content
                if tool_calls:
                    for tool_call in tool_calls:
                        final_content += f"\n\n[模型调用 Tool Call: {tool_call.function.name}:{tool_call.id}: {tool_call.function.arguments}]\n\n"

                # 执行工具并添加结果
                messages.extend([_execute_tool(tc) for tc in tool_calls])

                # hide history search tool call content
                if lang == 'cn':
                    hide_replace = '历史 tool_call 结果已被隐藏'
                else:
                    hide_replace = 'The results of historical tool_calls have been hidden'
                # scan first to index -1 messages find 'tool_call_id and name is search or web_search or WebSearch
                for i in range(len(messages)-1):
                    msg = messages[i]
                    if 'tool_call_id' in msg and ( msg.get('name', '') == 'search' or msg.get('name', '') == 'web_search' or msg.get('name', '') == 'WebSearch'):
                        # replace content
                        messages[i]['content'] = hide_replace
                
                # 获取新响应

                # if last is tool call search or web_search, add special input message
                last_message = messages[-1]
                if 'tool_call_id' in last_message and ( last_message.get('name', '') == 'search' or last_message.get('name', '') == 'web_search' or last_message.get('name', '') == 'WebSearch'):
                    
                    # event prompt for search
                    search_event_message = KimiPrompts.get_event_prompt(event_type='search', lang=lang)  # noqa: F821

                    # add search_event_message in the trail to send to model, but not add to messages
                    request_messages = messages + [search_event_message]
                    content, tool_calls, reasoning = self.request_model(
                        {'messages': request_messages, **config}
                    )
                else:
                    content, tool_calls, reasoning = self.request_model(
                        {'messages': messages, **config}
                    )
                
                turn_content = content or ""
                final_content += '\n' + turn_content
                if reasoning:
                    final_reasoning += '\n' + reasoning
                
            else:
                if tool_calls:
                    logger.warning(f"达到最大工具调用轮数: {MAX_TURNS}")
            
            return final_content, messages, final_reasoning
        except Exception as e:
            logger.error(f"请求失败: {e}", exc_info=True)
            return '', messages, None

    def request_model_with_tools_stream(self, request_body={}, lang="cn"):
        """请求模型并处理工具调用（流式版本）
        
        Yields:
            dict: 各种事件类型
                - {"type": "reasoning", "delta": "..."} thinking 模型的推理增量
                - {"type": "content", "delta": "..."} 文本增量
                - {"type": "tool_call_start", "tool_call": {...}} 开始工具调用
                - {"type": "tool_call_result", "tool_call": {...}, "result": "..."} 工具调用结果
                - {"type": "done", "content": "...", "reasoning_content": "...", "messages": [...], "tool_calls_info": [...]} 完成
        """
        import copy
        
        prompt = copy.deepcopy(request_body)
        if not isinstance(prompt, dict):
            raise ValueError("无效的提示格式。期望一个字典。")
        
        messages = prompt['messages']
        config = {
            'temperature': prompt.get('temperature', 0.6), 
            'tools': prompt.get('tools', []), 
            'max_tokens': prompt.get('max_tokens', 32000)
        }
        
        tool_calls_info = []
        final_content = ""
        final_reasoning = ""
        
        def _execute_tool_from_dict(tool_call_dict):
            """执行工具调用（从字典）"""
            try:
                args = json.loads(tool_call_dict["function"]["arguments"])
            except Exception:
                args = {}
            
            logger.info(f"执行工具: {tool_call_dict['function']['name']}, 参数: {args}")
            
            try:
                start = time.time()
                result = KimiInternalTools.dispatch_tool(
                    tool_name=tool_call_dict["function"]["name"],
                    tool_args=args,
                    lang=lang
                )
                elapsed = (time.time() - start) * 1000
                logger.info(f"工具执行耗时: {elapsed:.2f}ms")
                
                flag = result.get("status") == "Success"
                tool_resp = result.get("content", "")
            except Exception as e:
                logger.error(f"工具调用失败: {e}", exc_info=True)
                flag, tool_resp = False, str(e)
            
            return {
                "role": "tool", 
                "tool_call_id": tool_call_dict["id"], 
                "name": tool_call_dict["function"]["name"], 
                "content": tool_resp, 
                "_is_generated": True, 
                "_succ_flag": flag
            }
        
        try:
            MAX_TURNS = 20
            for turn in range(MAX_TURNS):
                turn_content = ""
                current_tool_calls = None
                
                # 流式请求
                for event in self.request_model_stream({'messages': messages, **config}):
                    if event["type"] == "reasoning":
                        # 传递 thinking 模型的推理内容
                        final_reasoning += event["delta"]
                        yield event
                    elif event["type"] == "content":
                        turn_content += event["delta"]
                        final_content += event["delta"]
                        yield event
                    elif event["type"] == "tool_calls":
                        current_tool_calls = event["tool_calls"]
                        turn_content = event.get("content", "")
                        if event.get("reasoning_content"):
                            final_reasoning += event.get("reasoning_content", "")
                    elif event["type"] == "done":
                        turn_content = event.get("content", turn_content)
                        if event.get("reasoning_content"):
                            final_reasoning += event.get("reasoning_content", "")
                
                # 如果没有工具调用，结束
                if not current_tool_calls:
                    break
                
                # 添加助手消息到 messages
                messages.append({
                    "role": "assistant",
                    "content": turn_content,
                    "tool_calls": current_tool_calls,
                    "_is_generated": True
                })
                
                # 执行工具调用
                for tc in current_tool_calls:
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except Exception:
                        args = {}
                    
                    # 通知开始工具调用
                    yield {
                        "type": "tool_call_start",
                        "tool_call": {
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "arguments": args
                        }
                    }
                    
                    # 执行工具
                    tool_result = _execute_tool_from_dict(tc)
                    messages.append(tool_result)
                    
                    # 保存工具调用信息
                    tool_info = {
                        "name": tc["function"]["name"],
                        "arguments": args,
                        "result": tool_result["content"]
                    }
                    tool_calls_info.append(tool_info)
                    
                    # 通知工具结果
                    yield {
                        "type": "tool_call_result",
                        "tool_call": {
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "arguments": args
                        },
                        "result": tool_result["content"]
                    }
                
                # 通知本轮结束，UI 应为下一轮创建新的 chat_message
                yield {
                    "type": "turn_end",
                    "turn": turn + 1
                }
                
                # 添加换行分隔
                final_content += "\n"
            
            else:
                if current_tool_calls:
                    logger.warning(f"达到最大工具调用轮数: {MAX_TURNS}")
            
            # 完成
            yield {
                "type": "done",
                "content": final_content,
                "reasoning_content": final_reasoning if final_reasoning else None,
                "messages": messages,
                "tool_calls_info": tool_calls_info
            }
            
        except Exception as e:
            logger.error(f"请求失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "error": str(e),
                "content": final_content,
                "reasoning_content": final_reasoning if final_reasoning else None,
                "messages": messages,
                "tool_calls_info": tool_calls_info
            }

