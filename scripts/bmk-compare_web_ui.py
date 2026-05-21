"""
Compare Web UI  新旧格式批量结果并排对比
完全复用 web_ui.py 的 CSS / HTML 结构
"""

import gradio as gr
import html as html_lib
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

from web_ui import CSS_STYLE as _BASE_CSS, GRADIO_CSS
sys.path.insert(0, str(Path(__file__).resolve().parent / "bmk"))
from compare import count_citations

# 追加 tooltip CSS（Gradio 6.x 不支持原生 title hover）
_TOOLTIP_CSS = """
<style>
    .cite-tip {
        position: relative;
        cursor: help;
    }
    .cite-tip:hover::after {
        content: attr(data-tooltip);
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        background: #1f2937;
        color: #fff;
        padding: 6px 10px;
        border-radius: 6px;
        font-size: 12px;
        white-space: pre-wrap;
        max-width: 400px;
        min-width: 150px;
        z-index: 999;
        pointer-events: none;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        line-height: 1.4;
    }
</style>
"""
CSS_STYLE = _BASE_CSS + _TOOLTIP_CSS


# ---------- BMK 预设 ----------

BMK_PRESETS = {
    "CN 300": {
        "dir_a": "bmk/default_bmk_cn_with_hook",
        "dir_b": "bmk/new_cite_cn",
        "label_a": "旧格式_with_hook",
        "label_b": "新格式_PUA",
        "judge": "judge/result/251021搜索业务重点BMK_for模型上线前评测_default_300_cn_表格.xlsx",
    },
    "EN 300": {
        "dir_a": "bmk/default_bmk_en_with_hook",
        "dir_b": "bmk/new_cite_en",
        "label_a": "旧格式_with_hook",
        "label_b": "新格式_PUA",
        "judge": "judge/result/251021搜索业务重点BMK_for模型上线前评测_default_300_en_表格.xlsx",
    },
    "SimpleQA": {
        "dir_a": "bmk/simpleqa_with_hook",
        "dir_b": "bmk/new_cite_simpleqa",
        "label_a": "旧格式_with_hook",
        "label_b": "新格式_PUA",
        "judge": "judge/result/251021搜索业务重点BMK_for模型上线前评测_researcher_simpleqa_表格.xlsx",
    },
}


# ---------- 数据 ----------

def load_batch_dir(dir_path):
    result = {}
    p = Path(dir_path)
    if not p.exists():
        return result
    for f in p.glob("*.json"):
        try:
            result[int(f.stem)] = json.load(open(f, encoding="utf-8"))
        except (ValueError, json.JSONDecodeError):
            continue
    return result


def load_judge(xlsx_path, label_a, label_b):
    result = {}
    p = Path(xlsx_path)
    if not p.exists():
        return result
    df = pd.read_excel(p, engine="openpyxl")
    for _, row in df.iterrows():
        idx = row.get("index")
        if idx == "" or pd.isna(idx):
            continue
        try:
            idx = int(idx)
        except (ValueError, TypeError):
            continue
        result[idx] = {
            "a_score": row.get(f"{label_a}_score", ""),
            "a_reason": row.get(f"{label_a}_reason", ""),
            "b_score": row.get(f"{label_b}_score", ""),
            "b_reason": row.get(f"{label_b}_reason", ""),
        }
    return result


def extract_final_text(data):
    final = ""
    for e in data.get("output", []):
        if e.get("type") == "model_end" and e.get("finish_reason") == "stop":
            for c in e.get("message", {}).get("contents", []):
                if c.get("text"):
                    final = c["text"]
    return final


def extract_tokens(data):
    prompt = comp = total = 0
    for e in data.get("output", []):
        if e.get("type") == "model_end":
            u = e.get("usage") or {}
            prompt += u.get("prompt_tokens", 0)
            comp += u.get("completion_tokens", 0)
            total += u.get("total_tokens", 0)
    return prompt, comp, total


def extract_search_count(data):
    n = 0
    for e in data.get("output", []):
        if e.get("type") == "model_end":
            for tc in e.get("message", {}).get("tool_calls", []):
                if tc.get("function", {}).get("name") == "web_search":
                    n += 1
    return n


def _parse_ref_line(line: str) -> tuple[str, str, str] | None:
    """解析单行 ref，返回 (id, url, title) 或 None。
    支持:
      # id: search:0#127(url) title (Authority:X)(date)
      # [^N^](url) title (date)
    """
    # 找 (Authority: 的位置，从那里往前截
    auth_pos = line.find(" (Authority:")
    date_pat = re.search(r' \(\d{4}-\d{2}-\d{2}\)\s*$', line)
    unknown_date = line.rstrip().endswith("(Unknown Date)")

    # 新格式
    m = re.match(r'^# id: (search:\d+#\d+)\(', line)
    if m:
        ref_id = m.group(1)
        rest = line[m.end():]  # 从 URL 开始
        # 找 ") " 后面紧跟 (Authority: 的位置来分割 URL 和 title
        if auth_pos > 0:
            # 从 (Authority: 往前找最近的 ") "
            before_auth = line[:auth_pos]
            # URL 从 ref_id( 之后开始到某个 ") " 结束
            url_start = m.end()
            # title 在 ") " 和 " (Authority:" 之间
            # 找最后一个 ") " 在 auth_pos 之前
            close_paren = before_auth.rfind(") ")
            if close_paren < url_start:
                close_paren = before_auth.rfind(")")
            url = line[url_start:close_paren]
            title = line[close_paren+1:auth_pos].strip()
            return ref_id, url, title
        return None

    # 旧格式
    m = re.match(r'^# \[\^(\d+)\^\]\(', line)
    if m:
        ref_id = m.group(1)
        rest = line[m.end():]  # noqa: F841
        # 找 date 或 Unknown Date 位置
        end_pos = None
        if date_pat:
            end_pos = date_pat.start()
        elif unknown_date:
            end_pos = line.rfind("(Unknown Date)")
        if end_pos and end_pos > m.end():
            before_date = line[m.end():end_pos]
            close_paren = before_date.rfind(") ")
            if close_paren < 0:
                close_paren = before_date.rfind(")")
            url = before_date[:close_paren]
            title = before_date[close_paren+1:].strip()
            return ref_id, url, title
        return None

    return None


def extract_ref_sources(data):
    """提取引用来源，支持新格式 (search:N#M) 和旧格式 ([^N^])"""
    sources = {}
    for e in data.get("output", []):
        if e.get("type") == "tool_end" and "web_search" in e.get("tool_call_id", ""):
            for part in e.get("result_parts", []):
                text = part.get("text", "") if isinstance(part, dict) else str(part)
                for line in text.split("\n"):
                    parsed = _parse_ref_line(line)
                    if parsed:
                        ref_id, url, title = parsed
                        sources[ref_id] = {"title": title or "(no title)", "url": url}
    return sources


# ---------- 引用高亮 ----------

_PUA_S = "\uE3A0"
_PUA_E = "\uE3A8"
_PUA_D = "[\uE3A1\uE3A2\uE3A3]"
_RE_PUA = re.compile(f"({re.escape(_PUA_S)})(cite|file|image|article)(.*?)({re.escape(_PUA_E)})")


def highlight(text, sources):
    """高亮引用并渲染 markdown。两种格式不同颜色，hover 显示来源，无效引用红色。"""
    # 1) 替换 PUA 引用为占位符（防止 markdown 渲染破坏）
    placeholders = {}
    counter = [0]

    def repl_pua(m):
        btype = m.group(2)
        refs = [r.strip() for r in re.split(_PUA_D, m.group(3)) if r.strip()]
        tips = []
        all_valid = True
        for rid in refs:
            s = sources.get(rid)
            if s:
                tips.append(f"{s['title']}\n{s['url']}")
            else:
                tips.append(f"{rid} (not found)")
                all_valid = False
        tip = html_lib.escape("\n---\n".join(tips))
        if not all_valid:
            bg, co = "#fee2e2", "#991b1b"  # 红色：无效引用
        elif btype == "article":
            bg, co = "#fef3c7", "#92400e"  # 黄色：article card
        else:
            bg, co = "#dbeafe", "#1e40af"  # 蓝色：cite/file/image
        lab = f"[{btype}:{len(refs)}]" if len(refs) > 1 else f"[{btype}]"
        key = f"%%PH{counter[0]}%%"
        counter[0] += 1
        placeholders[key] = f'<span class="cite-tip" data-tooltip="{tip}" style="background:{bg};color:{co};padding:1px 4px;border-radius:3px;font-size:12px;">{lab}</span>'
        return key

    text = _RE_PUA.sub(repl_pua, text)

    # 2) 替换旧格式 [^N^] 为占位符
    def repl_legacy(m):
        num = m.group(1)
        s = sources.get(num)
        if s:
            tip = html_lib.escape(f"{s['title']}\n{s['url']}")
            bg, co = "#dcfce7", "#166534"  # 绿色：旧格式
        else:
            tip = html_lib.escape(f"[^{num}^] (not found)")
            bg, co = "#fee2e2", "#991b1b"  # 红色：无效
        key = f"%%PH{counter[0]}%%"
        counter[0] += 1
        placeholders[key] = f'<span class="cite-tip" data-tooltip="{tip}" style="background:{bg};color:{co};padding:1px 4px;border-radius:3px;font-size:12px;">[^{num}^]</span>'
        return key

    text = re.sub(r'\[\^(\d+)\^\]', repl_legacy, text)

    # 3) 渲染 markdown
    import markdown
    html_out = markdown.markdown(text, extensions=['fenced_code', 'tables'])

    # 4) 还原占位符
    for key, val in placeholders.items():
        html_out = html_out.replace(key, val)

    return html_out


# ---------- 渲染（和 web_ui.py do_replay 完全一致的 HTML 结构） ----------

def render_side(data, j_score, j_reason, sources):
    """渲染一侧，输出 step-item HTML（和 web_ui render_step_item 结构一致）"""
    if data is None:
        return '<div class="step-item"><div class="step-label">N/A</div><div style="color:#9ca3af;">Missing</div></div>'
    if data.get("error"):
        return f'<div class="step-item"><div class="step-label">Error</div><div style="color:#dc2626;font-size:13px;">{html_lib.escape(str(data["error"]))}</div></div>'

    text = extract_final_text(data)
    p, c, t = extract_tokens(data)
    cites = count_citations(text)
    inl = cites["legacy_refs"] + cites["pua_refs"]
    art = cites["article_refs"]
    srch = extract_search_count(data)

    # judge badge
    jhtml = ""
    if j_score is not None and j_score != "":
        s = str(j_score)
        if s == "SKIP":
            jc = "#9ca3af"
        elif s == "1":
            jc = "#16a34a"
        elif s == "0.5":
            jc = "#ca8a04"
        else:
            jc = "#dc2626"
        jtip = html_lib.escape(str(j_reason)) if j_reason else ""
        jhtml = f' · <span class="cite-tip" data-tooltip="{jtip}" style="color:{jc};font-weight:600;">judge:{s}</span>'

    # 指标行（step-label 风格）
    meta = f'tokens:{t}({p}+{c}) · cite:inline:{inl} · cite:card:{art} · search:{srch}{jhtml}'
    content = highlight(text, sources) if text else '<span style="color:#9ca3af">(empty)</span>'

    return f'''
    <div class="step-item">
        <div class="step-label">{meta}</div>
        <div class="text" style="font-size:13px;">{content}</div>
    </div>
    '''


def render_sample(idx, data_a, data_b, la, lb, jd):
    query = ""
    if data_a:
        query = data_a.get("query", "")
    elif data_b:
        query = data_b.get("query", "")

    j = jd or {}
    src_a = extract_ref_sources(data_a) if data_a else {}
    src_b = extract_ref_sources(data_b) if data_b else {}
    left = render_side(data_a, j.get("a_score"), j.get("a_reason", ""), src_a)
    right = render_side(data_b, j.get("b_score"), j.get("b_reason", ""), src_b)

    # 和 web_ui do_replay 的 HTML 完全一致
    return f'''
    {CSS_STYLE}
    <div class="conversation">
        <div class="figure">#{idx} &mdash; {html_lib.escape(query[:200])}</div>
        <div class="branch-comparison">
            <div class="branch-side">
                <div class="branch-side-title">{html_lib.escape(la)}</div>
                {left}
            </div>
            <div class="branch-side">
                <div class="branch-side-title">{html_lib.escape(lb)}</div>
                {right}
            </div>
        </div>
    </div>
    '''


# ---------- 状态 ----------

_state = {"a": {}, "b": {}, "indices": [], "la": "", "lb": "", "judge": {}}


def _load_preset(name):
    preset = BMK_PRESETS.get(name)
    if not preset:
        return
    a = load_batch_dir(preset["dir_a"])
    b = load_batch_dir(preset["dir_b"])
    la, lb = preset["label_a"], preset["label_b"]
    judge = load_judge(preset["judge"], la, lb)
    indices = sorted(set(a.keys()) | set(b.keys()))
    _state.update({"a": a, "b": b, "indices": indices, "la": la, "lb": lb, "judge": judge})


def do_switch_bmk(name):
    _load_preset(name)
    if not _state["indices"]:
        return "Empty", gr.update(choices=[], value=None), ""
    indices = _state["indices"]
    choices = [str(i) for i in indices]
    jinfo = f", {len(_state['judge'])} judge" if _state["judge"] else ""
    status = f"{name}: {len(_state['a'])}+{len(_state['b'])} samples{jinfo}"
    idx = indices[0]
    html = render_sample(idx, _state["a"].get(idx), _state["b"].get(idx), _state["la"], _state["lb"], _state["judge"].get(idx))
    return status, gr.update(choices=choices, value=choices[0]), html


def do_view(idx_str):
    if not idx_str or not _state["indices"]:
        return ""
    idx = int(idx_str)
    return render_sample(idx, _state["a"].get(idx), _state["b"].get(idx), _state["la"], _state["lb"], _state["judge"].get(idx))


def do_nav(idx_str, direction):
    if not _state["indices"]:
        return gr.update(), ""
    indices = _state["indices"]
    try:
        pos = indices.index(int(idx_str))
    except (ValueError, IndexError):
        pos = 0
    pos = max(0, min(len(indices) - 1, pos + direction))
    idx = indices[pos]
    return gr.update(value=str(idx)), do_view(str(idx))


# ---------- UI ----------

def create_ui():
    # 启动时预加载 CN 300
    _load_preset("CN 300")
    init_choices = [str(i) for i in _state["indices"]]
    init_html = do_view(init_choices[0]) if init_choices else ""

    with gr.Blocks(title="Compare Web UI", theme=gr.themes.Base(), css=GRADIO_CSS) as app:
        with gr.Row(elem_classes="input-row"):
            bmk_dd = gr.Dropdown(
                label="BMK", choices=list(BMK_PRESETS.keys()),
                value="CN 300", scale=3
            )

        status_output = gr.Textbox(label="Status", interactive=False, lines=1,
                                   value=f"CN 300: {len(_state['a'])}+{len(_state['b'])} samples, {len(_state['judge'])} judge")

        with gr.Row(elem_classes="input-row"):
            sample_dd = gr.Dropdown(label="Sample", choices=init_choices,
                                    value=init_choices[0] if init_choices else None, scale=3)
            prev_btn = gr.Button("Prev", scale=1, elem_classes="action-btn")
            next_btn = gr.Button("Next", scale=1, elem_classes="action-btn")

        main_output = gr.HTML(value=init_html)

        bmk_dd.change(fn=do_switch_bmk, inputs=[bmk_dd], outputs=[status_output, sample_dd, main_output])
        sample_dd.change(fn=do_view, inputs=[sample_dd], outputs=[main_output])
        prev_btn.click(fn=lambda s: do_nav(s, -1), inputs=[sample_dd], outputs=[sample_dd, main_output])
        next_btn.click(fn=lambda s: do_nav(s, 1), inputs=[sample_dd], outputs=[sample_dd, main_output])

    return app


if __name__ == "__main__":
    os.system("lsof -i :7863 | grep LISTEN | awk '{print $2}' | xargs -r kill -9 2>/dev/null")
    app = create_ui()
    app.launch(server_name="0.0.0.0", server_port=7863, share=False, inbrowser=False)
