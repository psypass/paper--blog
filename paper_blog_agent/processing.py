from __future__ import annotations

import json
import re
from typing import Any

from paper_blog_agent.llm_settings import chat_completion
from paper_blog_agent.prompts import build_blog_generation_messages


def chunk_text(text: str, max_chars: int = 1400) -> list[dict]:
    clean = "\n".join(line.rstrip() for line in text.splitlines())
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
    chunks: list[dict] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        if current and current_len + len(paragraph) > max_chars:
            chunks.append({"id": len(chunks) + 1, "text": "\n\n".join(current)})
            current = []
            current_len = 0
        current.append(paragraph)
        current_len += len(paragraph)
    if current:
        chunks.append({"id": len(chunks) + 1, "text": "\n\n".join(current)})
    return chunks or [{"id": 1, "text": text.strip()}]


def extract_key_info(title: str, abstract: str, chunks: list[dict]) -> dict:
    snippets = [chunk["text"][:360].replace("\n", " ") for chunk in chunks[:4]]
    keywords = []
    for word in re.findall(r"[\w\u4e00-\u9fff]{3,}", f"{title} {abstract} {' '.join(snippets)}"):
        if word.lower() not in {item.lower() for item in keywords}:
            keywords.append(word)
        if len(keywords) >= 8:
            break
    return {
        "research_question": abstract or snippets[0] if snippets else title,
        "method": snippets[1] if len(snippets) > 1 else (snippets[0] if snippets else ""),
        "results": snippets[2] if len(snippets) > 2 else "",
        "limitations": "需要结合原文进一步人工核对图表、公式和实验细节。",
        "keywords": keywords,
        "source_chunk_ids": [chunk["id"] for chunk in chunks[:4]],
    }


def plan_blog(title: str, blog_type: str, profile: str) -> dict:
    label = {"popular": "科普版", "learning": "学习版", "technical": "技术版"}.get(blog_type, "学习版")
    return {
        "label": label,
        "sections": ["导语", "核心问题", "方法解释", "结果解读", "局限与注意点", "总结"],
        "profile": profile,
        "title": f"{title}：{label}解读",
    }


def generate_blog(title: str, authors: list[str], abstract: str, key_info: dict, outline: dict, chunks: list[dict]) -> str:
    authors_text = "、".join(authors) if authors else "未知作者"
    source_refs = ", ".join(f"[来源 {chunk_id}]" for chunk_id in key_info.get("source_chunk_ids", []))
    first_source = chunks[0]["text"][:220].replace("\n", " ") if chunks else ""
    return (
        f"# {outline['title']}\n\n"
        f"> 原论文：{title}  \n"
        f"> 作者：{authors_text}  \n"
        f"> 版本：{outline['label']}\n\n"
        f"## 导语\n\n"
        f"这篇材料关注的问题可以概括为：{key_info['research_question']} {source_refs}\n\n"
        f"## 核心问题\n\n"
        f"原文的核心信息来自材料中的关键片段。系统会先抽取文本、切分来源，再把内容重构成更适合阅读的博客草稿。[来源 1]\n\n"
        f"## 方法解释\n\n"
        f"{key_info['method'] or first_source} [来源 1]\n\n"
        f"## 结果解读\n\n"
        f"{key_info['results'] or abstract or '原文结果需要结合完整材料继续核对。'} {source_refs}\n\n"
        f"## 局限与注意点\n\n"
        f"{key_info['limitations']} 自动生成内容应保留人工复核环节，尤其是公式、图表和实验设置。\n\n"
        f"## 总结\n\n"
        f"这份草稿把原文内容整理为{outline['label']}，适合作为后续人工编辑和 HTML 展示的基础。\n"
    )


def verify_blog(markdown: str, chunks: list[dict]) -> dict:
    refs = {int(match) for match in re.findall(r"\[来源\s*(\d+)\]", markdown)}
    chunk_ids = {chunk["id"] for chunk in chunks}
    missing = sorted(refs - chunk_ids)
    status = "pass" if refs and not missing else "weak"
    return {
        "status": status,
        "referenced_chunks": sorted(refs),
        "missing_references": missing,
        "message": "引用均可对应原文切片。" if status == "pass" else "引用不足或存在无法对应的来源。",
    }


def revise_blog(markdown: str, verification: dict, chunks: list[dict]) -> str:
    if verification.get("status") == "pass" or not chunks:
        return markdown
    if "[来源" in markdown:
        return markdown
    return (
        markdown.rstrip()
        + "\n\n"
        + "## 来源补充\n\n"
        + f"以上草稿的主要判断应回到原文切片继续核对，优先参考 [来源 {chunks[0]['id']}]。"
        + "\n"
    )


def generate_llm_page(
    title: str,
    authors: list[str],
    abstract: str,
    chunks: list[dict],
    blog_type: str,
    llm_settings: dict[str, str] | None,
    user_profile: str = "",
) -> dict[str, Any] | None:
    if not llm_settings or not llm_settings.get("api_key") or not llm_settings.get("base_url") or not llm_settings.get("model"):
        return None
    source_pack = "\n\n".join(
        f"[来源 {chunk['id']}]\n{chunk.get('text', '')[:1400]}" for chunk in chunks[:8]
    )
    messages = build_blog_generation_messages(title, authors, abstract, source_pack, blog_type, user_profile)
    result = chat_completion(
        base_url=llm_settings["base_url"],
        api_key=llm_settings["api_key"],
        model=llm_settings["model"],
        messages=messages,
        temperature=0.2,
    )
    if result.get("status") != "ok":
        return None
    return _parse_json_object(result["content"])


def _parse_json_object(content: str) -> dict[str, Any] | None:
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict) or "page" not in payload:
        return None
    return payload


def page_blocks_to_markdown(page_payload: dict[str, Any], fallback_title: str) -> str:
    page = page_payload.get("page", {})
    title = page.get("title") or fallback_title
    lines = [f"# {title}", ""]
    knowledge = page_payload.get("paper_knowledge", {})
    summary = knowledge.get("one_sentence_summary")
    if summary:
        lines.extend([f"> {summary}", ""])
    for block in _as_list(page.get("blocks")):
        if not isinstance(block, dict):
            continue
        block_title = block.get("title", "未命名模块")
        lines.extend([f"## {block_title}", ""])
        for paragraph in _as_list(block.get("paragraphs")):
            lines.extend([str(paragraph), ""])
        for item in _as_list(block.get("items")):
            if isinstance(item, dict):
                text = item.get("text") or item.get("claim") or item.get("label") or json.dumps(item, ensure_ascii=False)
            else:
                text = str(item)
            lines.append(f"- {text}")
        if _as_list(block.get("items")):
            lines.append("")
        refs = _as_list(block.get("source_chunk_ids"))
        if refs:
            normalized_refs = [_normalize_source_ref(ref) for ref in refs]
            normalized_refs = [ref for ref in normalized_refs if ref]
            if normalized_refs:
                lines.extend([" ".join(f"[来源 {ref}]" for ref in normalized_refs), ""])
    return "\n".join(lines).strip() + "\n"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_source_ref(ref: Any) -> str:
    match = re.search(r"\d+", str(ref))
    return match.group(0) if match else ""


def page_payload_has_substance(page_payload: dict[str, Any]) -> bool:
    blocks = _as_list(page_payload.get("page", {}).get("blocks"))
    body_units = 0
    for block in blocks:
        if not isinstance(block, dict):
            continue
        body_units += sum(1 for paragraph in _as_list(block.get("paragraphs")) if len(str(paragraph).strip()) >= 12)
        body_units += sum(1 for item in _as_list(block.get("items")) if len(str(item).strip()) >= 12)
    return body_units >= 1
