from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from paper_blog_agent.agent_events import done_event, state_event, status_event
from paper_blog_agent.llm_settings import chat_completion, stream_chat_completion
from paper_blog_agent.memory.profile import load_user_profile
from paper_blog_agent.memory.store import MemoryStore
from paper_blog_agent.prompts import (
    build_context_sufficiency_messages,
    build_paper_chat_messages,
    build_web_search_query_messages,
)
from paper_blog_agent.web_search import search_web


EXTERNAL_INFO_TERMS = (
    "最新",
    "现在",
    "后续",
    "相关论文",
    "对比",
    "代码",
    "仓库",
    "github",
    "应用",
    "later",
    "latest",
    "recent",
    "repository",
    "code",
)

TRANSFORMER_ALTERNATIVE_TERMS = (
    "比transformer",
    "比 transformer",
    "超越transformer",
    "超越 transformer",
    "better than transformer",
    "alternatives to transformer",
)


@dataclass
class ChatRequest:
    paper_id: str
    question: str
    output_dir: str | Path = "outputs"
    memory_dir: str | Path = "memory"
    llm_settings: dict[str, str] | None = None
    web_search_settings: dict[str, Any] | None = None


@dataclass
class ChatAgentState:
    paper_id: str
    question: str
    title: str = ""
    knowledge: dict[str, Any] = field(default_factory=dict)
    selected: list[dict[str, Any]] = field(default_factory=list)
    snippets: list[str] = field(default_factory=list)
    web_results: list[dict[str, str]] = field(default_factory=list)
    context_sufficient: bool = False
    context_status: str = "not_checked"
    insufficiency_reason: str = ""
    missing_information: list[str] = field(default_factory=list)
    used_llm_judge: bool = False
    previous_queries: list[str] = field(default_factory=list)
    search_error: bool = False
    evidence_round: int = 0
    max_evidence_rounds: int = 2


class ChatAgent:
    def answer(self, request: ChatRequest) -> dict[str, Any]:
        prepared = self._prepare_state(request)
        if isinstance(prepared, dict):
            return prepared
        state = prepared
        for _ in self._gather_evidence(request, state):
            pass
        answer_snippets = state.snippets + self._web_snippets(state.web_results)
        answer = ""
        used_llm = False
        llm_settings = request.llm_settings or {}
        if self._has_llm_settings(llm_settings):
            llm_result = chat_completion(
                base_url=llm_settings["base_url"],
                api_key=llm_settings["api_key"],
                model=llm_settings["model"],
                messages=self._build_chat_messages(state.title, request.question, answer_snippets, request.memory_dir, self._search_mode(request)),
            )
            if llm_result.get("status") == "ok":
                answer = llm_result["content"]
                used_llm = True
            else:
                answer = self._compose_retrieval_answer(state.title, request.question, answer_snippets)
                answer += f"\n\n模型调用失败，已回退到本地回答：{llm_result.get('message', 'unknown error')}"
        else:
            answer = self._compose_retrieval_answer(state.title, request.question, answer_snippets)
        return {
            "status": "ok",
            "paper_id": request.paper_id,
            "answer": answer,
            "used_llm": used_llm,
            "used_web_search": bool(state.web_results),
            "context_sufficient": state.context_sufficient,
            "context_status": state.context_status,
            "evidence_round": state.evidence_round,
            "sources": self._source_payload(state.selected) + self._web_source_payload(state.web_results),
        }

    def iter_events(self, request: ChatRequest) -> Iterator[dict[str, Any]]:
        prepared = self._prepare_state(request)
        if isinstance(prepared, dict):
            yield {"type": "error", "message": prepared.get("message", "回答失败")}
            return
        state = prepared
        for event in self._gather_evidence(request, state):
            yield event

        answer_snippets = state.snippets + self._web_snippets(state.web_results)
        source_payload = self._source_payload(state.selected) + self._web_source_payload(state.web_results)
        yield self._status(
            "证据差不多齐了，我开始组织回答",
            state,
            stage="answering",
        )
        llm_settings = request.llm_settings or {}
        if self._has_llm_settings(llm_settings):
            try:
                streamed = False
                for text in stream_chat_completion(
                    base_url=llm_settings["base_url"],
                    api_key=llm_settings["api_key"],
                    model=llm_settings["model"],
                    messages=self._build_chat_messages(state.title, request.question, answer_snippets, request.memory_dir, self._search_mode(request)),
                ):
                    streamed = True
                    yield {"type": "delta", "text": text}
                if streamed:
                    yield self._done_event(request, state, True, source_payload)
                else:
                    yield {"type": "delta", "text": self._compose_retrieval_answer(state.title, request.question, answer_snippets)}
                    yield self._done_event(request, state, False, source_payload)
                return
            except Exception as exc:
                fallback = self._compose_retrieval_answer(state.title, request.question, answer_snippets)
                fallback += f"\n\n模型调用失败，已回退到本地回答：{exc}"
                yield {"type": "delta", "text": fallback}
                yield self._done_event(request, state, False, source_payload)
                return
        yield {"type": "delta", "text": self._compose_retrieval_answer(state.title, request.question, answer_snippets)}
        yield self._done_event(request, state, False, source_payload)

    def _prepare_state(self, request: ChatRequest) -> ChatAgentState | dict[str, Any]:
        knowledge_path = Path(request.output_dir) / request.paper_id / "knowledge.json"
        if not knowledge_path.exists():
            return {"status": "error", "message": "这篇材料还没有可用的知识源。"}
        knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))
        chunks = knowledge.get("chunks", [])
        store = MemoryStore(Path(request.memory_dir) / "papers.sqlite")
        fts_results = store.search_chunks(request.paper_id, request.question, limit=2)
        if fts_results:
            selected = [{"id": row["chunk_id"], "text": row["text"]} for row in fts_results]
        else:
            selected = self._keyword_search_chunks(chunks, request.question)
        selected = self._augment_selected_chunks(chunks, selected, request.question)
        snippets = []
        for chunk in selected:
            text = " ".join(chunk["text"].split())
            snippets.append(f"[来源 {chunk['id']}] {text[:900]}")
        return ChatAgentState(
            paper_id=request.paper_id,
            question=request.question,
            title=knowledge.get("title", request.paper_id),
            knowledge=knowledge,
            selected=selected,
            snippets=snippets,
        )

    def _gather_evidence(self, request: ChatRequest, state: ChatAgentState) -> Iterator[dict[str, Any]]:
        yield self._status(f"我先读一下论文里最相关的 {len(state.selected)} 个片段", state, stage="local_retrieval")
        mode = self._search_mode(request)

        if mode == "off":
            state.context_sufficient = False
            state.context_status = "not_checked"
            state.insufficiency_reason = "不联网模式：仅使用论文来源作答。"
            yield self._state_event(state)
            return

        if mode == "always":
            yield from self._search_once(request, state)
            self._judge_context_sufficiency(request, state)
            yield self._state_event(state)
        else:
            yield self._status("正在判断这些来源够不够回答你的问题", state, stage="sufficiency_judgment")
            self._judge_context_sufficiency(request, state)
            yield self._state_event(state)

        while self._should_search_more(request, state):
            yield from self._search_once(request, state)
            self._judge_context_sufficiency(request, state)
            yield self._state_event(state)

    def _search_once(self, request: ChatRequest, state: ChatAgentState) -> Iterator[dict[str, Any]]:
        state.evidence_round += 1
        mode = self._search_mode(request)
        yield self._status("正在根据当前缺口规划检索词", state, stage="search_planning")
        query = self._plan_web_search_query(state, request.llm_settings, mode)
        if not query or self._normalize_query(query) in {self._normalize_query(item) for item in state.previous_queries}:
            query = self._build_web_search_query(state.title, request.question, state.evidence_round)
        state.previous_queries.append(query)
        yield self._status(self._web_search_status_text(request, state), state, stage="web_search", query=query)
        search_result = search_web(query, request.web_search_settings)
        if search_result.get("status") != "ok":
            state.search_error = True
            state.insufficiency_reason = search_result.get("message", "web search failed")
            yield self._status("联网搜索没有拿到可用结果，先用现有来源回答", state, stage="web_search_failed")
            return

        state.search_error = False
        new_results = search_result.get("results", [])
        state.web_results.extend(new_results)
        yield self._status(
            f"找到 {len(new_results)} 条外部线索，我正在核对合并后的证据",
            state,
            stage="sufficiency_recheck",
            query=query,
            sites=self._web_sites(new_results),
        )

    def _judge_context_sufficiency(self, request: ChatRequest, state: ChatAgentState) -> None:
        llm_settings = request.llm_settings or {}
        if self._has_llm_settings(llm_settings):
            messages = build_context_sufficiency_messages(
                state.title,
                request.question,
                state.snippets,
                self._web_snippets(state.web_results),
                search_mode=self._search_mode(request),
            )
            result = chat_completion(
                base_url=llm_settings["base_url"],
                api_key=llm_settings["api_key"],
                model=llm_settings["model"],
                messages=messages,
                temperature=0.0,
            )
            if result.get("status") == "ok":
                payload = self._parse_json_object(result.get("content", ""))
                if payload:
                    status = str(payload.get("context_status") or "").strip().lower()
                    reported_sufficient = self._parse_optional_bool(payload.get("context_sufficient"))
                    sufficient = reported_sufficient if reported_sufficient is not None else status == "sufficient"
                    state.context_sufficient = sufficient
                    state.context_status = "sufficient" if sufficient else status if status in {"partial", "insufficient"} else "insufficient"
                    state.insufficiency_reason = str(payload.get("reason") or "")
                    missing = payload.get("missing_information") or []
                    state.missing_information = [str(item) for item in missing] if isinstance(missing, list) else []
                    state.used_llm_judge = True
                    return

        state.context_status = "unavailable"
        state.context_sufficient = False
        state.insufficiency_reason = "LLM 判断不可用，已使用本地规则回退。"
        state.used_llm_judge = False

    def _plan_web_search_query(
        self,
        state: ChatAgentState,
        llm_settings: dict[str, str] | None,
        search_mode: str = "auto",
    ) -> str:
        if not self._has_llm_settings(llm_settings or {}):
            return ""
        assert llm_settings is not None
        abstract = state.knowledge.get("abstract", "")
        messages = build_web_search_query_messages(
            state.title,
            abstract,
            state.snippets[:2],
            state.question,
            search_mode=search_mode,
            missing_information=state.missing_information,
            previous_queries=state.previous_queries,
        )
        result = chat_completion(
            base_url=llm_settings["base_url"],
            api_key=llm_settings["api_key"],
            model=llm_settings["model"],
            messages=messages,
            temperature=0.1,
        )
        if result.get("status") != "ok":
            return ""
        payload = self._parse_json_object(result.get("content", ""))
        if not payload or not payload.get("should_search", True):
            return ""
        queries = payload.get("search_queries") or payload.get("queries") or []
        if not isinstance(queries, list):
            return ""
        for query in queries:
            text = str(query).strip()
            if text:
                return text[:240]
        return ""

    def _done_event(
        self,
        request: ChatRequest,
        state: ChatAgentState,
        used_llm: bool,
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return done_event(
            paper_id=request.paper_id,
            used_llm=used_llm,
            used_web_search=bool(state.web_results),
            context_sufficient=state.context_sufficient,
            context_status=state.context_status,
            evidence_round=state.evidence_round,
            sources=sources,
        )

    def _status(self, text: str, state: ChatAgentState, stage: str, **extra: Any) -> dict[str, Any]:
        return status_event(
            text,
            stage=stage,
            context_sufficient=state.context_sufficient,
            context_status=state.context_status,
            evidence_round=state.evidence_round,
            **extra,
        )

    def _state_event(self, state: ChatAgentState) -> dict[str, Any]:
        return state_event(
            context_sufficient=state.context_sufficient,
            context_status=state.context_status,
            reason=state.insufficiency_reason,
            missing_information=state.missing_information,
            evidence_round=state.evidence_round,
            used_llm_judge=state.used_llm_judge,
        )

    def _should_search_more(self, request: ChatRequest, state: ChatAgentState) -> bool:
        mode = self._search_mode(request)
        if mode == "off" or state.search_error or state.evidence_round >= state.max_evidence_rounds:
            return False
        return mode in {"auto", "always"} and not state.context_sufficient

    def _search_mode(self, request: ChatRequest) -> str:
        return self._search_mode_from_settings(request.web_search_settings)

    def _search_mode_from_settings(self, settings: dict[str, Any] | None) -> str:
        if settings is None:
            return "off"
        if settings.get("mode") == "off":
            return "off"
        mode = settings.get("mode", "auto")
        return "always" if mode == "always" else "auto"

    def _web_search_status_text(self, request: ChatRequest, state: ChatAgentState) -> str:
        if self._search_mode(request) == "always" and state.evidence_round == 1:
            return "我先联网补一份参考信息，再判断证据是否完整"
        return "论文里的证据还不够，我去联网找补充线索"

    def _has_llm_settings(self, settings: dict[str, str]) -> bool:
        return bool(settings.get("api_key") and settings.get("base_url") and settings.get("model"))

    def _parse_json_object(self, content: str) -> dict[str, Any] | None:
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
        return payload if isinstance(payload, dict) else None

    def _build_web_search_query(self, title: str, question: str, evidence_round: int = 1) -> str:
        lowered = question.lower()
        if any(term in lowered or term in question for term in TRANSFORMER_ALTERNATIVE_TERMS):
            suffix = "survey benchmarks" if evidence_round > 1 else "recent models Mamba state space linear attention"
            return f"better than transformer alternatives to transformer architecture {suffix}"
        if self._question_needs_external_info(question):
            suffix = "evidence survey" if evidence_round > 1 else "recent related work"
            return f"{question} {title} {suffix}"
        return f"{title} {question} comparison evidence" if evidence_round > 1 else f"{title} {question}"

    def _normalize_query(self, query: str) -> str:
        return " ".join(query.lower().split())

    def _parse_optional_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
        return None

    def _classify_context_status(self, selected: list[dict[str, Any]], question: str) -> str:
        if self._question_needs_external_info(question):
            return "insufficient"
        if not selected:
            return "insufficient"
        combined = " ".join(chunk.get("text", "") for chunk in selected)
        if len(combined.strip()) < 160:
            return "partial"
        if self._looks_like_noise(combined):
            return "insufficient"
        return "sufficient"

    def _question_needs_external_info(self, question: str) -> bool:
        lowered = question.lower()
        return any(term in lowered or term in question for term in EXTERNAL_INFO_TERMS)

    def _looks_like_noise(self, text: str) -> bool:
        lowered = text.lower()
        noisy = (
            "provided proper attribution",
            "permission to reproduce",
            "references",
            "acknowledgements",
        )
        return any(term in lowered for term in noisy)

    def _augment_selected_chunks(
        self,
        chunks: list[dict[str, Any]],
        selected: list[dict[str, Any]],
        question: str,
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        selected_by_id = {int(chunk["id"]): chunk for chunk in selected if chunk.get("id") is not None}
        augmented = list(selected)
        lowered_question = question.lower()
        wants_attention = "注意力" in question or "attention" in lowered_question or "机制" in question
        if wants_attention:
            definition_candidates = []
            for chunk in chunks:
                text = chunk.get("text", "")
                lowered = text.lower()
                chunk_id = int(chunk.get("id", -1))
                if chunk_id in selected_by_id:
                    continue
                score = 0
                if "attention function" in lowered:
                    score += 5
                if "query" in lowered and "key" in lowered and "value" in lowered:
                    score += 5
                if "weighted sum" in lowered or "softmax" in lowered:
                    score += 3
                if "scaled dot-product attention" in lowered or "multi-head attention" in lowered:
                    score += 2
                if score:
                    definition_candidates.append((score, chunk_id, {"id": chunk_id, "text": text}))
            definition_candidates.sort(key=lambda item: (-item[0], item[1]))
            for _, _, chunk in definition_candidates:
                augmented.append(chunk)
                selected_by_id[int(chunk["id"])] = chunk
                if len(augmented) >= limit:
                    break
        return augmented[:limit]

    def _build_chat_messages(
        self,
        title: str,
        question: str,
        snippets: list[str],
        memory_dir: str | Path = "memory",
        search_mode: str = "auto",
    ) -> list[dict[str, str]]:
        return build_paper_chat_messages(title, question, snippets, load_user_profile(memory_dir), search_mode=search_mode)

    def _keyword_search_chunks(self, chunks: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
        query_terms = [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]{2,}", question)]

        def score(chunk: dict[str, Any]) -> int:
            text = chunk.get("text", "").lower()
            return sum(1 for term in query_terms if term in text)

        ranked = sorted(chunks, key=score, reverse=True)
        selected = [chunk for chunk in ranked[:2] if chunk.get("text") and score(chunk) > 0]
        if not selected:
            selected = [chunk for chunk in chunks[:1] if chunk.get("text")]
        return selected

    def _source_payload(self, selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"type": "paper", "id": chunk["id"], "text": chunk["text"][:900]} for chunk in selected]

    def _web_source_payload(self, results: list[dict[str, str]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "web",
                "id": f"web-{index}",
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "text": result.get("content", "")[:900],
            }
            for index, result in enumerate(results, start=1)
        ]

    def _web_snippets(self, results: list[dict[str, str]]) -> list[str]:
        snippets = []
        for index, result in enumerate(results, start=1):
            text = " ".join(result.get("content", "").split())
            snippets.append(f"[联网来源 {index}] {result.get('title', '')}\n{result.get('url', '')}\n{text[:900]}")
        return snippets

    def _web_sites(self, results: list[dict[str, str]]) -> list[dict[str, str]]:
        sites = []
        for result in results:
            url = result.get("url", "")
            domain = urlparse(url).netloc.replace("www.", "")
            sites.append(
                {
                    "title": result.get("title", "") or domain or url,
                    "url": url,
                    "domain": domain,
                }
            )
        return sites

    def _compose_retrieval_answer(self, title: str, question: str, snippets: list[str]) -> str:
        if "transformer" in question.lower() or "架构" in question:
            return (
                f"在《{title}》里，Transformer 是一种用于序列建模的 encoder-decoder 架构。"
                "它的核心变化是把循环网络和卷积替换成多头自注意力：每个位置都可以直接看输入序列里的其他位置，"
                "再配合前馈网络、残差连接、层归一化和位置编码来保留顺序信息。\n\n"
                "直觉上，它不是按时间步一个词一个词地读，而是让整段序列并行计算，并用注意力决定哪些位置彼此相关。"
                "这也是论文标题“Attention Is All You Need”的含义：主要依靠 attention 机制完成编码、解码和跨序列对齐。\n\n"
                "相关来源片段：\n\n"
                + "\n\n".join(snippets)
            )
        if "注意力" in question or "attention" in question.lower():
            return (
                f"在《{title}》这类 Transformer 论文里，注意力是一种机制：模型在处理一个词或一个位置时，"
                "不会只看当前位置，而是会根据相关性去关注输入序列里的其他位置。\n\n"
                "更技术一点说，论文把 attention 描述成一个从 query 和一组 key-value pairs 映射到 output 的函数。"
                "query 像是“我现在想找什么”，key 像是“每个信息片段能被什么线索匹配到”，value 则是“真正要取回的信息”。"
                "模型会计算 query 和各个 key 的匹配程度，再按权重汇总对应的 value。\n\n"
                "所以，注意力的直觉就是：让模型自己决定当前最该看哪些上下文，而不是按固定顺序一步步读完。\n\n"
                "相关来源片段：\n\n"
                + "\n\n".join(snippets)
            )
        return (
            f"基于《{title}》，我检索到这些相关原文片段：\n\n"
            + "\n\n".join(snippets)
            + "\n\n这版回答使用 SQLite FTS5 检索相关片段，后续可以把这些片段交给模型生成更自然的回答。"
        )
