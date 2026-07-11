from __future__ import annotations

import hashlib
import re
from pathlib import Path


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def first_nonempty_line(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip().strip("#").strip()
        if stripped:
            return stripped
    return fallback


def infer_title_from_text(text: str, fallback: str) -> str:
    bad_fragments = (
        "[page",
        "provided proper attribution",
        "permission to reproduce",
        "google hereby grants",
        "reproduce the tables",
        "figures in this paper",
        "journalistic",
        "scholarly works",
        "abstract",
    )
    for line in text.splitlines():
        stripped = line.strip().strip("#").strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(fragment in lowered for fragment in bad_fragments):
            continue
        if "@" in stripped:
            continue
        if len(stripped) > 120:
            continue
        return stripped
    return fallback


def extract_authors(text: str) -> list[str]:
    match = re.search(r"^authors?\s*:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return []
    return [item.strip() for item in re.split(r",|;|、", match.group(1)) if item.strip()]


def extract_abstract(text: str) -> str:
    inline = re.search(r"^abstract\s*:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    if inline:
        return inline.group(1).strip()
    block = re.search(
        r"(?:^|\n)abstract\s*\n+(.+?)(?:\n#{1,6}\s|\n\n[A-Z][^\n]{0,80}\n|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if block:
        return " ".join(block.group(1).split())
    return ""
