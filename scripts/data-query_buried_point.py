#!/usr/bin/env python3
"""
火山埋点事件日志查询工具
用于查询用户埋点事件数据，支持按用户ID、时间范围、事件类型查询
"""

import requests
import json
import urllib.parse
import argparse
import sys
from datetime import datetime, timedelta
from typing import Optional, List

# API 配置
QUERY_URL = "http://172.24.128.60:8186/api/v1/feedback/events/query"
GRAFANA_BASE_URL = "https://internal.company.com/explore"
GRAFANA_DATASOURCE_UID = "aemjei2r0rocgb"

# 埋点事件列表
EVENT_LIST = [
    "msh_enter_chat_detail",
    "msh_sent_message",
    "msh_nppt_chat_start",
    "msh_nppt_chat_failed",
    "msh_nppt_save_start",
    "msh_nppt_frame_load_start",
    "msh_nppt_frame_load_end",
    "msh_nppt_frame_show_end",
    "msh_nppt_agentic_card_show",
    "msh_nppt_agentic_card_click",
    "msh_nppt_agentic_generate_end",
    "msh_nppt_generate_click",
    "msh_nppt_generate_close",
    "msh_nppt_generate_end",
    "msh_nppt_export_start",
    "msh_nppt_export_end",
    "msh_interrupt_reply",
    "msh_upload_file",
    "msh_upload_file_finish",
    "msh_bot_click",
    "msh_file_artifacts_show",
    "msh_file_artifacts_click",
    "msh_file_reader_download",
    "android_tech_net_status_count",
    "msh_payment_success",
    "msh_nppt_html_badcase",
    "msh_nppt_retry_dialog_click",
    "sandbox_file_response_url_click",
    "msh_tool_click",
    "msh_feedback_submit",
    "msh_dislike",
    "ios_dev_network_request_begin",
    "ios_dev_network_request_failed",
    "ios_dev_network_request_success",
    "ios_dev_stream_start",
    "ios_dev_stream_failed",
]

# 异常事件列表
EXCEPTION_EVENTS = [
    "msh_nppt_html_badcase",
    "msh_nppt_chat_failed",
    "msh_interrupt_reply",
]


def timestamp_to_date_str(timestamp: int) -> str:
    """时间戳(秒)转北京时间字符串"""
    dt = datetime.fromtimestamp(timestamp)
    dt_beijing = dt + timedelta(hours=8)
    return dt_beijing.strftime('%Y-%m-%d %H:%M:%S')


def timestamp_to_date_str_ms(timestamp: int) -> str:
    """时间戳转北京时间字符串 - 自动判断秒级或毫秒级"""
    try:
        # 如果时间戳大于 10^12，认为是毫秒级
        if timestamp > 1000000000000:
            dt_utc = datetime.utcfromtimestamp(timestamp / 1000)
        else:
            dt_utc = datetime.utcfromtimestamp(timestamp)
        dt_beijing = dt_utc + timedelta(hours=8)
        return dt_beijing.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, OSError):
        return str(timestamp)


def date_str_to_timestamp_ms(date_str: str) -> int:
    """北京时间字符串转时间戳(毫秒) UTC - 使用 calendar.timegm 避免时区问题"""
    import calendar
    
    time_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    
    for fmt in time_formats:
        try:
            dt_beijing = datetime.strptime(date_str, fmt)
            # 将北京时间当作 UTC 时间处理，然后减 8 小时
            # 使用 calendar.timegm 将 UTC 时间转为时间戳，避免本地时区影响
            dt_utc = dt_beijing - timedelta(hours=8)
            timestamp_sec = calendar.timegm(dt_utc.timetuple())
            return int(timestamp_sec * 1000)
        except ValueError:
            continue
    
    raise ValueError(f"无法解析时间格式: {date_str}，请使用 '2026-01-30 15:07:33' 格式")


def fetch_buried_point_events(
    query_id: str,
    start_time: int,
    end_time: int,
    event_list: List[str] = None,
    page_size: int = 100,
    debug: bool = False
) -> dict:
    """
    查询埋点事件
    
    Args:
        query_id: 用户ID
        start_time: 开始时间（毫秒时间戳）
        end_time: 结束时间（毫秒时间戳）
        event_list: 事件列表（可选）
        page_size: 每页数量
        debug: 是否打印调试信息
    
    Returns:
        API 返回的 JSON 数据
    """
    payload = {
        "query_id": query_id,
        "start_time": start_time,
        "end_time": end_time,
        "event_list": event_list if event_list else EVENT_LIST,
        "page_size": page_size
    }
    
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    
    if debug:
        print(f"[DEBUG] Request URL: {QUERY_URL}")
        print(f"[DEBUG] Request payload: {json.dumps(payload, indent=2)}")
        print(f"[DEBUG] Beijing time range: {timestamp_to_date_str_ms(start_time)} ~ {timestamp_to_date_str_ms(end_time)}")
    
    try:
        response = requests.post(QUERY_URL, json=payload, headers=headers, timeout=30)
        
        if debug:
            print(f"[DEBUG] Response status: {response.status_code}")
            print(f"[DEBUG] Response body: {response.text[:500]}")
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        raise Exception("API请求超时（30秒），请检查网络连接或稍后重试")
    except requests.exceptions.ConnectionError:
        raise Exception(f"无法连接到API服务器: {QUERY_URL}")


def generate_grafana_trace_url(
    chat_id: str,
    feedback_time: str,
    datasource_uid: str = GRAFANA_DATASOURCE_UID
) -> str:
    """
    生成 Grafana Trace 探索链接
    
    Args:
        chat_id: 会话ID
        feedback_time: 反馈时间（北京时间），如 "2026-01-30 15:07:33"
        datasource_uid: Grafana 数据源 UID
    
    Returns:
        Grafana Explore URL
    """
    # 解析时间
    time_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d"
    ]
    
    dt_beijing: Optional[datetime] = None
    for fmt in time_formats:
        try:
            dt_beijing = datetime.strptime(feedback_time, fmt)
            break
        except ValueError:
            continue
    
    if dt_beijing is None:
        raise ValueError(f"无法解析时间格式: {feedback_time}")
    
    # 转换为 UTC（北京时间 UTC+8，所以减 8 小时）
    dt_utc = dt_beijing - timedelta(hours=8)
    
    # 计算前后 6 小时
    start_time = dt_utc - timedelta(hours=6)
    end_time = dt_utc + timedelta(hours=6)
    
    # 格式化为 ISO 8601 UTC 格式
    from_str = start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    to_str = end_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    # 构建 panes JSON 结构
    panes = {
        "r8n": {
            "datasource": datasource_uid,
            "queries": [
                {
                    "refId": "A",
                    "queryType": "traceql",
                    "query": f'{{span.chat_id="{chat_id}"}}',
                    "datasource": {
                        "type": "tempo",
                        "uid": datasource_uid
                    },
                    "limit": 20,
                    "tableType": "traces",
                    "metricsQueryType": "range"
                }
            ],
            "range": {
                "from": from_str,
                "to": to_str
            }
        }
    }
    
    # 压缩 JSON 并 URL 编码
    panes_json = json.dumps(panes, separators=(',', ':'))
    panes_encoded = urllib.parse.quote(panes_json, safe='')
    
    # 拼接最终 URL
    url = f"{GRAFANA_BASE_URL}?schemaVersion=1&panes={panes_encoded}&orgId=1"
    return url


def parse_params(params_str) -> dict:
    """解析 params 字段（JSON 字符串）"""
    try:
        if isinstance(params_str, str):
            return json.loads(params_str)
        return params_str if isinstance(params_str, dict) else {}
    except Exception:
        return {}


def extract_key_fields(event: dict) -> dict:
    """从埋点事件中提取关键字段"""
    params = parse_params(event.get('params', '{}'))
    
    return {
        'event': event.get('event', ''),
        'time': timestamp_to_date_str_ms(event.get('time', 0)),
        'server_time': timestamp_to_date_str_ms(event.get('server_time', 0)),
        'conversation_id': params.get('msh_conversation_id', ''),
        'message_id': params.get('msh_message_id', ''),
        'message_type': params.get('msh_message_type', ''),
        'input_mode': params.get('input_mode', ''),
        'enter_from': params.get('enter_from', ''),
        'platform': params.get('platform', ''),
        'app_version': params.get('app_version', ''),
        'device_platform': params.get('device_platform', ''),
        'bot_name': params.get('msh_bot_name', ''),
        'req_scenario': params.get('req_scenario', ''),
        'slide_id': params.get('slide_id', ''),
        'browser': params.get('browser', ''),
        'browser_version': params.get('browser_version', ''),
        'badcase_info': params.get('badcase_info', ''),
        'is_success': params.get('is_success', ''),
        'error_reason': params.get('error_reason', ''),
        'raw_params': params,
    }


def query_by_user_and_time(
    user_id: str,
    feedback_time: str,
    time_range_hours: int = 1,
    event_list: List[str] = None,
    page_size: int = 100
) -> dict:
    """
    根据用户ID和反馈时间查询埋点
    
    Args:
        user_id: 用户ID
        feedback_time: 反馈时间（北京时间），如 "2026-01-30 15:07:33"
        time_range_hours: 前后时间范围（小时）
        event_list: 事件列表（可选）
        page_size: 每页数量
    
    Returns:
        包含查询结果和统计信息的字典
    """
    # 将反馈时间转换为时间戳
    timestamp_ms = date_str_to_timestamp_ms(feedback_time)
    
    # 计算查询时间范围
    start_time = timestamp_ms - (3600 * 1000 * time_range_hours)
    end_time = timestamp_ms + (3600 * 1000 * time_range_hours)
    
    # 查询埋点
    results = fetch_buried_point_events(
        query_id=user_id,
        start_time=start_time,
        end_time=end_time,
        event_list=event_list,
        page_size=page_size
    )
    
    # 解析事件
    events = results.get("data", {}).get("events", [])
    parsed_events = [extract_key_fields(event) for event in events]
    
    # 生成统计信息
    event_counts = {}
    conversation_ids = set()
    platforms = {}
    exception_events = []
    
    for event in parsed_events:
        # 事件类型统计
        event_name = event['event']
        event_counts[event_name] = event_counts.get(event_name, 0) + 1
        
        # 会话ID统计
        if event['conversation_id']:
            conversation_ids.add(event['conversation_id'])
        
        # 平台统计
        platform = event['platform']
        if platform:
            platforms[platform] = platforms.get(platform, 0) + 1
        
        # 异常事件
        if event_name in EXCEPTION_EVENTS:
            exception_events.append(event)
        # 失败事件
        if event.get('is_success') == 'false':
            if event not in exception_events:
                exception_events.append(event)
    
    return {
        'user_id': user_id,
        'feedback_time': feedback_time,
        'query_range': {
            'start_time': timestamp_to_date_str_ms(start_time),
            'end_time': timestamp_to_date_str_ms(end_time),
        },
        'total_events': len(parsed_events),
        'event_counts': event_counts,
        'conversation_ids': list(conversation_ids),
        'platforms': platforms,
        'exception_events': exception_events,
        'events': parsed_events,
        'grafana_urls': {
            conv_id: generate_grafana_trace_url(conv_id, feedback_time)
            for conv_id in conversation_ids
        },
        'raw_response': results,
    }


def query_by_conversation(
    conversation_id: str,
    user_id: str = None,
    time_range_hours: int = 6
) -> dict:
    """
    根据会话ID查询埋点
    
    Args:
        conversation_id: 会话ID
        user_id: 用户ID（可选，用于查询）
        time_range_hours: 时间范围（小时）
    
    Returns:
        查询结果
    """
    # 使用当前时间作为基准
    now = datetime.now()
    feedback_time = now.strftime("%Y-%m-%d %H:%M:%S")
    
    # 查询
    return query_by_user_and_time(
        user_id=user_id or "",
        feedback_time=feedback_time,
        time_range_hours=time_range_hours,
        page_size=1000
    )


def main():
    parser = argparse.ArgumentParser(description='火山埋点事件日志查询工具')
    parser.add_argument('--action', choices=['user_time', 'conversation'], required=True,
                        help='查询类型: user_time=按用户和时间查询, conversation=按会话查询')
    parser.add_argument('--user-id', help='用户ID')
    parser.add_argument('--conversation-id', help='会话ID (chat_id)')
    parser.add_argument('--feedback-time', help='反馈时间，格式: "2026-01-30 15:07:33" (北京时间)')
    parser.add_argument('--time-range', type=int, default=1, help='前后时间范围（小时），默认1小时')
    parser.add_argument('--page-size', type=int, default=100, help='每页数量，默认100')
    parser.add_argument('--output', '-o', help='输出文件路径（JSON格式）')
    parser.add_argument('--debug', action='store_true', help='打印调试信息')
    
    args = parser.parse_args()
    
    try:
        if args.action == 'user_time':
            if not args.user_id or not args.feedback_time:
                print("错误: --user-id 和 --feedback-time 参数必需", file=sys.stderr)
                sys.exit(1)
            
            # 打印调试信息
            if args.debug:
                print(f"[DEBUG] 用户ID: {args.user_id}")
                print(f"[DEBUG] 反馈时间: {args.feedback_time}")
                print(f"[DEBUG] 时间范围: {args.time_range}小时")
            
            results = query_by_user_and_time(
                user_id=args.user_id,
                feedback_time=args.feedback_time,
                time_range_hours=args.time_range,
                page_size=args.page_size
            )
            
        elif args.action == 'conversation':
            if not args.conversation_id:
                print("错误: --conversation-id 参数必需", file=sys.stderr)
                sys.exit(1)
            
            results = query_by_conversation(
                conversation_id=args.conversation_id,
                user_id=args.user_id,
                time_range_hours=args.time_range
            )
        
        # 输出结果
        json_output = json.dumps(results, indent=2, ensure_ascii=False)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(json_output)
            print(f"结果已保存到: {args.output}")
            print(f"总事件数: {results['total_events']}")
            print(f"会话数: {len(results['conversation_ids'])}")
            print(f"异常事件数: {len(results['exception_events'])}")
            
            # 如果没有数据，给出提示
            if results['total_events'] == 0:
                print("\n提示: 未查询到埋点数据，可能原因：")
                print("  1. 当前网络环境无法访问完整埋点数据（可能需要VPN/内网）")
                print("  2. 该用户在此时间段内确实没有埋点记录")
                print("  3. 用户ID格式不正确")
        else:
            print(json_output)
            
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

