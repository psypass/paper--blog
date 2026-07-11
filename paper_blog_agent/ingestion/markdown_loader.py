from __future__ import annotations

import re
from pathlib import Path

from paper_blog_agent.ingestion.common import extract_abstract, extract_authors, file_sha256, first_nonempty_line
from paper_blog_agent.models import PaperSource


class MarkdownLoader:
    def load(self, path: str) -> PaperSource:
        file_path = Path(path)
        text = file_path.read_text(encoding="utf-8")
        heading = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        title = heading.group(1).strip() if heading else first_nonempty_line(text, file_path.stem)
        source_id = file_sha256(file_path)
        return PaperSource(
            source_type="markdown",
            source_id=source_id,
            title=title,
            authors=extract_authors(text),
            abstract=extract_abstract(text),
            raw_text=text,
            metadata={"filename": file_path.name},
            original_path=str(file_path),
        )
