#!/usr/bin/env python3
"""
Feedback 数据库检索工具
用于连接 regression 数据库查询用户反馈
支持 feedback、feedback_subscription、feedback_Internal_Tool 三个表
"""

import mysql.connector
import json
import sys
import argparse
from datetime import datetime

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_CONFIG_DIR = REPO_ROOT / "scripts"
if str(RUNTIME_CONFIG_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_CONFIG_DIR))

from runtime_config import get_regression_db_config

# 数据库连接配置
DB_CONFIG = get_regression_db_config(__file__)

def get_connection():
    """获取数据库连接"""
    return mysql.connector.connect(**DB_CONFIG)

def format_datetime(rows):
    """转换 datetime 为字符串以便 JSON 序列化"""
    for row in rows:
        for key, value in row.items():
            if isinstance(value, datetime):
                row[key] = value.isoformat()
    return rows

# ==================== feedback 表查询 ====================

def search_feedback_by_chat_id(chat_id: str, limit: int = 10):
    """根据 chat_id 搜索 feedback 表"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    query = """
        SELECT id, chat_id, user_feedback, created_at, status, 
               analysis_result, severity, issue_type
        FROM feedback 
        WHERE chat_id = %s 
        ORDER BY created_at DESC 
        LIMIT %s
    """
    
    cursor.execute(query, (chat_id, limit))
    results = cursor.fetchall()
    cursor.close()
    cnx.close()
    
    return format_datetime(results)

def search_feedback_by_keyword(keyword: str, limit: int = 20):
    """根据关键词搜索 feedback 表"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    query = """
        SELECT id, chat_id, user_feedback, created_at, status,
               analysis_result, severity, issue_type
        FROM feedback 
        WHERE user_feedback LIKE %s 
           OR analysis_result LIKE %s
        ORDER BY created_at DESC 
        LIMIT %s
    """
    
    like_pattern = f"%{keyword}%"
    cursor.execute(query, (like_pattern, like_pattern, limit))
    results = cursor.fetchall()
    cursor.close()
    cnx.close()
    
    return format_datetime(results)

def get_feedback_stats():
    """获取 feedback 表统计信息"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    cursor.execute("SELECT COUNT(*) as total FROM feedback")
    total = cursor.fetchone()['total']
    
    cursor.execute("""
        SELECT status, COUNT(*) as count 
        FROM feedback 
        GROUP BY status
    """)
    status_stats = cursor.fetchall()
    
    cursor.execute("""
        SELECT severity, COUNT(*) as count 
        FROM feedback 
        GROUP BY severity
    """)
    severity_stats = cursor.fetchall()
    
    cursor.execute("""
        SELECT issue_type, COUNT(*) as count 
        FROM feedback 
        WHERE issue_type IS NOT NULL
        GROUP BY issue_type
        ORDER BY count DESC
        LIMIT 10
    """)
    issue_type_stats = cursor.fetchall()
    
    cursor.close()
    cnx.close()
    
    return {
        'table': 'feedback',
        'total': total,
        'by_status': status_stats,
        'by_severity': severity_stats,
        'by_issue_type': issue_type_stats
    }

# ==================== feedback_subscription 表查询 ====================

def search_subscription_by_chat_id(chat_id: str, limit: int = 10):
    """根据 chat_id 搜索 feedback_subscription 表"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    query = """
        SELECT feedback_id, content, user_id, chat_id, segment_id,
               feedback_type, source, os_version, created_at,
               subscription_type, subscription_end_time, subscription_status,
               chat_model, subscription_region, ip_location, thumb_status,
               thread_id, version, device_model, related_features,
               problem_details, problem_type, skill_type, agent_swarm
        FROM feedback_subscription 
        WHERE chat_id = %s 
        ORDER BY created_at DESC 
        LIMIT %s
    """
    
    cursor.execute(query, (chat_id, limit))
    results = cursor.fetchall()
    cursor.close()
    cnx.close()
    
    return format_datetime(results)

def search_subscription_by_thread_id(thread_id: str, limit: int = 10):
    """根据 thread_id 搜索 feedback_subscription 表（[Internal Docs Platform]卡片线程ID）"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    query = """
        SELECT feedback_id, content, user_id, chat_id, segment_id,
               feedback_type, source, os_version, created_at,
               subscription_type, subscription_end_time, subscription_status,
               chat_model, subscription_region, ip_location, thumb_status,
               thread_id, version, device_model, related_features,
               problem_details, problem_type, skill_type, agent_swarm
        FROM feedback_subscription 
        WHERE thread_id = %s 
        ORDER BY created_at DESC 
        LIMIT %s
    """
    
    cursor.execute(query, (thread_id, limit))
    results = cursor.fetchall()
    cursor.close()
    cnx.close()
    
    return format_datetime(results)

def search_subscription_by_keyword(keyword: str, limit: int = 20):
    """根据关键词搜索 feedback_subscription 表"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    query = """
        SELECT feedback_id, content, user_id, chat_id, segment_id,
               feedback_type, source, created_at,
               subscription_type, subscription_status,
               subscription_region, thumb_status, thread_id
        FROM feedback_subscription 
        WHERE content LIKE %s 
           OR problem_details LIKE %s
           OR related_features LIKE %s
        ORDER BY created_at DESC 
        LIMIT %s
    """
    
    like_pattern = f"%{keyword}%"
    cursor.execute(query, (like_pattern, like_pattern, like_pattern, limit))
    results = cursor.fetchall()
    cursor.close()
    cnx.close()
    
    return format_datetime(results)

def search_subscription_by_thumb(thumb_status: int, limit: int = 20):
    """根据点赞状态搜索（0=无反馈，1=赞，2=踩）"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    query = """
        SELECT feedback_id, content, user_id, chat_id, created_at,
               subscription_type, subscription_status, thumb_status, thread_id
        FROM feedback_subscription 
        WHERE thumb_status = %s
        ORDER BY created_at DESC 
        LIMIT %s
    """
    
    cursor.execute(query, (thumb_status, limit))
    results = cursor.fetchall()
    cursor.close()
    cnx.close()
    
    return format_datetime(results)

def get_subscription_stats():
    """获取 feedback_subscription 表统计信息"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    cursor.execute("SELECT COUNT(*) as total FROM feedback_subscription")
    total = cursor.fetchone()['total']
    
    cursor.execute("""
        SELECT subscription_status, COUNT(*) as count 
        FROM feedback_subscription 
        GROUP BY subscription_status
    """)
    status_stats = cursor.fetchall()
    
    cursor.execute("""
        SELECT subscription_type, COUNT(*) as count 
        FROM feedback_subscription 
        GROUP BY subscription_type
    """)
    type_stats = cursor.fetchall()
    
    cursor.execute("""
        SELECT thumb_status, COUNT(*) as count 
        FROM feedback_subscription 
        GROUP BY thumb_status
    """)
    thumb_stats = cursor.fetchall()
    
    cursor.execute("""
        SELECT subscription_region, COUNT(*) as count 
        FROM feedback_subscription 
        GROUP BY subscription_region
    """)
    region_stats = cursor.fetchall()
    
    cursor.close()
    cnx.close()
    
    return {
        'table': 'feedback_subscription',
        'total': total,
        'by_subscription_status': status_stats,
        'by_subscription_type': type_stats,
        'by_thumb_status': thumb_stats,
        'by_region': region_stats
    }

# ==================== feedback_Internal_Tool 表查询 ====================

def search_Internal_Tool_by_chat_id(chat_id: str, limit: int = 10):
    """根据 chat_id 搜索 feedback_Internal_Tool 表"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    query = """
        SELECT feedback_id, feedback_content, user_id, chat_id, segment_id,
               feedback_type, meta, subscription_info, thumb_status,
               user_query, thread_id, skill_type, created_at
        FROM feedback_Internal_Tool 
        WHERE chat_id = %s 
        ORDER BY created_at DESC 
        LIMIT %s
    """
    
    cursor.execute(query, (chat_id, limit))
    results = cursor.fetchall()
    cursor.close()
    cnx.close()
    
    return format_datetime(results)

def search_Internal_Tool_by_thread_id(thread_id: str, limit: int = 10):
    """根据 thread_id 搜索 feedback_Internal_Tool 表（[Internal Docs Platform]卡片线程ID）"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    query = """
        SELECT feedback_id, feedback_content, user_id, chat_id, segment_id,
               feedback_type, meta, subscription_info, thumb_status,
               user_query, thread_id, skill_type, created_at
        FROM feedback_Internal_Tool 
        WHERE thread_id = %s 
        ORDER BY created_at DESC 
        LIMIT %s
    """
    
    cursor.execute(query, (thread_id, limit))
    results = cursor.fetchall()
    cursor.close()
    cnx.close()
    
    return format_datetime(results)

def search_Internal_Tool_by_keyword(keyword: str, limit: int = 20):
    """根据关键词搜索 feedback_Internal_Tool 表"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    query = """
        SELECT feedback_id, feedback_content, user_id, chat_id, created_at,
               thumb_status, thread_id, skill_type, feedback_type
        FROM feedback_Internal_Tool 
        WHERE feedback_content LIKE %s 
           OR user_query LIKE %s
        ORDER BY created_at DESC 
        LIMIT %s
    """
    
    like_pattern = f"%{keyword}%"
    cursor.execute(query, (like_pattern, like_pattern, limit))
    results = cursor.fetchall()
    cursor.close()
    cnx.close()
    
    return format_datetime(results)

def search_Internal_Tool_by_thumb(thumb_status: int, limit: int = 20):
    """根据点赞状态搜索 feedback_Internal_Tool 表"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    query = """
        SELECT feedback_id, feedback_content, user_id, chat_id, created_at,
               thumb_status, thread_id, skill_type, feedback_type
        FROM feedback_Internal_Tool 
        WHERE thumb_status = %s
        ORDER BY created_at DESC 
        LIMIT %s
    """
    
    cursor.execute(query, (thumb_status, limit))
    results = cursor.fetchall()
    cursor.close()
    cnx.close()
    
    return format_datetime(results)

def get_Internal_Tool_stats():
    """获取 feedback_Internal_Tool 表统计信息"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    cursor.execute("SELECT COUNT(*) as total FROM feedback_Internal_Tool")
    total = cursor.fetchone()['total']
    
    cursor.execute("""
        SELECT feedback_type, COUNT(*) as count 
        FROM feedback_Internal_Tool 
        GROUP BY feedback_type
    """)
    type_stats = cursor.fetchall()
    
    cursor.execute("""
        SELECT thumb_status, COUNT(*) as count 
        FROM feedback_Internal_Tool 
        GROUP BY thumb_status
    """)
    thumb_stats = cursor.fetchall()
    
    cursor.execute("""
        SELECT skill_type, COUNT(*) as count 
        FROM feedback_Internal_Tool 
        WHERE skill_type IS NOT NULL
        GROUP BY skill_type
        ORDER BY count DESC
        LIMIT 10
    """)
    skill_stats = cursor.fetchall()
    
    cursor.close()
    cnx.close()
    
    return {
        'table': 'feedback_Internal_Tool',
        'total': total,
        'by_feedback_type': type_stats,
        'by_thumb_status': thumb_stats,
        'by_skill_type': skill_stats
    }

# ==================== 联合查询 ====================

def search_combined_by_chat_id(chat_id: str, limit: int = 10):
    """联合查询三个表，获取完整反馈信息"""
    cnx = get_connection()
    cursor = cnx.cursor(dictionary=True)
    
    # 查询 feedback 表
    cursor.execute("""
        SELECT id, chat_id, user_feedback, created_at, status, 
               analysis_result, severity, issue_type
        FROM feedback 
        WHERE chat_id = %s 
        ORDER BY created_at DESC
        LIMIT %s
    """, (chat_id, limit))
    feedback_results = cursor.fetchall()
    
    # 查询 feedback_subscription 表
    cursor.execute("""
        SELECT feedback_id, content, user_id, created_at,
               subscription_type, subscription_status, thumb_status,
               thread_id, problem_type, skill_type
        FROM feedback_subscription 
        WHERE chat_id = %s 
        ORDER BY created_at DESC
        LIMIT %s
    """, (chat_id, limit))
    subscription_results = cursor.fetchall()
    
    # 查询 feedback_Internal_Tool 表
    cursor.execute("""
        SELECT feedback_id, feedback_content, user_id, chat_id, created_at,
               thumb_status, thread_id, skill_type, feedback_type,
               user_query, meta, subscription_info
        FROM feedback_Internal_Tool 
        WHERE chat_id = %s 
        ORDER BY created_at DESC
        LIMIT %s
    """, (chat_id, limit))
    Internal_Tool_results = cursor.fetchall()
    
    cursor.close()
    cnx.close()
    
    return {
        'chat_id': chat_id,
        'feedback_table': format_datetime(feedback_results),
        'subscription_table': format_datetime(subscription_results),
        'Internal_Tool_table': format_datetime(Internal_Tool_results)
    }

def main():
    parser = argparse.ArgumentParser(description='Feedback 数据库检索工具')
    parser.add_argument('--action', 
                        choices=['chat_id', 'keyword', 'stats', 
                                'sub_chat_id', 'sub_thread_id', 'sub_keyword', 'sub_thumb', 'sub_stats',
                                'Internal_Tool_chat_id', 'Internal_Tool_thread_id', 'Internal_Tool_keyword', 'Internal_Tool_thumb', 'Internal_Tool_stats',
                                'combined'],
                        required=True, 
                        help='检索类型')
    parser.add_argument('--value', help='检索值（chat_id、关键词或 thread_id）')
    parser.add_argument('--thumb', type=int, choices=[0, 1, 2], help='点赞状态 (0=无, 1=赞, 2=踩)')
    parser.add_argument('--limit', type=int, default=10, help='返回结果数量限制')
    parser.add_argument('--output', '-o', help='输出文件路径（JSON格式）')
    
    args = parser.parse_args()
    
    try:
        if args.action == 'chat_id':
            if not args.value:
                print("错误: --value 参数需要提供 chat_id", file=sys.stderr)
                sys.exit(1)
            results = search_feedback_by_chat_id(args.value, args.limit)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'keyword':
            if not args.value:
                print("错误: --value 参数需要提供关键词", file=sys.stderr)
                sys.exit(1)
            results = search_feedback_by_keyword(args.value, args.limit)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'stats':
            results = get_feedback_stats()
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'sub_chat_id':
            if not args.value:
                print("错误: --value 参数需要提供 chat_id", file=sys.stderr)
                sys.exit(1)
            results = search_subscription_by_chat_id(args.value, args.limit)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'sub_thread_id':
            if not args.value:
                print("错误: --value 参数需要提供 thread_id（[Internal Docs Platform]卡片线程ID）", file=sys.stderr)
                sys.exit(1)
            results = search_subscription_by_thread_id(args.value, args.limit)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'sub_keyword':
            if not args.value:
                print("错误: --value 参数需要提供关键词", file=sys.stderr)
                sys.exit(1)
            results = search_subscription_by_keyword(args.value, args.limit)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'sub_thumb':
            if args.thumb is None:
                print("错误: --thumb 参数必需 (0=无反馈, 1=赞, 2=踩)", file=sys.stderr)
                sys.exit(1)
            results = search_subscription_by_thumb(args.thumb, args.limit)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'sub_stats':
            results = get_subscription_stats()
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'Internal_Tool_chat_id':
            if not args.value:
                print("错误: --value 参数需要提供 chat_id", file=sys.stderr)
                sys.exit(1)
            results = search_Internal_Tool_by_chat_id(args.value, args.limit)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'Internal_Tool_thread_id':
            if not args.value:
                print("错误: --value 参数需要提供 thread_id（[Internal Docs Platform]卡片线程ID）", file=sys.stderr)
                sys.exit(1)
            results = search_Internal_Tool_by_thread_id(args.value, args.limit)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'Internal_Tool_keyword':
            if not args.value:
                print("错误: --value 参数需要提供关键词", file=sys.stderr)
                sys.exit(1)
            results = search_Internal_Tool_by_keyword(args.value, args.limit)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'Internal_Tool_thumb':
            if args.thumb is None:
                print("错误: --thumb 参数必需 (0=无反馈, 1=赞, 2=踩)", file=sys.stderr)
                sys.exit(1)
            results = search_Internal_Tool_by_thumb(args.thumb, args.limit)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'Internal_Tool_stats':
            results = get_Internal_Tool_stats()
            print(json.dumps(results, indent=2, ensure_ascii=False))
            
        elif args.action == 'combined':
            if not args.value:
                print("错误: --value 参数需要提供 chat_id", file=sys.stderr)
                sys.exit(1)
            results = search_combined_by_chat_id(args.value, args.limit)
            json_output = json.dumps(results, indent=2, ensure_ascii=False)
            
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(json_output)
                print(f"结果已保存到: {args.output}")
            else:
                print(json_output)
            
    except mysql.connector.Error as err:
        print(f"数据库错误: {err}", file=sys.stderr)
        sys.exit(1)
    except Exception as err:
        print(f"错误: {err}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()

