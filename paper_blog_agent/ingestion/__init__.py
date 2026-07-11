from __future__ import annotations

import re
from pathlib import Path


ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")


def resolve_input_source(input_value: str) -> str:
    value = input_value.strip()
    lower = value.lower()
    if "arxiv.org/abs/" in lower or "arxiv.org/pdf/" in lower or ARXIV_ID_RE.match(value):
        return "arxiv"

    suffix = Path(value).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".docx":
        return "docx"
    return "unsupported"


__all__ = ["resolve_input_source"]
