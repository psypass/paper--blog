from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from paper_blog_agent.agent_events import done_event, status_event
from paper_blog_agent.exporters import markdown_to_html, write_outputs
from paper_blog_agent.ingestion import resolve_input_source
from paper_blog_agent.ingestion.arxiv_loader import ArxivLoader
from paper_blog_agent.ingestion.docx_loader import DocxLoader
from paper_blog_agent.ingestion.markdown_loader import MarkdownLoader
from paper_blog_agent.ingestion.pdf_loader import PdfLoader
from paper_blog_agent.memory.profile import load_user_profile
from paper_blog_agent.memory.store import MemoryStore
from paper_blog_agent.processing import (
    chunk_text,
    extract_key_info,
    generate_blog,
    generate_llm_page,
    page_payload_has_substance,
    page_blocks_to_markdown,
    plan_blog,
    revise_blog,
    verify_blog,
)

WORKFLOW_NODES = (
    "init_context",
    "load_user_memory",
    "resolve_source",
    "load_source",
    "normalize_paper",
    "check_cache",
    "chunk_source_text",
    "extract_info",
    "save_paper_memory",
    "plan_blog_node",
    "generate_blog_node",
    "verify_blog_node",
    "revise_if_needed",
    "export_outputs",
    "save_knowledge_source",
    "save_generation_history",
)

WORKFLOW_STAGE_BY_NODE = {
    "init_context": "准备记忆中",
    "load_user_memory": "准备记忆中",
    "resolve_source": "解析来源中",
    "load_source": "解析来源中",
    "normalize_paper": "解析来源中",
    "check_cache": "解析来源中",
    "chunk_source_text": "提取内容中",
    "extract_info": "提取内容中",
    "save_paper_memory": "提取内容中",
    "plan_blog_node": "生成解读中",
    "generate_blog_node": "生成解读中",
    "verify_blog_node": "校验来源中",
    "revise_if_needed": "校验来源中",
    "export_outputs": "导出结果中",
    "save_knowledge_source": "导出结果中",
    "save_generation_history": "导出结果中",
}


def run_workflow(
    input_value: str,
    memory_dir: str | Path = "memory",
    output_dir: str | Path = "outputs",
    blog_type: str = "learning",
    llm_settings: dict[str, str] | None = None,
) -> dict[str, Any]:
    state = _initial_state(input_value, memory_dir, output_dir, blog_type, llm_settings)
    for node in _workflow_callables():
        state = node(state)
        if state.get("status") == "error":
            return state
    return _workflow_result(state)


def iter_workflow_events(
    input_value: str,
    memory_dir: str | Path = "memory",
    output_dir: str | Path = "outputs",
    blog_type: str = "learning",
    llm_settings: dict[str, str] | None = None,
):
    state = _initial_state(input_value, memory_dir, output_dir, blog_type, llm_settings)
    last_stage = ""
    for node in _workflow_callables():
        stage = WORKFLOW_STAGE_BY_NODE.get(node.__name__, "")
        if stage and stage != last_stage:
            yield status_event(stage, stage=node.__name__)
            last_stage = stage
        state = node(state)
        if state.get("status") == "error":
            yield done_event(result=state)
            return
    yield done_event(result=_workflow_result(state))


def _initial_state(
    input_value: str,
    memory_dir: str | Path,
    output_dir: str | Path,
    blog_type: str,
    llm_settings: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "input_value": input_value,
        "memory_dir": Path(memory_dir),
        "output_dir": Path(output_dir),
        "blog_type": blog_type,
        "llm_settings": llm_settings or {},
        "errors": [],
    }


def _workflow_callables():
    lookup = globals()
    return tuple(lookup[name] for name in WORKFLOW_NODES)


def _workflow_result(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        "paper_id": state["paper_id"],
        "markdown_path": state["markdown_path"],
        "html_path": state["html_path"],
        "verification_path": state["verification_path"],
        "cache_hit": state.get("cache_hit", False),
        "verification": state["verification"],
        "used_llm_generation": state.get("used_llm_generation", False),
    }


def init_context(state: dict[str, Any]) -> dict[str, Any]:
    state["store"] = MemoryStore(state["memory_dir"] / "papers.sqlite")
    return state


def load_user_memory(state: dict[str, Any]) -> dict[str, Any]:
    state["user_profile"] = load_user_profile(state["memory_dir"])
    return state


def resolve_source(state: dict[str, Any]) -> dict[str, Any]:
    source_type = resolve_input_source(state["input_value"])
    if source_type == "unsupported":
        return {**state, "status": "error", "errors": [f"Unsupported input: {state['input_value']}"]}
    state["source_type"] = source_type
    return state


def load_source(state: dict[str, Any]) -> dict[str, Any]:
    loaders = {
        "pdf": PdfLoader(),
        "markdown": MarkdownLoader(),
        "docx": DocxLoader(),
        "arxiv": ArxivLoader(),
    }
    state["paper_source"] = loaders[state["source_type"]].load(state["input_value"])
    return state


def normalize_paper(state: dict[str, Any]) -> dict[str, Any]:
    source = state["paper_source"]
    state["paper_id"] = f"{source.source_type}-{source.source_id[:16].replace('/', '_')}"
    return state


def check_cache(state: dict[str, Any]) -> dict[str, Any]:
    cached = state["store"].get_paper(state["paper_source"].source_id)
    state["cache_hit"] = cached is not None
    state["cached_paper"] = cached
    return state


def chunk_source_text(state: dict[str, Any]) -> dict[str, Any]:
    state["chunks"] = chunk_text(state["paper_source"].raw_text)
    return state


def extract_info(state: dict[str, Any]) -> dict[str, Any]:
    source = state["paper_source"]
    state["key_info"] = extract_key_info(source.title, source.abstract, state["chunks"])
    return state


def save_paper_memory(state: dict[str, Any]) -> dict[str, Any]:
    source = state["paper_source"]
    state["store"].upsert_paper(
        {
            "paper_id": state["paper_id"],
            "source_type": source.source_type,
            "source_id": source.source_id,
            "title": source.title,
            "authors": source.authors,
            "abstract": source.abstract,
            "tags": state["key_info"].get("keywords", []),
            "original_path": source.original_path,
            "metadata": source.metadata,
        }
    )
    return state


def plan_blog_node(state: dict[str, Any]) -> dict[str, Any]:
    source = state["paper_source"]
    state["outline"] = plan_blog(source.title, state["blog_type"], state["user_profile"])
    return state


def generate_blog_node(state: dict[str, Any]) -> dict[str, Any]:
    source = state["paper_source"]
    page_payload = generate_llm_page(
        source.title,
        source.authors,
        source.abstract,
        state["chunks"],
        state["blog_type"],
        state.get("llm_settings"),
        state.get("user_profile", ""),
    )
    if page_payload and page_payload_has_substance(page_payload):
        state["page_payload"] = page_payload
        state["markdown"] = page_blocks_to_markdown(page_payload, state["outline"]["title"])
        state["used_llm_generation"] = True
    else:
        state["markdown"] = generate_blog(
            source.title,
            source.authors,
            source.abstract,
            state["key_info"],
            state["outline"],
            state["chunks"],
        )
        state["used_llm_generation"] = False
    state["revision_count"] = 0
    return state


def verify_blog_node(state: dict[str, Any]) -> dict[str, Any]:
    state["verification"] = verify_blog(state["markdown"], state["chunks"])
    return state


def revise_if_needed(state: dict[str, Any]) -> dict[str, Any]:
    while state["verification"].get("status") != "pass" and state["revision_count"] < 2:
        state["markdown"] = revise_blog(state["markdown"], state["verification"], state["chunks"])
        state["revision_count"] += 1
        state["verification"] = verify_blog(state["markdown"], state["chunks"])
    return state


def export_outputs(state: dict[str, Any]) -> dict[str, Any]:
    source = state["paper_source"]
    paper_output_dir = state["output_dir"] / state["paper_id"]
    html_text = markdown_to_html(
        state["markdown"],
        {
            "title": source.title,
            "authors": source.authors,
            "source": source.pdf_url or source.original_path or source.source_id,
        },
        state["verification"],
    )
    paths = write_outputs(paper_output_dir, state["markdown"], html_text, state["verification"])
    state.update(paths)
    return state


def save_knowledge_source(state: dict[str, Any]) -> dict[str, Any]:
    source = state["paper_source"]
    knowledge = {
        "paper_id": state["paper_id"],
        "title": source.title,
        "authors": source.authors,
        "abstract": source.abstract,
        "source": source.pdf_url or source.original_path or source.source_id,
        "chunks": state["chunks"],
        "key_info": state["key_info"],
        "paper_knowledge": state.get("page_payload", {}).get("paper_knowledge", {}),
        "page": state.get("page_payload", {}).get("page", {}),
        "verification": state["verification"],
    }
    path = Path(state["html_path"]).parent / "knowledge.json"
    path.write_text(json.dumps(knowledge, ensure_ascii=False, indent=2), encoding="utf-8")
    state["knowledge_path"] = str(path)
    state["store"].index_chunks(state["paper_id"], state["chunks"])
    return state


def save_generation_history(state: dict[str, Any]) -> dict[str, Any]:
    state["store"].save_generation(
        paper_id=state["paper_id"],
        blog_type=state["blog_type"],
        markdown_path=state["markdown_path"],
        html_path=state["html_path"],
        verification_path=state["verification_path"],
        satisfied=None,
    )
    return state
