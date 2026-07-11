from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from paper_blog_agent.agents.chat_agent import ChatAgent, ChatRequest
from paper_blog_agent.ingestion import resolve_input_source
from paper_blog_agent.llm_settings import load_llm_config, save_llm_config
from paper_blog_agent.memory.profile import (
    load_profile_settings as read_profile_settings,
    save_profile_settings as write_profile_settings,
)
from paper_blog_agent.memory.store import MemoryStore
from paper_blog_agent.workflow import iter_workflow_events, run_workflow


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "-", name.strip())
    return cleaned.strip(".-") or "upload.md"


def resolve_submission_input(
    fields: dict[str, str],
    files: dict[str, dict[str, Any]],
    upload_dir: str | Path = "uploads",
) -> str:
    input_value = fields.get("source_text", "").strip()
    source_name = fields.get("source_name", "").strip()

    file_info = files.get("file")
    if file_info and file_info.get("content"):
        upload_root = Path(upload_dir)
        upload_root.mkdir(parents=True, exist_ok=True)
        upload_path = upload_root / safe_filename(file_info.get("filename") or "upload")
        upload_path.write_bytes(file_info["content"])
        return str(upload_path)

    if input_value and source_name:
        detected_from_name = resolve_input_source(source_name)
        if detected_from_name in {"markdown", "docx", "pdf"}:
            upload_root = Path(upload_dir)
            upload_root.mkdir(parents=True, exist_ok=True)
            upload_path = upload_root / safe_filename(source_name)
            upload_path.write_text(input_value, encoding="utf-8")
            return str(upload_path)

    return input_value


def generate_from_submission(
    fields: dict[str, str],
    files: dict[str, dict[str, Any]],
    memory_dir: str | Path = "memory",
    output_dir: str | Path = "outputs",
    upload_dir: str | Path = "uploads",
) -> dict[str, Any]:
    input_value = resolve_submission_input(fields, files, upload_dir)
    if not input_value:
        return {"status": "error", "message": "请粘贴论文链接，或上传一份材料。"}

    detected_type = resolve_input_source(input_value)
    result = run_workflow(
        input_value=input_value,
        memory_dir=memory_dir,
        output_dir=output_dir,
        blog_type=fields.get("blog_type", "learning") or "learning",
        llm_settings={
            "base_url": fields.get("base_url", ""),
            "api_key": fields.get("api_key", ""),
            "model": fields.get("model", ""),
        },
    )
    if result.get("status") != "ok":
        return result | {"detected_type": detected_type}

    return _result_payload(result, detected_type)


def iter_generate_events(
    fields: dict[str, str],
    files: dict[str, dict[str, Any]],
    memory_dir: str | Path = "memory",
    output_dir: str | Path = "outputs",
    upload_dir: str | Path = "uploads",
):
    yield {"type": "status", "text": "接收材料中"}
    input_value = resolve_submission_input(fields, files, upload_dir)
    if not input_value:
        yield {"type": "error", "message": "请粘贴论文链接，或上传一份材料。"}
        return

    detected_type = resolve_input_source(input_value)
    final_result: dict[str, Any] | None = None
    for event in iter_workflow_events(
        input_value=input_value,
        memory_dir=memory_dir,
        output_dir=output_dir,
        blog_type=fields.get("blog_type", "learning") or "learning",
        llm_settings={
            "base_url": fields.get("base_url", ""),
            "api_key": fields.get("api_key", ""),
            "model": fields.get("model", ""),
        },
    ):
        if event.get("type") == "done":
            final_result = event["result"]
        else:
            yield event

    if not final_result:
        yield {"type": "error", "message": "生成失败。"}
        return
    if final_result.get("status") != "ok":
        yield {"type": "error", "message": final_result.get("message") or "; ".join(final_result.get("errors", [])) or "生成失败。"}
        return

    yield {"type": "done", "result": _result_payload(final_result, detected_type)}


def _result_payload(result: dict[str, Any], detected_type: str) -> dict[str, Any]:
    markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
    html = Path(result["html_path"]).read_text(encoding="utf-8")
    verification = json.loads(Path(result["verification_path"]).read_text(encoding="utf-8"))
    return result | {
        "detected_type": detected_type,
        "markdown": markdown,
        "html": html,
        "html_url": f"/generated/{result['paper_id']}/blog.html",
        "verification": verification,
        "used_llm_generation": result.get("used_llm_generation", False),
    }


def list_history(memory_dir: str | Path = "memory") -> list[dict[str, Any]]:
    store = MemoryStore(Path(memory_dir) / "papers.sqlite")
    rows = store.list_recent_papers()
    return [
        {
            "paper_id": row["paper_id"],
            "title": row["title"],
            "source_type": row["source_type"],
            "abstract": row["abstract"] or "",
            "last_read_at": row["last_read_at"],
        }
        for row in rows
    ]


def delete_history_item(
    paper_id: str,
    memory_dir: str | Path = "memory",
    output_dir: str | Path = "outputs",
) -> dict[str, Any]:
    paper_id = paper_id.strip()
    if not paper_id:
        return {"status": "error", "message": "缺少 paper_id。", "deleted": False}

    store = MemoryStore(Path(memory_dir) / "papers.sqlite")
    deleted = store.delete_paper(paper_id)
    output_root = Path(output_dir).resolve()
    target = (output_root / paper_id).resolve()
    if target.exists() and output_root in target.parents:
        shutil.rmtree(target)
    return {"status": "ok", "paper_id": paper_id, "deleted": deleted}


def load_profile_settings(memory_dir: str | Path = "memory") -> dict[str, Any]:
    return {"status": "ok", "profile": read_profile_settings(memory_dir)}


def save_profile_settings(settings: dict[str, Any], memory_dir: str | Path = "memory") -> dict[str, Any]:
    profile = write_profile_settings(settings, memory_dir)
    return {"status": "ok", "profile": profile}


def load_llm_config_settings(memory_dir: str | Path = "memory") -> dict[str, Any]:
    return {"status": "ok", "config": load_llm_config(memory_dir)}


def save_llm_config_settings(settings: dict[str, Any], memory_dir: str | Path = "memory") -> dict[str, Any]:
    return {"status": "ok", "config": save_llm_config(settings, memory_dir)}


def chat_with_paper(
    paper_id: str,
    question: str,
    output_dir: str | Path = "outputs",
    memory_dir: str | Path = "memory",
    llm_settings: dict[str, str] | None = None,
    web_search_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ChatAgent().answer(
        ChatRequest(
            paper_id=paper_id,
            question=question,
            output_dir=output_dir,
            memory_dir=memory_dir,
            llm_settings=llm_settings,
            web_search_settings=web_search_settings,
        )
    )


def iter_chat_events(
    paper_id: str,
    question: str,
    output_dir: str | Path = "outputs",
    memory_dir: str | Path = "memory",
    llm_settings: dict[str, str] | None = None,
    web_search_settings: dict[str, Any] | None = None,
):
    return ChatAgent().iter_events(
        ChatRequest(
            paper_id=paper_id,
            question=question,
            output_dir=output_dir,
            memory_dir=memory_dir,
            llm_settings=llm_settings,
            web_search_settings=web_search_settings,
        )
    )


def search_settings_from_fields(fields: dict[str, str]) -> dict[str, Any]:
    return {
        "mode": fields.get("web_search_mode", "auto") or "auto",
        "provider": fields.get("search_provider", "tavily") or "tavily",
        "api_key": fields.get("search_api_key", ""),
        "max_results": safe_int(fields.get("max_search_results", "5"), 5),
    }


def profile_from_fields(fields: dict[str, str]) -> dict[str, Any]:
    return {
        "language": fields.get("language", ""),
        "default_blog_type": fields.get("default_blog_type", ""),
        "target_reader": fields.get("target_reader", ""),
        "tone": fields.get("tone", ""),
        "structure": parse_field_list(fields.get("structure", "")),
        "depth": fields.get("depth", ""),
        "math_level": fields.get("math_level", ""),
        "focus_areas": parse_field_list(fields.get("focus_areas", "")),
    }


def parse_field_list(value: str) -> list[str]:
    if not value:
        return []
    try:
        payload = json.loads(value)
        if isinstance(payload, list):
            return [str(item).strip() for item in payload if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in re.split(r"[,，、]", value) if item.strip()]


def truthy(value: str) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


def safe_int(value: str, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
