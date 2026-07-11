from __future__ import annotations


def build_web_search_query_messages(
    title: str,
    abstract: str,
    snippets: list[str],
    question: str,
    search_mode: str = "auto",
    missing_information: list[str] | None = None,
    previous_queries: list[str] | None = None,
) -> list[dict[str, str]]:
    local_snippets = "\n".join(snippets[:2])
    missing_context = "、".join(missing_information or []) or "未提供"
    previous_context = "\n".join(f"- {query}" for query in previous_queries or []) or "无"
    mode_guidance = (
        "当前是总是搜索模式（默认参考模式）：必须生成能补充背景、后续、对比或权威说明的 query，"
        "即使本地论文片段可能已经足够也一样。"
        if search_mode == "always"
        else "当前是自动搜索模式：优先围绕当前来源缺口生成 query，用于补齐回答所需的外部证据。"
    )
    return [
        {
            "role": "system",
            "content": (
                "你是 web search query planner。根据论文信息和用户问题生成适合搜索引擎的英文检索式。"
                "只输出 JSON，不要输出 Markdown。"
                f"{mode_guidance}"
                "如果用户问题需要论文外部、最新、后续、对比或代码信息，should_search 为 true。"
                "search_queries 必须是 1 到 3 条英文 query，避免只重复论文标题。"
                "如果已经有搜索记录，新的 query 必须针对当前缺口换一个角度，不能重复已有 query。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"论文标题：{title}\n"
                f"摘要：{abstract or '未提供'}\n"
                f"本地片段：\n{local_snippets or '无'}\n"
                f"用户问题：{question}\n\n"
                f"当前缺口：{missing_context}\n"
                f"已执行的 query：\n{previous_context}\n\n"
                "输出 JSON：{\"should_search\": true, \"search_queries\": [\"...\"]}"
            ),
        },
    ]
