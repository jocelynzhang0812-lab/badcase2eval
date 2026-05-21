#!/usr/bin/env python3
"""
bitable_to_orbit.py  从[Internal Docs Platform]多维表格读数据，上传到 Platform

一键完成：[Internal Docs Platform]多维表格 → JSONL → Platform Dataset

用法:
    # 从 URL 读取，输出 JSONL
    python scripts/bitable_to_orbit.py \
        "https://internal-docs.company.com/base/appXXX?table=tblYYY" \
        -o dataset.jsonl

    # 中文字段自动映射成英文
    python scripts/bitable_to_orbit.py \
        "https://internal-docs.company.com/base/appXXX?table=tblYYY" \
        --field-map "问题:query,评判标准:rubric,场景:scenario,难度:difficulty" \
        -o dataset.jsonl

    # 直接上传 Platform（不落地 JSONL）
    python scripts/bitable_to_orbit.py \
        "https://internal-docs.company.com/base/appXXX?table=tblYYY" \
        --upload --dataset-name "search-quality-v1" \
        --input-fields query,rubric \
        --field-map "问题:query,评判标准:rubric"

    # 用 app_token + table_id（不用 URL）
    python scripts/bitable_to_orbit.py \
        --app-token appXXX --table-id tblYYY \
        -o dataset.jsonl

    # --fields 筛选（不改名，只选列）
    if args.fields and not field_map:
        keep = {f.strip() for f in args.fields.split(",")}
        rows = [{k: v for k, v in row.items() if k in keep} for row in rows]
        print(f"   保留字段: {list(keep)}（忽略了其他字段）")

    # 预览前 5 条
    python scripts/bitable_to_orbit.py \
        "https://internal-docs.company.com/base/appXXX?table=tblYYY" \
        --preview 5

环境变量:
    在 Kitty 环境中自动认证，无需额外配置。
    上传 Platform 需要 AuthGateway_ACCESS_TOKEN。
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ---------- URL 解析 ----------

def parse_bitable_url(url: str) -> tuple[str, str]:
    """从[Internal Docs Platform]多维表格 URL 提取 app_token 和 table_id

    支持格式:
      https://xxx.feishu.cn/base/appXXX?table=tblYYY
      https://xxx.feishu.cn/base/appXXX?table=tblYYY&view=vewZZZ
    """
    parsed = urlparse(url)
    path = parsed.path

    # 提取 app_token
    match = re.search(r'/base/([a-zA-Z0-9]+)', path)
    if not match:
        raise ValueError(f"无法从 URL 提取 app_token: {url}")
    app_token = match.group(1)

    # 提取 table_id
    params = parse_qs(parsed.query)
    table_id = params.get("table", [None])[0]
    if not table_id:
        raise ValueError(f"URL 中缺少 table 参数: {url}")

    return app_token, table_id


# ---------- 字段值处理 ----------

def flatten_field_value(value) -> str:
    """把[Internal Docs Platform]多维表格的复杂字段值转成简单字符串

    多维表格字段值可能是：
    - 字符串/数字/布尔 → 直接用
    - 列表（多选/人员）→ 逗号连接
    - 字典（链接/附件）→ 提取 text 或 link
    - None → 空字符串
    """
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                # 人员字段 {"name": "xxx", "id": "xxx"}
                # 链接字段 {"text": "xxx", "link": "xxx"}
                parts.append(
                    item.get("text", item.get("name", item.get("value", str(item))))
                )
            else:
                parts.append(str(item))
        return ", ".join(parts)
    if isinstance(value, dict):
        # 单个链接/附件
        return value.get("text", value.get("name", value.get("value", json.dumps(value, ensure_ascii=False))))
    return str(value)


# ---------- [Internal Docs Platform]读取 ----------

def get_feishu_client():
    """获取[Internal Docs Platform]客户端（Kitty 环境自动认证）"""
    # 尝试 Kitty 环境
    try:
        skill_dir = Path(__file__).resolve().parent.parent
        # 尝试多个可能的 kitty-feishu 路径
        for candidate in [
            skill_dir / "kitty-feishu" / "scripts",
            Path.home() / ".kitty" / "workers",
        ]:
            if not candidate.exists():
                continue
            # 搜索 kitty_feishu.py
            for p in candidate.rglob("kitty_feishu.py"):
                sys.path.insert(0, str(p.parent))
                break

        from kitty_feishu import KittyFeishuClient

        # 获取 session_key
        kitty_api_base = os.environ.get("KITTY_API_BASE", "")
        kitty_api_token = os.environ.get("KITTY_API_TOKEN", "")
        if kitty_api_base and kitty_api_token:
            # 从 Kitty API 获取 session_key
            import httpx
            resp = httpx.get(
                f"{kitty_api_base}/feishu/session-key",
                headers={"Authorization": f"Bearer {kitty_api_token}"},
                timeout=10,
            )
            session_key = resp.json().get("session_key", "")
            if session_key:
                return KittyFeishuClient(session_key=session_key)

        print("️ 未检测到 Kitty 环境，尝试其他认证方式...")

    except Exception as e:
        print(f"️ Kitty 客户端初始化失败: {e}")

    # Fallback: 直接用[Internal Docs Platform] API
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        print(" 需要设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET 环境变量")
        print("   或在 Kitty 环境中运行（自动认证）")
        sys.exit(1)

    # 简单的直连客户端
    return SimpleFeishuClient(app_id, app_secret)


class SimpleFeishuClient:
    """简单的[Internal Docs Platform] API 客户端（不依赖 Kitty）"""

    def __init__(self, app_id: str, app_secret: str):
        import httpx
        self.http = httpx.Client(timeout=30)
        self.base = "https://open.feishu.cn/open-apis"
        # 获取 tenant_access_token
        resp = self.http.post(
            f"{self.base}/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        self.token = resp.json().get("tenant_access_token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def get_bitable_fields(self, app_token, table_id):
        resp = self.http.get(
            f"{self.base}/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            headers=self.headers,
        )
        return resp.json().get("data", {}).get("items", [])

    def query_bitable(self, app_token, table_id, filters=None, page_size=100):
        payload = {"page_size": page_size}
        resp = self.http.post(
            f"{self.base}/bitable/v1/apps/{app_token}/tables/{table_id}/records/search",
            headers=self.headers,
            json=payload,
        )
        return resp.json().get("data", {}).get("items", [])


def read_bitable(client, app_token: str, table_id: str) -> tuple[list[dict], list[str]]:
    """读取多维表格的所有记录"""
    # 获取字段
    fields = client.get_bitable_fields(app_token, table_id)
    field_names = [f.get("field_name", "") for f in fields]
    print(f"   字段: {field_names}")

    # 获取记录
    records = client.query_bitable(app_token, table_id, page_size=500)
    print(f"   记录数: {len(records)}")

    # 展开 fields
    rows = []
    for rec in records:
        rec_fields = rec.get("fields", {})
        row = {}
        for name, value in rec_fields.items():
            row[name] = flatten_field_value(value)
        rows.append(row)

    return rows, field_names


# ---------- 主流程 ----------

def main():
    parser = argparse.ArgumentParser(description="[Internal Docs Platform]多维表格 → Platform")
    parser.add_argument("url", nargs="?", default=None, help="[Internal Docs Platform]多维表格 URL")
    parser.add_argument("--app-token", default=None, help="app_token（不用 URL 时）")
    parser.add_argument("--table-id", default=None, help="table_id（不用 URL 时）")
    parser.add_argument("--field-map", default=None,
                        help="字段映射（中文:英文,中文:英文）如 '问题:query,评判标准:rubric'。只导出映射的字段")
    parser.add_argument("--fields", default=None,
                        help="只导出这些字段（逗号分隔，不改名）如 'query,rubric,scenario'")
    parser.add_argument("-o", "--output", default=None, help="输出 JSONL 路径")
    parser.add_argument("--preview", type=int, default=None, help="预览前 N 条")

    # Platform 上传参数
    parser.add_argument("--upload", action="store_true", help="直接上传到 Platform")
    parser.add_argument("--dataset-name", default=None, help="Platform Dataset 名称")
    parser.add_argument("--input-fields", default=None, help="Platform Input 字段（逗号分隔）")
    parser.add_argument("--metadata-fields", default=None, help="Platform Metadata 字段（逗号分隔）")
    parser.add_argument("--description", default="", help="Dataset 描述")
    parser.add_argument("--tag", default=None, help="Dataset tag")

    args = parser.parse_args()

    # 解析 app_token 和 table_id
    if args.url:
        app_token, table_id = parse_bitable_url(args.url)
    elif args.app_token and args.table_id:
        app_token, table_id = args.app_token, args.table_id
    else:
        print(" 请提供[Internal Docs Platform]多维表格 URL 或 --app-token + --table-id")
        sys.exit(1)

    print(f" [Internal Docs Platform]多维表格: app={app_token}, table={table_id}")

    # 解析字段映射
    field_map = {}
    if args.field_map:
        for pair in args.field_map.split(","):
            parts = pair.strip().split(":")
            if len(parts) == 2:
                field_map[parts[0].strip()] = parts[1].strip()
        print(f" 字段映射: {field_map}")

    # 读取数据
    print("\n 读取[Internal Docs Platform]多维表格...")
    client = get_feishu_client()
    rows, field_names = read_bitable(client, app_token, table_id)

    if not rows:
        print(" 没有读到数据")
        sys.exit(1)

    # 应用字段映射（指定了 field-map 则只保留映射的字段，其他忽略）
    if field_map:
        mapped_rows = []
        for row in rows:
            mapped = {}
            for k, v in row.items():
                if k in field_map:
                    mapped[field_map[k]] = v
                # 没在 field_map 里的字段 → 忽略
            mapped_rows.append(mapped)
        rows = mapped_rows
        print(f"   映射后字段: {list(field_map.values())}（忽略了 {len(field_names) - len(field_map)} 个字段）")

    # --fields 筛选（不改名，只选列）
    if args.fields and not field_map:
        keep = {f.strip() for f in args.fields.split(",")}
        rows = [{k: v for k, v in row.items() if k in keep} for row in rows]
        print(f"   保留字段: {list(keep)}（忽略了其他字段）")

    # 预览
    if args.preview:
        print(f"\n 预览前 {args.preview} 条:")
        for i, row in enumerate(rows[:args.preview]):
            print(f"\n  [{i}] {json.dumps(row, ensure_ascii=False)[:300]}")
        return

    # 输出 JSONL
    output_path = args.output or f"/tmp/bitable_{table_id}.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\n 已导出 {len(rows)} 条 → {output_path}")

    # 上传 Platform
    if args.upload:
        if not args.dataset_name:
            print(" 上传需要 --dataset-name")
            sys.exit(1)

        print(f"\n⬆️ 上传到 Platform: {args.dataset_name}")
        # 用 Platform CLI 上传
        orbit_cli = None
        for candidate in [
            Path(__file__).parent.parent / "skills" / "Platform" / "Platform.mjs",
            Path.home() / ".AI_Platform" / "skills" / "Platform" / "Platform.mjs",
        ]:
            if candidate.exists():
                orbit_cli = str(candidate)
                break
        if not orbit_cli:
            # 搜索
            for p in Path.home().rglob("skills/Platform/Platform.mjs"):
                orbit_cli = str(p)
                break

        if not orbit_cli:
            print(" 找不到 Platform CLI，请手动上传:")
            print(f"  node Platform.mjs upload {output_path} --dataset {args.dataset_name}")
            sys.exit(1)

        cmd = ["node", orbit_cli, "upload", output_path, "--dataset", args.dataset_name]
        if args.input_fields or args.metadata_fields:
            mapping = {}
            if args.input_fields:
                mapping["inputFields"] = [f.strip() for f in args.input_fields.split(",")]
            if args.metadata_fields:
                mapping["metadataFields"] = [f.strip() for f in args.metadata_fields.split(",")]
            cmd += ["--field-mapping", json.dumps(mapping)]

        import subprocess
        result = subprocess.run(cmd, cwd=str(Path(orbit_cli).parent))
        sys.exit(result.returncode)
    else:
        print("\n下一步:")
        print("  # 上传 Platform")
        print(f"  node Platform.mjs upload {output_path} --dataset <名称> --field-mapping '{{\"inputFields\":[\"query\",\"rubric\"]}}'")


if __name__ == "__main__":
    main()
