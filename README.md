# Paper Blog Agent

一个本地优先的论文调研与解读工具。输入一篇 arXiv 论文、PDF、Markdown 或 DOCX，应用会解析材料、生成带来源约束的调研页面，并将论文内容存入本地记忆；之后可围绕当前论文继续追问，在需要时用联网检索补充证据。

项目不是通用联网聊天机器人。它的核心原则是：先从论文片段回答，重要结论必须能回到论文或联网来源；证据不足时明确说明缺口，而不是补造事实。

## 能做什么

- 导入 arXiv ID/URL、本地 `.pdf`、`.md`、`.markdown`、`.docx`。
- 自动识别来源、提取文本、切分片段，并将论文与全文检索索引保存在本地 SQLite。
- 生成可编辑的 Markdown、展示用 HTML、结构化知识文件和校验报告。
- 提供三种论文解读模式：科普、学习、技术。
- 围绕当前论文进行流式追问，并展示 Agent 正在执行的检索、判断、核对与生成步骤。
- 在来源不够时可由 LLM 规划检索词，再经 Tavily 补充网页证据。
- 从兼容 OpenAI 的供应商 `/models` 接口读取模型列表并持久化。
- 保存用户偏好、模型配置、搜索配置和历史论文记录。

## 工作方式

### 论文整理

```text
输入材料
  -> 解析与标准化
  -> 切分论文片段
  -> 提取关键信息
  -> 按输出模式生成结构化解读
  -> 校验来源支持情况
  -> 导出 Markdown / HTML / knowledge.json
  -> 写入 SQLite + FTS5 本地记忆
```

没有配置 LLM 时，流程仍会保留本地解析、片段和基础结果；配置兼容 OpenAI 的模型后，会使用模型生成结构化解读并执行更完整的证据校验。

### 论文追问与联网补充

追问先从当前论文的 `knowledge.json` 和 SQLite FTS5 索引中取回相关片段。联网模式有三种：

| 模式 | 行为 |
| --- | --- |
| `off` / 离线 | 只根据论文片段回答，不进行来源充足度判断和联网。 |
| `auto` / 自动补充 | LLM 判断论文证据是否足够；不足时生成 query、搜索、复核，直到证据足够或达到轮次上限。 |
| `always` / 总是联网 | 每次追问都先检索外部来源，再由 LLM 判断合并后的证据是否足够。 |

搜索结果不是自动事实。它们会作为“联网来源”与论文片段一起交给模型判断和回答，界面会保留来源编号与网页链接。

## 三种解读模式

三档模式共享“只根据来源、输出 JSON、标记证据缺口”等公共约束，但分别维护独立的 prompt 模块，因此不只是改变语气。

| 模式 | 适合谁 | 重点 |
| --- | --- | --- |
| 科普 | 初次接触领域的读者 | 动机、直觉、生活化类比、术语解释、少公式。 |
| 学习 | 正在建立知识体系的读者 | 问题、概念、方法、例子、易错点和后续复习方向。 |
| 技术 | 需要评估或实现方法的读者 | 模型结构、数据流、算法步骤、复杂度、实验、局限与复现线索。 |

模式 prompt 位于 `paper_blog_agent/prompts/blog_modes/`，公共生成契约位于 `paper_blog_agent/prompts/blog_generation.py`。

## 快速开始

需要 Python 3.10 或更高版本。项目使用 `uv` 管理依赖。

```bash
uv sync
uv run paper-blog-agent-web --port 8767
```

浏览器打开 [http://127.0.0.1:8767](http://127.0.0.1:8767)。如需换端口，修改 `--port` 的值：

```bash
uv run paper-blog-agent-web --port 8765
```

也可以直接使用模块入口：

```bash
uv run python -m paper_blog_agent.web --port 8767
```

### 命令行生成

```bash
uv run paper-blog-agent path/to/paper.md
uv run paper-blog-agent 1706.03762 --blog-type technical
uv run paper-blog-agent path/to/paper.pdf --blog-type popular
```

生成结果默认写到 `outputs/<paper_id>/`。

## 配置模型与联网搜索

在 Web 界面的“设置”中完成配置：

1. 选择供应商，填写 Base URL、API Key 和模型名；或点击“获取模型列表”从供应商 `/models` 接口加载。
2. 设置输出语言、目标读者、语气、深度、公式处理和关注重点。
3. 在“联网补充”中填写 Tavily Search API Key，并选择 `off`、`auto` 或 `always`。

当前内置常见 OpenAI-compatible 供应商预设，包括 DeepSeek、OpenAI、OpenRouter、Moonshot、DashScope、Gemini、Groq 和 Custom。模型及搜索配置保存在 `memory/llm_config.json`，用户偏好保存在 `memory/user_profile.md`。

注意：这是本地单用户工具，API Key 会以明文写入本地配置文件。不要把 `memory/llm_config.json` 提交到公共仓库，也不要在不可信设备上保存真实密钥。

## 本地数据

```text
memory/
  papers.sqlite          # 论文、chunk 与 FTS5 检索索引
  llm_config.json        # 模型、模型列表、搜索配置和 API Key
  user_profile.md        # 输出偏好
uploads/                 # Web 上传的源文件
outputs/<paper_id>/
  blog.md                # 可编辑调研稿
  blog.html              # 可直接打开的调研页面
  knowledge.json         # 后续问答使用的论文知识源
  verification_report.json
```

删除历史项目时，应用会同步删除 SQLite 中的论文、生成记录、索引和对应输出目录。

## 项目结构

```text
paper_blog_agent/
  agents/chat_agent.py      # 论文问答、证据判断和联网检索 loop
  ingestion/                # arXiv、PDF、Markdown、DOCX 解析
  memory/                   # SQLite FTS5 与用户偏好
  prompts/                  # 生成、问答、搜索、校验提示词
    blog_modes/             # 科普 / 学习 / 技术独立模式模块
  workflow.py               # 论文导入与生成工作流
  web.py                    # HTTP、SSE、静态资源边界
  web_api.py                # Web 业务 API
web/                        # Vue CDN 前端与样式
tests/                      # 单元与架构边界测试
docs/architecture.md        # 详细架构、数据流和接口说明
```

更多模块职责、SSE 事件流与架构图请查看 [docs/architecture.md](docs/architecture.md)。

## 开发与验证

```bash
uv run python -m unittest discover -s tests -v
node --check web/app.js
node --check web/search_mode.js
```

测试覆盖论文导入、FTS5 检索、生成工作流、LLM 配置、联网证据循环、SSE 事件、前端标记和模块边界。

## 当前边界

- Web Search 当前实现的是 Tavily provider；代码已保留 provider adapter 边界，其他供应商尚未接入。
- LLM 接口要求兼容 OpenAI Chat Completions 形式；不同供应商的字段或模型能力差异需要自行核对。
- 自动与总是联网模式会尽量补齐证据，但不能代替对原始论文和外部来源的人工判断。
