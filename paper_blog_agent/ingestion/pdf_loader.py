from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from paper_blog_agent.ingestion.common import extract_abstract, extract_authors, file_sha256, infer_title_from_text
from paper_blog_agent.models import PaperSource


class PdfLoader:
    def load(self, path: str) -> PaperSource:
        file_path = Path(path)
        reader = PdfReader(str(file_path))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[page {index}]\n{text.strip()}")
        raw_text = "\n\n".join(pages)
        return PaperSource(
            source_type="pdf",
            source_id=file_sha256(file_path),
            title=infer_title_from_text(raw_text, file_path.stem),
            authors=extract_authors(raw_text),
            abstract=extract_abstract(raw_text),
            raw_text=raw_text,
            metadata={"filename": file_path.name, "page_count": len(reader.pages)},
            original_path=str(file_path),
            pdf_path=str(file_path),
        )
