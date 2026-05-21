#!/usr/bin/env python3
"""
获取 Internal_Tool 聊天的完整对话轨迹（JSON格式）
用于深度分析对话结构、工具调用详情、异常信息等
"""

import json

from kimi_model import KimiInternalTools

import requests


def get_full_trajectory(chat_id: str, offset: int = 0, limit: int = 50) -> dict:
    """
    获取完整对话轨迹
    
    Args:
        chat_id: Internal_Tool 聊天 ID
        offset: 起始消息索引
        limit: 返回的消息数量
        
    Returns:
        包含完整消息数据的字典
    """
    
    # 1. 获取聊天元数据
    chat_df = KimiInternalTools.get_chat_content(chat_id)
    
    if chat_df is None or chat_df.empty:
        return {"error": "未找到轨迹数据"}
    
    total_messages = len(chat_df)
    
    # 2. 分页
    if offset >= total_messages:
        return {"error": f"偏移量 {offset} 超出总消息数 {total_messages}"}
    
    end_index = min(offset + limit, total_messages)
    chat_df = chat_df.iloc[offset:end_index].reset_index(drop=True)
    has_more = end_index < total_messages
    
    # 3. 获取每条消息的详细内容
    full_messages = []
    stats = {
        'total_blocks': 0,
        'tool_calls': 0,
        'tool_errors': 0,
        'exceptions': 0,
        'text_blocks': 0,
        'file_outputs': []
    }
    
    for idx, row in chat_df.iterrows():
        segment_id = row.get('id', '')
        role = row.get('role', '')
        depth = row.get('depth', '')
        
        if not segment_id:
            continue
        
        # 获取消息详情
        segment_content = KimiInternalTools.get_segment_content(segment_id)
        
        message_content = {
            'id': segment_id,
            'role': role,
            'depth': depth,
            'index': offset + idx
        }
        
        if segment_content and 'message' in segment_content:
            msg_data = segment_content['message']
            blocks = msg_data.get('message', {}).get('blocks', [])
            message_content['block_count'] = len(blocks)
            
            # 处理 blocks
            block_summaries = []
            for block in blocks:
                block_type = _extract_block_type(block)
                stats['total_blocks'] += 1
                
                summary = _extract_block_summary(block, block_type)
                
                # 对于 multiStage 和 stage 类型，保留原始 block 的完整内容
                if block_type in ['multiStage', 'stage']:
                    summary['_raw'] = block
                
                block_summaries.append(summary)
                
                # 更新统计
                if block_type == 'tool':
                    stats['tool_calls'] += 1
                    if summary.get('has_error'):
                        stats['tool_errors'] += 1
                elif block_type in ['toolResult', 'tool_result']:
                    if summary.get('has_error'):
                        stats['tool_errors'] += 1
                elif block_type == 'exception':
                    stats['exceptions'] += 1
                elif block_type == 'text':
                    stats['text_blocks'] += 1
                elif block_type == 'file' and role == 'assistant':
                    if summary.get('file_name'):
                        stats['file_outputs'].append({
                            'msg_id': segment_id,
                            'file_name': summary.get('file_name'),
                            'file_type': summary.get('file_type')
                        })
            
            message_content['blocks'] = block_summaries
            
            # 添加 trace URL（如果有）
            if 'traceUrl' in segment_content:
                message_content['trace_url'] = segment_content['traceUrl']
            
            # 从接口层获取 model response（如果是 user 消息）
            if role == 'user' and 'traceSemanticUrl' in segment_content:
                trace_url = KimiInternalTools.CHATLET_BASE_URL + segment_content['traceSemanticUrl']
                try:
                    resp = requests.get(trace_url, headers=KimiInternalTools.CHATLET_HEADERS, timeout=30)
                    if resp.status_code == 200:
                        trace_data = resp.json()
                        model_responses = []
                        
                        for workflow in trace_data.get('workflows', []):
                            for pipeline in workflow.get('pipelines', []):
                                for step in pipeline.get('steps', []):
                                    if step.get('kind') == 'KIND_MODEL_REQUEST':
                                        model_resp = step.get('response', {})
                                        model_responses.append({
                                            'content': model_resp.get('content', ''),
                                            'reasoning_content': model_resp.get('reasoning_content', ''),
                                            'tool_calls': model_resp.get('tool_calls', []),
                                            'usage': model_resp.get('usage', {}),
                                            'finish_reason': model_resp.get('finish_reason', ''),
                                            'model': model_resp.get('model', '')
                                        })
                        
                        message_content['model_responses'] = model_responses
                except Exception as e:
                    message_content['model_response_error'] = str(e)
        else:
            message_content['error'] = 'Failed to fetch content'
        
        full_messages.append(message_content)
    
    # 4. 组装结果
    result = {
        'summary': {
            'chat_id': chat_id,
            'total_messages': total_messages,
            'current_range': {
                'offset': offset,
                'limit': limit,
                'returned': len(chat_df),
                'has_more': has_more,
                'next_offset': end_index if has_more else None
            },
            'roles': chat_df['role'].unique().tolist() if 'role' in chat_df.columns else [],
            'statistics': stats
        },
        'messages': full_messages
    }
    
    return result


def _extract_block_type(block: dict) -> str:
    """提取 block 的类型"""
    type_priority = ['tool', 'toolResult', 'tool_result', 'text', 'think', 
                     'multiStage', 'stage', 'file', 'exception', 'error', 
                     'output', 'result']
    for key in type_priority:
        if key in block:
            return key
    return 'unknown'


def _extract_block_summary(block: dict, block_type: str) -> dict:
    """提取 block 的关键摘要信息"""
    summary = {'type': block_type}
    
    if block_type == 'tool':
        tool = block.get('tool', {})
        summary['tool_name'] = tool.get('name', 'unknown')
        summary['tool_call_id'] = tool.get('toolCallId', 'unknown')
        
        # 解析 args
        args_raw = tool.get('args', tool.get('arguments', '{}'))
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except Exception:
            args = {}
        
        summary['args_preview'] = str(args)[:200] + '...' if len(str(args)) > 200 else str(args)
        
        if tool.get('isError', False):
            summary['has_error'] = True
            
    elif block_type in ['toolResult', 'tool_result']:
        result = block.get(block_type, {})
        summary['status'] = result.get('status', 'unknown')
        summary['tool_call_id'] = result.get('toolCallId', result.get('tool_call_id', ''))
        
        content = result.get('content', '')
        if isinstance(content, dict):
            stderr = content.get('stderr', '')
            if stderr and ('error' in stderr.lower() or 'exception' in stderr.lower()):
                summary['has_error'] = True
                summary['error_preview'] = stderr[:200]
        elif isinstance(content, str) and ('error' in content.lower() or 'exception' in content.lower()):
            summary['has_error'] = True
            
    elif block_type == 'text':
        text = block.get('text', {}).get('content', '')
        summary['text_preview'] = text[:150] + '...' if len(text) > 150 else text
        
    elif block_type == 'file':
        file_info = block.get('file', {})
        summary['file_id'] = file_info.get('id', '')
        summary['file_name'] = file_info.get('file_name', 'N/A')
        summary['file_type'] = file_info.get('type', 'N/A')
        summary['content_type'] = file_info.get('content_type', 'N/A')
        
    elif block_type == 'exception':
        exc = block.get('exception', {})
        error_info = exc.get('error', {})
        summary['reason'] = error_info.get('reason', 'unknown')
        summary['severity'] = error_info.get('severity', 'unknown')
        
    elif block_type == 'think':
        think = block.get('think', {})
        content = think.get('content', '')
        summary['think_preview'] = content[:150] + '...' if len(content) > 150 else content
        
    elif block_type == 'multiStage':
        multi_stage = block.get('multiStage', {})
        if multi_stage:
            stages = multi_stage.get('stages', [])
            summary['stage_count'] = len(stages)
            summary['stage_ids'] = [s.get('id', 'unknown') for s in stages[:5]]
        summary['preview'] = 'Multi-stage process'
        
    elif block_type == 'stage':
        stage = block.get('stage', {})
        if stage:
            summary['stage_id'] = stage.get('id', 'unknown')
            summary['stage_name'] = stage.get('name', 'unknown')
            summary['stage_status'] = stage.get('status', 'unknown')
        summary['preview'] = 'Stage block'
        
    return summary


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='获取 Internal_Tool 完整对话轨迹')
    parser.add_argument('chat_id', help='Internal_Tool 聊天 ID')
    parser.add_argument('--offset', type=int, default=0, help='起始消息索引')
    parser.add_argument('--limit', type=int, default=50, help='返回消息数量')
    parser.add_argument('--output', '-o', help='输出文件路径')
    
    args = parser.parse_args()
    
    result = get_full_trajectory(args.chat_id, args.offset, args.limit)
    
    # 输出为 JSON
    json_output = json.dumps(result, ensure_ascii=False, indent=2)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(json_output)
        print(f" 结果已保存到: {args.output}")
    else:
        print(json_output)

