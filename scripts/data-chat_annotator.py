#!/usr/bin/env python3
"""
Chat 对话标注工具  自动分析 Chat 对话，提取每轮 query 并进行需求类型和场景打标

改编自 hualiang/claw-skills 的 chat-annotator skill

用法:
    python data-chat_annotator.py --chat-id <CHAT_ID>
    python data-chat_annotator.py --chat-id <CHAT_ID> --debug --full
    python data-chat_annotator.py --chat-id <CHAT_ID> --output result.csv --json result.json

环境变量:
    AuthGateway_ACCESS_TOKEN  GoldQuarry API 认证 (必需)

输出字段:
    chat_id, segment_id, query, 文件名, 轮次, 模型resp,
    是否点赞/点踩, 用户是否取消, 需求标签, 场景标签

需求类型 (8种):
    纠错/修复问题 | 新增Feature | 约束增强 | 新增同类产物
    产物转化 | Follow up questions | 独立问题 | 首轮对话

场景类型 (5种):
    vibe coding | ppt | excel表格 | docs文档 | 其他
"""

import argparse
import csv
import json
import os
import re
import sys
import urllib.request
import urllib.error
import ssl
from pathlib import Path

# ---------------------------------------------------------------------------
# API 配置
# ---------------------------------------------------------------------------

GOLDQUARRY_BASE = "https://internal.company.com"

# GPT-OSS 120B Judge 接口
GPT_OSS_URL = "https://gpt-oss-120b-judge.app.internal.company.com/v1/completions"


def _get_env(name, required=True):
    val = os.environ.get(name, "")
    if required and not val:
        print(f" 环境变量 {name} 未设置，请先 source .env", file=sys.stderr)
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# GoldQuarry API
# ---------------------------------------------------------------------------

# 模块级缓存 token，避免每次 API 调用都读环境变量
_AuthGateway_TOKEN = None


def _get_AuthGateway_token():
    global _AuthGateway_TOKEN
    if _AuthGateway_TOKEN is None:
        _AuthGateway_TOKEN = _get_env("AuthGateway_ACCESS_TOKEN")
    return _AuthGateway_TOKEN


def goldquarry_api(endpoint, data):
    """调用 GoldQuarry API"""
    token = _get_AuthGateway_token()
    url = f"{GOLDQUARRY_BASE}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "X-AuthGateway-Access-Token": token,
    }
    req = urllib.request.Request(
        url, data=json.dumps(data).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f" GoldQuarry API 错误 ({e.code}): {endpoint}\n   {body[:200]}", file=sys.stderr)
        raise
    except urllib.error.URLError as e:
        print(f" GoldQuarry API 连接失败: {e.reason}", file=sys.stderr)
        raise


# ---------------------------------------------------------------------------
# LLM 调用 (GPT-OSS 120B Judge)
# ---------------------------------------------------------------------------

def llm_classify(prompt, max_tokens=1200):
    """调用 GPT-OSS 120B Judge 进行分类"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    body = {
        "prompt": prompt,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }

    req = urllib.request.Request(
        GPT_OSS_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
            result = json.loads(resp.read().decode())
            return result.get("choices", [{}])[0].get("text", "").strip()
    except urllib.error.HTTPError as e:
        print(f" GPT-OSS API 错误 ({e.code})", file=sys.stderr)
        return ""
    except urllib.error.URLError as e:
        print(f" GPT-OSS API 连接失败: {e.reason}", file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------
# 数据提取
# ---------------------------------------------------------------------------

def extract_chat_data(chat_id):
    """从 GoldQuarry 提取 Chat 轮次数据"""
    print(f"[Step 1] 提取 Chat: {chat_id}", file=sys.stderr)

    result = goldquarry_api(
        "/api/chatlet.v2.ChatletService/ListMessages",
        {"chatId": chat_id, "limit": 100},
    )

    messages = []
    for entry in result.get("messageEntries", []):
        msg = entry.get("message", {})
        meta = msg.get("meta", {})
        messages.append(
            {"id": meta.get("id"), "role": meta.get("role"), "depth": meta.get("depth") or 0}
        )
    messages.sort(key=lambda x: x["depth"])

    def get_message_detail(msg_id):
        res = goldquarry_api(
            "/api/chatlet.v2.ChatletService/GetMessage", {"messageId": msg_id}
        )
        msg_data = res.get("message", {}).get("message", {})

        text = ""
        files = []
        for block in msg_data.get("blocks", []):
            if "text" in block:
                t = block["text"].get("content", "")
                if t:
                    text = f"{text}\n{t}" if text else t
            elif "artifact" in block:
                artifact = block["artifact"]
                atype = artifact.get("type", "")
                atitle = artifact.get("title", "")
                if atype == "ARTIFACT_TYPE_SLIDES_JSON":
                    try:
                        content = json.loads(artifact.get("content", "{}"))
                        outline = content.get("outline", {})
                        title = outline.get("pptTitle", "PPT")
                        count = outline.get("slidesCount", 0)
                        text = f"[PPT: {title}] - {count} 页幻灯片"
                    except Exception:
                        text = "[PPT 产物]"
                elif atype == "ARTIFACT_TYPE_CODE":
                    text = f"[代码产物: {atitle}]"
                elif atype == "ARTIFACT_TYPE_DOCX":
                    text = f"[Word文档: {atitle}]"
                elif atype == "ARTIFACT_TYPE_XLSX":
                    text = f"[Excel表格: {atitle}]"
                else:
                    text = f"[{atype}: {atitle}]"
            elif "slidesView" in block:
                sv = block["slidesView"]
                if not text:
                    text = f"[PPT预览: {sv.get('title', 'PPT')}] - {sv.get('totalCount', 0)} 页"
            if "file" in block:
                fname = block["file"].get("meta", {}).get("name", "")
                if fname:
                    files.append(fname)
        return {
            "content": text,
            "files": files,
            "vote": msg_data.get("vote"),
            "status": msg_data.get("status"),
        }

    rounds = []
    for i, msg in enumerate(messages):
        if msg["role"] != "user":
            continue
        assistant_msg = None
        for j in range(i + 1, len(messages)):
            if messages[j]["role"] == "assistant":
                assistant_msg = messages[j]
                break
        if assistant_msg:
            user_detail = get_message_detail(msg["id"])
            asst_detail = get_message_detail(assistant_msg["id"])
            rounds.append(
                {
                    "round": len(rounds) + 1,
                    "segment_id": assistant_msg["id"],
                    "query": user_detail["content"],
                    "files": user_detail["files"],
                    "response": asst_detail["content"],
                    "vote": asst_detail["vote"],
                    "is_cancelled": asst_detail["status"] != "MESSAGE_STATUS_COMPLETED",
                }
            )

    print(f"   {len(rounds)} 轮对话\n", file=sys.stderr)
    return rounds


# ---------------------------------------------------------------------------
# 分类 Prompt 构建与解析
# ---------------------------------------------------------------------------

FEW_SHOT = """【示例1】
上一轮: 我为你生成了一个销售报告PPT，包含10页内容。
本轮: PPT产物呢？没法下载
输出:
<analysis>
  <thinking>用户指出上一轮产物无法下载，要求修复</thinking>
  <requirement_type>纠错/修复问题</requirement_type>
  <scene_type>ppt</scene_type>
</analysis>

【示例2】
上一轮: 我为你创建了一个简单的个人网站首页。
本轮: 增加后台管理系统
输出:
<analysis>
  <thinking>用户要求增加新的功能模块</thinking>
  <requirement_type>新增Feature</requirement_type>
  <scene_type>vibe coding</scene_type>
</analysis>

【示例3】
上一轮: 我可以为你生成一个PPT。
本轮: 把搜索范围限定为2025年
输出:
<analysis>
  <thinking>用户对即将生成的产物追加约束条件</thinking>
  <requirement_type>约束增强</requirement_type>
  <scene_type>ppt</scene_type>
</analysis>

【示例4】
上一轮: 报告已生成，包含市场分析。
本轮: 按照这个报告模板，生成一个新的PPT
输出:
<analysis>
  <thinking>用户基于上一轮产物，要求生成类似的另一个产物</thinking>
  <requirement_type>新增同类产物</requirement_type>
  <scene_type>ppt</scene_type>
</analysis>

【示例5】
上一轮: 我为你创建了一个Word文档。
本轮: 根据这个文档再做一个PPT
输出:
<analysis>
  <thinking>用户要求跨模态转换（Word → PPT）</thinking>
  <requirement_type>产物转化</requirement_type>
  <scene_type>docs文档</scene_type>
</analysis>

【示例6】
上一轮: 销售数据显示Q3增长了20%。
本轮: 这个数据点来源是什么，列出来
输出:
<analysis>
  <thinking>用户追问数据来源，不要求改动上一轮产物</thinking>
  <requirement_type>Follow up questions</requirement_type>
  <scene_type>excel表格</scene_type>
</analysis>

【示例7】
上一轮: 我为你生成了一张喜马拉雅旅行照片。
本轮: 再生成3张类似的照片
输出:
<analysis>
  <thinking>用户基于上一轮产物，要求生成类似的更多照片</thinking>
  <requirement_type>新增同类产物</requirement_type>
  <scene_type>vibe coding</scene_type>
</analysis>"""

VALID_REQ_TYPES = [
    "纠错/修复问题", "新增Feature", "约束增强", "新增同类产物",
    "产物转化", "Follow up questions", "独立问题", "首轮对话",
]

VALID_SCENE_TYPES = ["vibe coding", "ppt", "excel表格", "docs文档", "其他"]


def build_prompt(prev_response, current_query, current_files, round_num):
    return f"""你是一个对话需求分析专家。

【需求类型】
1. 纠错/修复问题：用户指出上一轮产物/回复的问题，要求修复。
2. 新增Feature：要求增加新的功能模块、页面、系统等新内容。
3. 约束增强：对已有或即将生成的产物追加约束条件。
4. 新增同类产物：基于上一轮产物，要求生成类似的另一个产物。
5. 产物转化：跨模态或格式转换产物。
6. Follow up questions：追问、澄清、解释，不要求改动上一轮产物。
7. 独立问题：重新开启一个与前轮无关的新任务。
8. 首轮对话：第一轮。

【场景类型】
- vibe coding：网站、网页、图片生成、代码开发
- ppt：幻灯片、演示文稿
- excel表格：表格、数据、CSV
- docs文档：Word、文档
- 其他：不属于以上类别

{FEW_SHOT}

【当前任务】第 {round_num} 轮

【上一轮模型回复】：
{prev_response[:600] if prev_response else "（无）"}

【本轮用户输入】：
{current_query}

【本轮上传文件】：{', '.join(current_files) if current_files else '无'}

按以下 XML 格式输出（只输出 XML）：
<analysis>
  <thinking>简要分析</thinking>
  <requirement_type>标签</requirement_type>
  <scene_type>标签</scene_type>
</analysis>

输出："""


def parse_xml_result(xml_text):
    """解析 LLM 返回的 XML 分类结果"""
    result = {"requirement_type": "无法判断", "scene_type": "其他"}

    # XML 标签提取
    for tag, key, valid in [
        ("requirement_type", "requirement_type", VALID_REQ_TYPES),
        ("scene_type", "scene_type", VALID_SCENE_TYPES),
    ]:
        matches = re.findall(rf"<{tag}>(.*?)</{tag}>", xml_text, re.DOTALL)
        if matches:
            raw = matches[-1].strip()
            for v in valid:
                if v in raw:
                    result[key] = v
                    break

    return result


# ---------------------------------------------------------------------------
# 标注主流程
# ---------------------------------------------------------------------------

def annotate_chat(chat_id, full=False):
    """完整标注流程: 提取数据 → LLM 分类 → 返回标注结果"""
    rounds = extract_chat_data(chat_id)
    if not rounds:
        print("️  未获取到对话数据", file=sys.stderr)
        return []

    annotations = []
    for i, r in enumerate(rounds):
        print(f"[Step 2] 分析第 {r['round']} 轮...", file=sys.stderr)

        if r["round"] == 1:
            req_type, scene_type = "首轮对话", "其他"
            xml_raw = "<first_round/>"
        else:
            prev_resp = rounds[i - 1]["response"] if i > 0 else ""
            prompt = build_prompt(prev_resp, r["query"], r["files"], r["round"])
            xml_raw = llm_classify(prompt)
            parsed = parse_xml_result(xml_raw)
            req_type = parsed["requirement_type"]
            scene_type = parsed["scene_type"]

        vote = r["vote"]
        vote_display = "点赞" if vote == "VOTE_UP" else ("点踩" if vote == "VOTE_DOWN" else "无")
        resp_display = r["response"] if full else (
            r["response"][:500] + "..." if len(r["response"]) > 500 else r["response"]
        )

        annotations.append(
            {
                "chat_id": chat_id,
                "segment_id": r["segment_id"],
                "query": r["query"],
                "文件名": ", ".join(r["files"]) if r["files"] else "-",
                "轮次": r["round"],
                "模型resp": resp_display,
                "是否点赞/点踩": vote_display,
                "用户是否取消": "是" if r["is_cancelled"] else "否",
                "需求标签": req_type,
                "场景标签": scene_type,
                "_xml_raw": xml_raw,
            }
        )
        print(f"   需求={req_type}, 场景={scene_type}", file=sys.stderr)

    return annotations


# ---------------------------------------------------------------------------
# 保存结果
# ---------------------------------------------------------------------------

def save_results(chat_id, annotations, output_dir, debug=False):
    """保存标注结果到目录"""
    out = Path(output_dir) / chat_id
    out.mkdir(parents=True, exist_ok=True)

    # CSV（去掉 _ 开头的内部字段）
    csv_rows = [{k: v for k, v in a.items() if not k.startswith("_")} for a in annotations]
    if csv_rows:
        csv_path = out / "result.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
            w.writeheader()
            w.writerows(csv_rows)
        print(f"[保存] {csv_path}", file=sys.stderr)

    if debug:
        (out / "debug.json").write_text(
            json.dumps(annotations, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        with open(out / "raw_xml.txt", "w", encoding="utf-8") as f:
            for a in annotations:
                f.write(f"=== Round {a.get('轮次')} ===\n")
                f.write(f"Query: {a.get('query', '')[:100]}...\n")
                f.write(f"XML:\n{a.get('_xml_raw', 'N/A')}\n{'=' * 50}\n\n")
        print(f"[保存] {out}/debug.json, raw_xml.txt", file=sys.stderr)

    return str(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Chat 对话标注  自动提取轮次并用 LLM 打需求/场景标签"
    )
    parser.add_argument("--chat-id", required=True, help="Chat ID")
    parser.add_argument("--output", "-o", help="额外输出到指定 CSV")
    parser.add_argument("--json", "-j", help="额外输出到指定 JSON")
    parser.add_argument("--output-dir", default="annotator_output",
                        help="标注结果目录 (默认: ./annotator_output)")
    parser.add_argument("--debug", action="store_true", help="保存 debug 中间文件")
    parser.add_argument("--full", action="store_true", help="输出完整模型回复（不截断）")
    args = parser.parse_args()

    try:
        annotations = annotate_chat(args.chat_id, full=args.full)

        # 保存到默认目录
        save_results(args.chat_id, annotations, args.output_dir, debug=args.debug)

        # 额外 CSV
        if args.output:
            rows = [{k: v for k, v in a.items() if not k.startswith("_")} for a in annotations]
            if rows:
                with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.DictWriter(f, fieldnames=rows[0].keys())
                    w.writeheader()
                    w.writerows(rows)
                print(f"[完成] CSV → {args.output}", file=sys.stderr)

        # 额外 JSON
        if args.json:
            data = annotations if args.debug else [
                {k: v for k, v in a.items() if not k.startswith("_")} for a in annotations
            ]
            Path(args.json).write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"[完成] JSON → {args.json}", file=sys.stderr)

        # stdout
        out_data = [
            {k: v for k, v in a.items() if not k.startswith("_")} for a in annotations
        ]
        print(json.dumps(out_data, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f" 错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
