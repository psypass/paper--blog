from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PaperSource:
    source_type: str
    source_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    raw_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    original_path: str | None = None
    pdf_path: str | None = None
    pdf_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
