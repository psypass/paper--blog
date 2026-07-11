from __future__ import annotations


def build_context_sufficiency_messages(
    title: str,
    question: str,
    paper_snippets: list[str],
    web_snippets: list[str],
    search_mode: str = "auto",
) -> list[dict[str, str]]:
    paper_context = "\n\n".join(paper_snippets) or "无"
    web_context = "\n\n".join(web_snippets) or "无"
    mode_guidance = (
        "当前是总是搜索模式（始终联网作为参考）。首轮联网检索后才执行本次判断；联网来源是必经参考，"
        "不能仅因为出现联网来源就认为论文来源不足。应判断论文片段和联网片段合在一起是否足够回答问题。"
        if search_mode == "always"
        else "当前是自动搜索模式。请根据论文片段和已有联网片段决定是否需要联网补充；"
        "只有当前证据不能支撑严谨回答时，才判定为不足。"
    )
    return [
        {
            "role": "system",
            "content": (
                "你是论文问答 agent 的 evidence sufficiency judge。"
                "你的任务不是回答用户问题，而是判断当前来源是否足够支撑一个严谨回答。"
                "必须同时看论文片段、联网片段和用户问题。"
                f"{mode_guidance}"
                "如果问题询问最新进展、后续工作、外部对比、代码仓库、当前状态，而来源没有覆盖这些信息，"
                "context_sufficient 必须为 false。"
                "如果来源只覆盖背景论文但无法回答用户真正问的比较、时间或外部事实，也必须为 false。"
                "只输出 JSON，不要输出 Markdown 或解释文字。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"论文标题：{title}\n\n"
                f"用户问题：{question}\n\n"
                f"论文来源片段：\n{paper_context}\n\n"
                f"联网来源片段：\n{web_context}\n\n"
                "输出 JSON："
                "{\"context_sufficient\": false, "
                "\"context_status\": \"insufficient|partial|sufficient\", "
                "\"reason\": \"为什么当前来源够或不够\", "
                "\"missing_information\": [\"还缺什么信息\"]}"
            ),
        },
    ]
