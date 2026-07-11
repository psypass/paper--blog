from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MemoryStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    authors_json TEXT NOT NULL,
                    abstract TEXT,
                    tags_json TEXT NOT NULL,
                    original_path TEXT,
                    last_read_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id TEXT NOT NULL,
                    blog_type TEXT NOT NULL,
                    markdown_path TEXT NOT NULL,
                    html_path TEXT NOT NULL,
                    verification_path TEXT NOT NULL,
                    satisfied INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(paper_id) REFERENCES papers(paper_id)
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
                    paper_id UNINDEXED,
                    chunk_id UNINDEXED,
                    text
                )
                """
            )

    def upsert_paper(self, paper: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc).isoformat()
        paper_id = paper["paper_id"]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO papers (
                    paper_id, source_type, source_id, title, authors_json, abstract,
                    tags_json, original_path, last_read_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    title=excluded.title,
                    authors_json=excluded.authors_json,
                    abstract=excluded.abstract,
                    tags_json=excluded.tags_json,
                    original_path=excluded.original_path,
                    last_read_at=excluded.last_read_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    paper_id,
                    paper["source_type"],
                    paper["source_id"],
                    paper["title"],
                    json.dumps(paper.get("authors", []), ensure_ascii=False),
                    paper.get("abstract", ""),
                    json.dumps(paper.get("tags", []), ensure_ascii=False),
                    paper.get("original_path"),
                    now,
                    json.dumps(paper.get("metadata", {}), ensure_ascii=False),
                ),
            )
        return paper_id

    def get_paper(self, source_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM papers WHERE source_id = ?", (source_id,)).fetchone()
        return dict(row) if row else None

    def save_generation(
        self,
        paper_id: str,
        blog_type: str,
        markdown_path: str,
        html_path: str,
        verification_path: str,
        satisfied: bool | None,
    ) -> None:
        value = None if satisfied is None else int(satisfied)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO generations (
                    paper_id, blog_type, markdown_path, html_path,
                    verification_path, satisfied, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    paper_id,
                    blog_type,
                    markdown_path,
                    html_path,
                    verification_path,
                    value,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def list_generations(self, paper_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM generations WHERE paper_id = ? ORDER BY created_at DESC",
                (paper_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_recent_papers(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM papers ORDER BY last_read_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_paper(self, paper_id: str) -> bool:
        with self._connect() as conn:
            exists = conn.execute("SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
            conn.execute("DELETE FROM chunk_fts WHERE paper_id = ?", (paper_id,))
            conn.execute("DELETE FROM generations WHERE paper_id = ?", (paper_id,))
            conn.execute("DELETE FROM papers WHERE paper_id = ?", (paper_id,))
        return exists is not None

    def index_chunks(self, paper_id: str, chunks: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chunk_fts WHERE paper_id = ?", (paper_id,))
            conn.executemany(
                "INSERT INTO chunk_fts (paper_id, chunk_id, text) VALUES (?, ?, ?)",
                [(paper_id, int(chunk["id"]), chunk.get("text", "")) for chunk in chunks],
            )

    def search_chunks(self, paper_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        normalized = self._normalize_fts_query(query)
        if not normalized:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT chunk_id, text, bm25(chunk_fts) AS rank
                FROM chunk_fts
                WHERE paper_id = ? AND chunk_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (paper_id, normalized, max(limit * 4, 8)),
            ).fetchall()
        ranked = [
            {"id": int(row["chunk_id"]), "chunk_id": int(row["chunk_id"]), "text": row["text"], "rank": row["rank"]}
            for row in rows
        ]
        ranked.sort(key=lambda row: (self._chunk_penalty(row["text"]), row["rank"]))
        return ranked[:limit]

    def _normalize_fts_query(self, query: str) -> str:
        import re

        terms = re.findall(r"[\w\u4e00-\u9fff]{2,}", query)
        expanded = list(terms)
        glossary = {
            "注意力": ["attention", "self", "query", "key", "value"],
            "自注意力": ["self", "attention", "query", "key", "value"],
            "transformer": ["transformer", "encoder", "decoder", "self", "attention", "architecture"],
            "架构": ["architecture", "encoder", "decoder", "stack", "layer"],
            "编码器": ["encoder"],
            "解码器": ["decoder"],
            "查询": ["query"],
            "键": ["key"],
            "值": ["value"],
        }
        for term in terms:
            for zh, additions in glossary.items():
                if zh in term:
                    expanded.extend(additions)
        terms = []
        for term in expanded:
            if term not in terms:
                terms.append(term)
        return " OR ".join(terms[:12])

    def _chunk_penalty(self, text: str) -> int:
        lowered = text.lower()
        penalty = 0
        if "provided proper attribution" in lowered or "permission to reproduce" in lowered:
            penalty += 4
        if lowered.count("@") >= 2:
            penalty += 2
        if "abstract" in lowered or "introduction" in lowered:
            penalty -= 1
        if "query" in lowered and "key" in lowered and "value" in lowered:
            penalty -= 3
        if "encoder" in lowered and "decoder" in lowered:
            penalty -= 3
        if "self-attention" in lowered or "multi-head attention" in lowered:
            penalty -= 2
        return penalty
