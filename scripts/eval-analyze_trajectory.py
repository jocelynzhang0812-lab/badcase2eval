#!/usr/bin/env python3
"""
轨迹分析辅助脚本
用于从 trajectory 中提取关键信息和统计数据
"""

import re
import json
from typing import Dict, List, Any


def parse_trajectory(trajectory_text: str) -> Dict[str, Any]:
    """解析 trajectory 文本，提取结构化信息"""
    
    result = {
        "total_turns": 0,
        "total_steps": 0,
        "tool_calls": [],
        "exceptions": [],
        "user_queries": [],
        "model_responses": [],
        "token_usage": []
    }
    
    # 统计轮次
    turn_matches = re.findall(r'\[user_query\]\[turn_(\d+)\]', trajectory_text)
    result["total_turns"] = len(set(turn_matches))
    
    # 统计步骤
    step_matches = re.findall(r'\[model_resp\]\[turn_\d+\]\[step_(\d+)\]', trajectory_text)
    result["total_steps"] = len(step_matches)
    
    # 提取工具调用
    tool_pattern = r'\[tool_call\] Tool Name: (\S+) , Tool Call ID: (\S+) , Tool Args: ({.*?})'
    for match in re.finditer(tool_pattern, trajectory_text, re.DOTALL):
        tool_name = match.group(1)
        tool_id = match.group(2)
        try:
            tool_args = json.loads(match.group(3))
        except Exception:
            tool_args = {"raw": match.group(3)}
        
        result["tool_calls"].append({
            "name": tool_name,
            "id": tool_id,
            "args": tool_args
        })
    
    # 提取异常
    exception_pattern = r'\[Exception\] (.*?)(?=\n|$)'
    for match in re.finditer(exception_pattern, trajectory_text):
        result["exceptions"].append(match.group(1).strip())
    
    # 提取用户查询
    query_pattern = r'\[user_query\]\[turn_\d+\] (.*?)(?=\n|$)'
    for match in re.finditer(query_pattern, trajectory_text):
        result["user_queries"].append(match.group(1).strip())
    
    # 提取 Token 使用
    usage_pattern = r'\[model_usage\] ({.*?})'
    for match in re.finditer(usage_pattern, trajectory_text):
        try:
            usage = json.loads(match.group(1))
            result["token_usage"].append(usage)
        except Exception:
            pass
    
    return result


def analyze_tools(tool_calls: List[Dict]) -> Dict[str, Any]:
    """分析工具调用统计"""
    
    tool_stats = {}
    for call in tool_calls:
        name = call["name"]
        if name not in tool_stats:
            tool_stats[name] = {"count": 0, "args_keys": set()}
        tool_stats[name]["count"] += 1
        if isinstance(call.get("args"), dict):
            tool_stats[name]["args_keys"].update(call["args"].keys())
    
    # 转换 set 为 list 以便 JSON 序列化
    for name in tool_stats:
        tool_stats[name]["args_keys"] = list(tool_stats[name]["args_keys"])
    
    return {
        "unique_tools": len(tool_stats),
        "total_calls": len(tool_calls),
        "tool_breakdown": tool_stats
    }


def calculate_token_stats(token_usage_list: List[Dict]) -> Dict[str, Any]:
    """计算 Token 使用统计"""
    
    if not token_usage_list:
        return {}
    
    total_input = sum(u.get("input_tokens", 0) for u in token_usage_list)
    total_output = sum(u.get("output_tokens", 0) for u in token_usage_list)
    total = sum(u.get("total_tokens", 0) for u in token_usage_list)
    
    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total,
        "avg_input_per_step": total_input / len(token_usage_list) if token_usage_list else 0,
        "avg_output_per_step": total_output / len(token_usage_list) if token_usage_list else 0,
    }


def generate_summary(trajectory_text: str) -> str:
    """生成 trajectory 摘要报告"""
    
    parsed = parse_trajectory(trajectory_text)
    tool_analysis = analyze_tools(parsed["tool_calls"])
    token_stats = calculate_token_stats(parsed["token_usage"])
    
    lines = [
        "# Trajectory 分析摘要",
        "",
        "## 基本信息",
        f"- 总轮次: {parsed['total_turns']}",
        f"- 总步骤: {parsed['total_steps']}",
        f"- 工具调用次数: {tool_analysis['total_calls']}",
        f"- 唯一工具数: {tool_analysis['unique_tools']}",
        f"- 异常次数: {len(parsed['exceptions'])}",
        "",
        "## 工具调用统计"
    ]
    
    for tool_name, stats in tool_analysis["tool_breakdown"].items():
        lines.append(f"- {tool_name}: {stats['count']} 次")
    
    if token_stats:
        lines.extend([
            "",
            "## Token 使用统计",
            f"- 总输入: {token_stats['total_input_tokens']}",
            f"- 总输出: {token_stats['total_output_tokens']}",
            f"- 总计: {token_stats['total_tokens']}",
            f"- 平均每步输入: {token_stats['avg_input_per_step']:.1f}",
            f"- 平均每步输出: {token_stats['avg_output_per_step']:.1f}",
        ])
    
    if parsed["exceptions"]:
        lines.extend([
            "",
            "## 异常记录",
        ])
        for i, exc in enumerate(parsed["exceptions"], 1):
            lines.append(f"{i}. {exc}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python analyze_trajectory.py <trajectory_file>")
        sys.exit(1)
    
    with open(sys.argv[1], 'r') as f:
        trajectory_text = f.read()
    
    summary = generate_summary(trajectory_text)
    print(summary)

