# 问题排查指南

## 1. 按产出物类型快速诊断

### 诊断流程图

```
用户反馈问题
    │
    ├──→ 包含 "PPT/演示/幻灯片" ─────────────────────────┐
    │                                                   ▼
    ├──→ 包含 "网页/网站/链接/部署" ──→ 按 Web 问题排查  │
    │                                                   │
    ├──→ 包含 "Word/Excel/PDF/文件" ──→ 按文档问题排查  │
    │                                                   │
    └──→ 不明确 ──→ 先获取 trajectory 确定产出物类型   │
                                                      ▼
                                            按 PPT 问题排查
```

---

## 2. PPT 问题专项排查

### 核心原则
> **slides_generator 不在 `/mnt/Internal_Toolomputer/output/` 生成文件！**

### 用户说"PPT 没生成"

**排查步骤：**

```python
# 1. 检查 trajectory
trajectory = get_compact_trajectory(chat_id="xxx")

# 2. 搜索 slides_generator 调用
has_ppt_tool = "mshtools-slides_generator" in trajectory

if has_ppt_tool:
    # PPT 已生成！问题可能是：
    # a) 用户没找到下载入口
    # b) 前端展示问题
    # c) PPT 内容不符合预期
    conclusion = "PPT 已生成，需进一步确认具体问题类型"
else:
    # 真未生成
    # 检查是否误解需求
    conclusion = "未调用 slides_generator，检查意图理解"
```

**常见误判纠正：**

|  错误结论 |  正确结论 |
|-----------|-----------|
| "PPT 文件未在 output 目录生成" | "PPT 通过 slides_generator 生成，不在 output 目录存放" |
| "未找到 PPT 产出物" | "slides_generator 已调用，PPT 已生成" |
| "PPT 生成失败" | "slides_generator 调用成功，需确认前端展示" |

### 检查 slides_generator 参数

```python
# 提取 slides_generator 调用参数
import re, json

pattern = r'\[tool_call\] Tool Name: mshtools-slides_generator.*?Tool Args: ({.*?})'
match = re.search(pattern, trajectory, re.DOTALL)

if match:
    args = json.loads(match.group(1))
    html_content = args.get('content', '')
    
    # 检查内容完整性
    checks = {
        "内容非空": len(html_content) > 100,
        "包含 HTML 标签": '<html' in html_content.lower() or '<body' in html_content.lower(),
        "包含幻灯片标记": 'slide' in html_content.lower() or 'reveal' in html_content.lower(),
        "内容未截断": not html_content.endswith('...'),
    }
```

### PPT 常见问题分类

| 问题现象 | 根因 | 检查点 |
|---------|------|--------|
| 用户说"没生成" | 用户未找到下载入口 | slides_generator 是否调用 |
| 用户说"下载不了" | 前端/浏览器问题 | 调用成功，内容完整 |
| 用户说"内容不对" | 内容生成问题 | HTML 内容是否符合需求 |
| 用户说"格式错乱" | HTML/CSS 问题 | slides_generator 的样式参数 |

---

## 3. Web 网页问题专项排查

### 用户说"网页打不开"

**排查步骤（使用 browser 工具）：**

```python
# 1. 从 trajectory 获取部署的 URL
import re

url_pattern = r'(https?://[\w.-]+\.[a-zA-Z]{2,}[^\s\]"]*)'
urls = re.findall(url_pattern, trajectory)

url = urls[0]  # 获取第一个链接

# 2. 使用 browser 工具检查
browser_navigate(url=url)
browser_wait_for(time=3)  # 等待页面加载
snapshot = browser_snapshot()
console_errors = browser_console_messages(level="error")

# 3. 分析结果
page_content = snapshot.get("content", "")

if len(page_content) < 100:
    # 页面几乎空白
    issue = "页面内容极少，可能是空白页"
    if console_errors:
        issue += "（有 JS 错误）"
elif "404" in page_content or "Not Found" in page_content:
    issue = "页面返回 404 错误"
elif console_errors:
    issue = f"页面有 {len(console_errors)} 个 JS 错误"
else:
    issue = "页面正常加载，可能是用户端问题"
```

### 检查部署完整性

```python
# 获取所有文件
files = get_Internal_Tool_files(chat_id="xxx")

# 检查是否包含必要资源
html_files = [f for f in files if f['extension'] == '.html']
css_files = [f for f in files if f['extension'] == '.css']
js_files = [f for f in files if f['extension'] == '.js']

# 问题诊断
if not html_files:
    issue = "缺少 HTML 文件"
elif not css_files and "样式" in user_feedback:
    issue = "可能缺少 CSS 文件，导致样式错乱"
elif not js_files and "交互" in user_feedback:
    issue = "可能缺少 JS 文件，导致交互失效"
```

### Web 常见问题分类

| 问题现象 | 可能原因 | 检查方法 |
|---------|---------|---------|
| 404 错误 | 部署路径错误、文件未部署 | browser_navigate 检查 |
| 页面空白 | JS 错误、资源未加载、HTML 为空 | browser_console_messages 检查 JS 错误 |
| 页面错乱 | CSS 未加载、路径错误 | browser_snapshot 检查渲染结果 |
| 交互失效 | JS 错误、资源缺失 | browser_console_messages 检查错误 |
| 图片不显示 | 图片路径为绝对路径或图片未部署 | 检查图片资源是否在部署目录 |
| 响应慢 | 资源过大、网络问题 | browser 加载时间观察 |

---

## 4. 文档问题专项排查

### 文件打不开/损坏

**首要检查：是否用 write_file 直接写了二进制文件**

```python
# 检查文件内容
result = check_output_file(chat_id="xxx", full_path="/mnt/Internal_Toolomputer/output/file.xlsx")

if result["success"]:
    content = result["content"]
    
    # 如果是二进制文件被 write_file 直接写入，内容会类似：
    if content.startswith('PK') or content.startswith('%PDF'):
        if "file corrupted" in user_feedback.lower():
            issue = "用 write_file 直接写了二进制文件，导致文件损坏"
            solution = "应使用 pandas/openpyxl/reportlab 等库生成"
```

### 各类文档检查要点

#### Word (.docx)

```python
# 正确生成方式：
# 1. write_file 生成 markdown
# 2. 前端自动转换为 Word

# 错误方式（会导致文件损坏）：
# write_file 直接写 .docx 二进制内容

# 检查
files = get_Internal_Tool_files(chat_id="xxx")
word_files = [f for f in files if f['extension'] == '.docx']

if word_files:
    # 检查 trajectory 中生成方式
    if "to_markdown" in trajectory or ".md" in trajectory:
        conclusion = "Word 通过 markdown 转换生成，方式正确"
    else:
        conclusion = "疑似直接用 write_file 写 .docx，可能损坏"
```

#### Excel (.xlsx)

```python
# 正确生成方式：
# ipython + pandas: df.to_excel('/mnt/Internal_Toolomputer/output/file.xlsx')
# 或 openpyxl: wb.save('/mnt/Internal_Toolomputer/output/file.xlsx')

# 错误方式（会导致文件损坏）：
# write_file 直接写 .xlsx 内容

# 检查 trajectory
correct_pattern = "to_excel" in trajectory or "openpyxl" in trajectory or "Workbook" in trajectory
wrong_pattern = "write_file" in trajectory and ".xlsx" in trajectory

if wrong_pattern and not correct_pattern:
    issue = "用 write_file 直接写 Excel 文件，导致文件损坏"
```

#### PDF (.pdf)

```python
# 正确生成方式：
# ipython + reportlab: canvas.save()
# 或 fpdf: pdf.output()

# 错误方式（会导致文件损坏）：
# write_file 直接写 .pdf 内容

# 检查
correct_pattern = "reportlab" in trajectory or "fpdf" in trajectory or "canvas.save" in trajectory
wrong_pattern = "write_file" in trajectory and ".pdf" in trajectory

if wrong_pattern and not correct_pattern:
    issue = "用 write_file 直接写 PDF 文件，导致文件损坏"
```

#### CSV (.csv)

```python
# CSV 可以直接用 write_file 写入文本内容
# 也可以用 pandas: df.to_csv()

# 两种方式都正确
correct = ("write_file" in trajectory and ".csv" in trajectory) or "to_csv" in trajectory
```

### 文档问题快速分类

| 问题现象 | 可能原因 | 快速检查 |
|---------|---------|---------|
| 文件打不开 | 用 write_file 写了二进制文件 | 检查生成方式 |
| 内容为空 | write_file 写入空内容 | check_output_file 检查 |
| 格式错乱 | 编码问题、分隔符错误 | 检查文件头 |
| 数据缺失 | 写入不完整、截断 | 检查文件大小和行数 |
| 乱码 | 编码问题（UTF-8 BOM） | 检查编码格式 |

---

## 5. 严重程度评估指南

| 严重程度 | 定义 | PPT 示例 | Web 示例 | 文档示例 |
|---------|------|---------|---------|---------|
| **critical** | 完全无法使用，核心功能失败 | 付费后 slides_generator 未调用，真无 PPT | 部署后网站完全无法访问 | 文件损坏无法打开 |
| **major** | 主要功能受影响，有明显缺陷 | PPT 内容严重偏离需求 | 页面显示错乱、功能失效 | 内容缺失/错误、格式严重错乱 |
| **minor** | 轻微影响，可用但有瑕疵 | PPT 排版不美观 | 样式微调、加载稍慢 | 格式微调、轻微排版问题 |

---

## 6. need_human 场景清单

在以下情况标记 `need_human`：

### PPT 相关
- slides_generator 调用成功但用户仍说"没生成"，无法确定是前端问题还是用户操作问题
- PPT 内容业务逻辑正确性需要人工判断

### Web 相关
- browser 工具检查正常但用户坚持说打不开，可能是特定浏览器/网络环境问题
- 网站功能逻辑正确性需要人工验证

### 文档相关
- 文件内容业务数据正确性需要人工核对
- 格式转换后的样式问题（Word/PDF 转换效果）

### 通用场景
- 涉及模型内部决策逻辑无法解释
- 多问题交织难以分离根因
- 首次遇到的边界情况

---

## 7. 证据提取模板

### PPT 问题证据

```yaml
# 好的证据
evidence: >
  [tool_call] Tool Name: mshtools-slides_generator, Tool Args:
  {"content": "<!DOCTYPE html><html><head>...</head><body>...5000 chars..."}
  
  分析：slides_generator 在 turn_2 step_1 被调用，HTML 内容完整（5000+ 字符），
  包含完整的 PPT 结构，PPT 已成功生成。
```

### Web 问题证据

```yaml
# 好的证据
evidence: >
  [tool_call] Tool Name: mshtools-deploy_website, Tool Args:
  {"path": "/mnt/Internal_Toolomputer/output/my-site"}
  
  browser 工具检查结果：
  - URL: https://deployed-site-xxx.com
  - browser_navigate: 成功访问
  - browser_snapshot: 页面显示 "404 Not Found"
  - browser_console_messages: 无 JS 错误
  
  分析：deploy_website 已调用，但部署后的链接返回 404 页面，部署路径可能错误。
```

### 文档问题证据

```yaml
# 好的证据
evidence: >
  [tool_call] Tool Name: mshtools-write_file, Tool Args:
  {"file_path": "/mnt/Internal_Toolomputer/output/report.xlsx", 
   "content": "PK\x03\x04...（二进制内容）"}
  
  check_output_file 结果：
  - 文件大小：5KB
  - 尝试打开：文件损坏或格式不正确
  
  分析：使用 write_file 直接写入了 .xlsx 二进制内容，导致 Excel 文件损坏。
  应使用 pandas 或 openpyxl 生成。
```

---

## 8. 常见用户反馈映射

| 用户原话 | 产出物类型 | 可能的问题类型 | 检查重点 |
|---------|-----------|--------------|---------|
| "PPT 没生成" | PPT | 需确认是展示问题还是真未生成 | slides_generator 调用 |
| "下载不了" | PPT/文档 | 前端问题或文件损坏 | 调用成功性、文件完整性 |
| "网页打不开/空白" | Web | deploy/JS 错误/资源问题 | browser_navigate + console |
| "网页显示错乱" | Web | CSS/资源路径问题 | browser_snapshot |
| "文件打不开" | 文档 | 文件损坏、格式错误 | 生成方式 |
| "Word 是空的" | Word | 写入内容为空 | 内容检查 |
| "Excel 格式不对" | Excel | 生成方式错误或数据问题 | 生成库使用 |
| "PDF 损坏" | PDF | write_file 直接写二进制 | 生成方式 |
| "内容不是我想要的" | 通用 | 意图理解偏差 | 第一轮理解 |
| "少了第 X 页" | PPT/文档 | 内容缺失、截断 | 内容完整性 |

