from __future__ import annotations

from paper_blog_agent.prompts.blog_modes import BLOG_MODE_GUIDANCE


def build_blog_generation_messages(
    title: str,
    authors: list[str],
    abstract: str,
    source_pack: str,
    blog_type: str,
    user_profile: str = "",
) -> list[dict[str, str]]:
    mode_guidance = BLOG_MODE_GUIDANCE.get(blog_type, BLOG_MODE_GUIDANCE["learning"])
    return [
        {
            "role": "system",
            "content": (
                "你是论文阅读产品的信息架构师，任务是把论文来源片段重构成可渲染的结构化页面数据。"
                "必须只输出一个合法 JSON 对象，不要输出 Markdown、代码块或解释性前后缀。"
                "不要生成目录型空壳；每个 block 必须有实质性 paragraphs 或 items。"
                "所有重要判断都必须能回到 source_chunk_ids，不能编造来源没有支持的结论。"
                "如果来源不足，要在 block 中说明不足，而不是补充外部知识。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"论文标题：{title}\n"
                f"作者：{'、'.join(authors) if authors else '未知'}\n"
                f"摘要：{abstract or '未提供'}\n"
                f"输出模式：{blog_type}\n"
                f"当前模式要求：\n{mode_guidance}\n\n"
                f"用户偏好：\n{user_profile or '未提供，使用默认清晰可靠风格。'}\n\n"
                "允许的 block.type 包括：overview、problem、concept、mechanism、architecture、experiment、"
                "comparison、limitation、takeaway、source_note。\n"
                "page.blocks 建议 5 到 8 个；每个 block 包含 type、title、paragraphs、items、source_chunk_ids。"
                "paper_knowledge 至少包含 one_sentence_summary、core_problem、key_concepts、contributions、limitations。"
                "paragraphs 写成可直接展示给用户的中文，不要只写章节名。"
                "source_chunk_ids 只能使用来源片段中出现的数字 ID。\n\n"
                f"来源片段：\n{source_pack}\n\n"
                "输出 JSON 形状："
                "{\"paper_knowledge\": {...}, "
                "\"page\": {\"title\": \"...\", \"level\": \"popular|learning|technical\", \"blocks\": [...]}}"
            ),
        },
    ]
