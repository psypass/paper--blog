from __future__ import annotations


def build_verification_messages(markdown: str, source_pack: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是论文内容忠实性审校员。请检查博客草稿中的关键说法是否被来源片段支持。"
                "只输出 JSON，不要输出 Markdown。"
                "对每条 claim 给出 status：supported、weak、unsupported。"
                "unsupported 必须给出 revision_suggestion。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"来源片段：\n{source_pack}\n\n"
                f"博客草稿：\n{markdown}\n\n"
                "输出 JSON：{\"overall_status\": \"pass|weak|fail\", "
                "\"claims\": [{\"claim\": \"...\", \"status\": \"...\", "
                "\"source_chunk_ids\": [1], \"revision_suggestion\": \"...\"}]}"
            ),
        },
    ]
