#!/usr/bin/env python3
"""脱敏脚本 - 将项目脱敏后用于 GitHub 公开发布"""

import os
import re
from pathlib import Path

DESENSITIZATION_RULES = {
    # AI_Platform 相关产品名称替换（优先级高）
    r'\bKimi\s+Code\b': 'AI_Code_Platform',
    r'\bkimi\s+code\b': 'ai_code_platform',
    r'\bKimi(?!\s+Code)\b': 'AI_Platform',
    r'\bkimi(?!\s+code)\b': 'ai_platform',
    r'\bkimi-([a-z0-9\-]+)': r'ai-\1',
    r'AI_Platform\.team': 'ai.internal.com',
    
    # AuthGateway 替换
    r'AuthGateway': 'AuthGateway',
    r'AuthGateway': 'auth_gateway',
    r'AuthGateway': 'AUTH_GATEWAY',
    
    # 内部域名替换
    r'https?://([a-z0-9\-]+\.)?msh\.team': 'https://internal.company.com',
    r'https?://([a-z0-9\-]+\.)?msh\.work': 'https://internal.company.com',
    r'https?://OpenAI-compatible\.feishu\.cn': 'https://internal-docs.company.com',
    r'https?://dev\.msh\.team': 'https://dev.internal.company.com',
    r'https?://deva\.msh\.team': 'https://internal.company.com',
    r'https?://chatty\.dev\.AI_Platform\.team': 'https://chatty.internal.ai.com',
    r'https?://Platform\.msh\.team': 'https://platform.internal.ai.com',
    r'https?://Platform\.deva\.msh\.team': 'https://platform.internal.ai.com',
    r'https?://vibe-coding-viewer\.app\.msh\.team': 'https://viewer.internal.ai.com',
    r'https?://model_checkpoint-[a-z0-9\-]+\.app\.msh\.team': 'https://model.internal.ai.com',
    r'https?://goldai_service\.msh\.team': 'https://models.internal.ai.com',
    r'https?://openai\.app\.msh\.team': 'https://gateway.internal.ai.com',
    
    # PyPI 镜像替换
    r'https?://pypi\.msh\.team': 'https://pypi.org',
    
    # 删除 internal.company.com 和 internal.company.com 的非 https 引用
    r'deva\.msh\.team': 'internal.company.com',
    r'msh\.team': 'internal.company.com',
    
    # 员工名字替换
    r'[Colleague Name 1]': '[Colleague Name 1]',
    r'[Colleague Name 2]': '[Colleague Name 2]',
    r'[Colleague Name 1]': '[Colleague Name 1]',
    r'[Colleague Name 2]': '[Colleague Name 2]',
    r'[Colleague Name 3]': '[Colleague Name 3]',
    r'[Colleague Name 4]': '[Colleague Name 4]',
    r'[Colleague Name 5]': '[Colleague Name 5]',
    
    # Internal_AI_Service → 替换为通用名称
    r'Internal_AI_Service': 'Internal_AI_Service',
    r'ai_service': 'ai_service',
    r'ai_service': 'AI_Service',
    
    # 内部平台提及
    r'[Internal Docs Platform]': '[Internal Docs Platform]',
    r'[Internal Chat Platform]': '[Internal Chat Platform]',
    r'Internal_Tool': 'Internal_Tool',
    
    # OpenAI-compatible → OpenAI-compatible
    r'\bMoonshot\b': 'OpenAI-compatible',
    r'\bmoonshot\b': 'openai-compatible',
    
    # Platform 保留但标记为内部
    r'\bOrbit\s+平台': 'Internal Evaluation Platform',
    r'\bOrbit\b': 'Platform',
    
    # 其他 AI_Platform 关键词
    r'model_checkpoint': 'model_checkpoint',
    r'model_checkpoint': 'model_checkpoint',
    
    # 删除所有 emoji
    r'[\U0001F000-\U0001FAFF]|[\u2600-\u27BF]|[\u2300-\u23FF]|[\u2000-\u206F]|[\u2700-\u27BF]': '',
}

def desensitize_content(content):
    """对文件内容进行脱敏"""
    # 逐个应用脱敏规则
    for pattern, replacement in DESENSITIZATION_RULES.items():
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
    return content

def process_file(input_file, output_file):
    """处理单个文件"""
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 对文本文件进行脱敏
        if any(input_file.endswith(ext) for ext in ['.md', '.py', '.yaml', '.yml', '.json', '.txt', '.env.example', '.toml', '.mjs']):
            content = desensitize_content(content)
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"处理失败: {input_file}")
        return False

def process_directory(input_dir, output_dir):
    """递归处理目录"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    processed = 0
    for item in input_path.rglob('*'):
        if item.is_file():
            relative_path = item.relative_to(input_path)
            output_item = output_path / relative_path
            if process_file(str(item), str(output_item)):
                processed += 1
        else:
            (output_path / item.relative_to(input_path)).mkdir(parents=True, exist_ok=True)
    
    return processed

if __name__ == '__main__':
    import sys
    input_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else '../evalskill-desensitized'
    processed = process_directory(input_dir, output_dir)
    print(f" 脱敏完成！已处理 {processed} 个文件")
