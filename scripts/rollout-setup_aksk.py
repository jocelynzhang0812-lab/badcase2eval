#!/usr/bin/env python3
"""
setup_aksk.py  自动配置 Platform AKSK（一键补齐所有 key）

读取本地环境变量，自动在 Platform 上创建缺失的 AKSK Secret。
小白只需要在 .env 里填好 key，跑这个脚本就行。

用法:
    # 检查哪些 key 缺失（不创建）
    python scripts/setup_aksk.py --check

    # 自动补齐缺失的 key
    python scripts/setup_aksk.py

    # 指定额外的 key
    python scripts/setup_aksk.py --extra "MY_CUSTOM_KEY"

环境变量:
    AuthGateway_ACCESS_TOKEN  Platform 认证（必需）
    OPENAI_API_KEY  Internal_AI_Service API
    SEARCH_TOKEN  搜索 token
    DATASOURCE_KEY  数据源 key
    ANTHROPIC_API_KEY  Internal_AI_Service API（和 OPENAI_API_KEY 一样）
"""

import argparse
import json
import os
import sys

try:
    import httpx
    CLIENT = httpx.Client(timeout=15)
except ImportError:
    import urllib.request
    import urllib.error
    CLIENT = None

ORBIT_BASE = os.environ.get("ORBIT_API_BASE", "https://platform.internal.ai.com")

# 需要配置的 key 列表
# (key_name, description, required)
EXPECTED_KEYS = [
    ("OPENAI_API_KEY",        "Internal_AI_Service API key（跑模型用）",                              True),
    ("ANTHROPIC_API_KEY",     "Internal_AI_Service API key（kimi_chat/kimi_agent 必需）",              True),
    ("AuthGateway_ACCESS_TOKEN", "Platform 认证 token",                                      True),
    ("SEARCH_TOKEN",          "搜索 token（搜索评测用）",                              False),
    ("DATASOURCE_KEY",        "数据源 key（数据源评测用）",                            False),
]

for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(k, None)


def api_request(method, url, headers, data=None):
    """兼容 httpx 和 urllib 的请求"""
    if CLIENT:
        if method == "GET":
            resp = CLIENT.get(url, headers=headers)
        else:
            resp = CLIENT.post(url, headers=headers, json=data)
        return resp.status_code, resp.json()
    else:
        req = urllib.request.Request(url, method=method, headers=headers)
        if data:
            req.data = json.dumps(data).encode()
            req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read()) if e.read() else {}


def get_existing_aksk(token):
    """获取已有的 AKSK 列表"""
    status, data = api_request(
        "GET", f"{ORBIT_BASE}/api/aksk",
        {"X-AuthGateway-Access-Token": token},
    )
    if status != 200:
        print(f" 获取 AKSK 失败: {status}")
        return {}

    items = data if isinstance(data, list) else data.get("items", data.get("success", []))
    if isinstance(items, dict) and "items" in items:
        items = items["items"]
    if not isinstance(items, list):
        items = []

    existing = {}
    for item in items:
        key = item.get("key", "")
        if key:
            existing[key] = {
                "id": item.get("id"),
                "masked": item.get("maskedValue", ""),
            }
    return existing


def create_aksk(token, key, value):
    """创建一个 AKSK"""
    status, data = api_request(
        "POST", f"{ORBIT_BASE}/api/aksk",
        {"X-AuthGateway-Access-Token": token, "Content-Type": "application/json"},
        {"key": key, "value": value},
    )
    return status == 200 and (data.get("success", False) or isinstance(data, dict))


def main():
    parser = argparse.ArgumentParser(description="自动配置 Platform AKSK")
    parser.add_argument("--check", action="store_true", help="只检查不创建")
    parser.add_argument("--extra", default=None, help="额外的 key（逗号分隔）")
    args = parser.parse_args()

    token = os.environ.get("AuthGateway_ACCESS_TOKEN", "")
    if not token:
        print(" 请设置 AuthGateway_ACCESS_TOKEN 环境变量")
        sys.exit(1)

    # 获取已有 AKSK
    print(" 检查已有 AKSK...")
    existing = get_existing_aksk(token)
    print(f"   已有 {len(existing)} 个: {', '.join(existing.keys())}")

    # 检查需要的 key
    keys_to_check = list(EXPECTED_KEYS)
    if args.extra:
        for k in args.extra.split(","):
            k = k.strip()
            if k:
                keys_to_check.append((k, "自定义 key"))

    missing = []
    print(f"\n 检查 {len(keys_to_check)} 个 key:\n")

    for entry in keys_to_check:
        if len(entry) == 3:
            key_name, description, required = entry
        else:
            key_name, description = entry
            required = True
        in_orbit = key_name in existing
        in_env = bool(os.environ.get(key_name))

        if in_orbit:
            masked = existing[key_name]["masked"]
            print(f"   {key_name}: 已在 Platform (id={existing[key_name]['id']}, {masked})")
        elif in_env:
            val = os.environ[key_name]
            print(f"  ️  {key_name}: 本地有但 Platform 没有 → {'待创建' if not args.check else '需要创建'}")
            missing.append((key_name, val, description))
        elif required:
            print(f"   {key_name}: 本地和 Platform 都没有  {description}")
        else:
            print(f"   {key_name}: 未配置（可选） {description}")

    if not missing:
        print("\n 所有 key 都已配置，无需操作！")
        return

    if args.check:
        print(f"\n️  {len(missing)} 个 key 需要创建。去掉 --check 自动创建。")
        return

    # 自动创建
    print(f"\n 自动创建 {len(missing)} 个 AKSK...\n")
    success = 0
    for key_name, value, description in missing:
        print(f"  创建 {key_name}...", end=" ")
        if create_aksk(token, key_name, value):
            print("")
            success += 1
        else:
            print(" 失败")

    print(f"\n{'=' * 40}")
    print(f" 创建成功: {success}/{len(missing)}")
    if success == len(missing):
        print(" 所有 AKSK 配置完成，可以跑评测了！")


if __name__ == "__main__":
    main()
