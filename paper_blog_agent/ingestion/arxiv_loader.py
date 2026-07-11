from __future__ import annotations

import re
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from paper_blog_agent.ingestion.pdf_loader import PdfLoader
from paper_blog_agent.models import PaperSource


class ArxivLoader:
    API_URL = "https://export.arxiv.org/api/query"

    def load(self, input_value: str) -> PaperSource:
        arxiv_id = self._extract_id(input_value)
        metadata = self._fetch_metadata(arxiv_id)
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        pdf_path = self._download_pdf(arxiv_id, pdf_url)
        source = PdfLoader().load(str(pdf_path))
        source.source_type = "arxiv"
        source.source_id = arxiv_id
        source.title = metadata.get("title") or source.title
        source.authors = metadata.get("authors") or source.authors
        source.abstract = metadata.get("abstract") or source.abstract
        source.metadata.update(metadata)
        source.original_path = input_value
        source.pdf_url = pdf_url
        return source

    def _extract_id(self, input_value: str) -> str:
        value = input_value.strip()
        match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", value, flags=re.IGNORECASE)
        if match:
            return match.group(1).removesuffix(".pdf")
        return value

    def _fetch_metadata(self, arxiv_id: str) -> dict:
        query = urllib.parse.urlencode({"id_list": arxiv_id})
        with urllib.request.urlopen(f"{self.API_URL}?{query}", timeout=20) as response:
            root = ET.fromstring(response.read())
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return {}
        title = "".join(entry.findtext("atom:title", default="", namespaces=ns).split())
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        abstract = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
        authors = [
            (author.findtext("atom:name", default="", namespaces=ns) or "").strip()
            for author in entry.findall("atom:author", ns)
        ]
        return {
            "title": title,
            "authors": [author for author in authors if author],
            "abstract": abstract,
            "published": entry.findtext("atom:published", default="", namespaces=ns),
            "updated": entry.findtext("atom:updated", default="", namespaces=ns),
        }

    def _download_pdf(self, arxiv_id: str, pdf_url: str) -> Path:
        safe_name = arxiv_id.replace("/", "_")
        target = Path(tempfile.gettempdir()) / "paper_blog_agent_arxiv" / f"{safe_name}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            urllib.request.urlretrieve(pdf_url, target)
        return target
