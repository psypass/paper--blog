from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any, Protocol


@dataclass
class SearchResult:
    title: str
    url: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class SearchProvider(Protocol):
    provider_id: str

    def search(self, query: str, api_key: str, max_results: int = 5) -> dict[str, Any]:
        ...


class TavilySearchProvider:
    provider_id = "tavily"

    def search(self, query: str, api_key: str, max_results: int = 5) -> dict[str, Any]:
        return search_tavily(query=query, api_key=api_key, max_results=max_results)


SEARCH_PROVIDERS: dict[str, SearchProvider] = {
    TavilySearchProvider.provider_id: TavilySearchProvider(),
}


def search_web(query: str, settings: dict[str, Any] | None) -> dict[str, Any]:
    if not settings:
        return {"status": "error", "message": "Search settings are required.", "results": []}
    provider = str(settings.get("provider") or "tavily").lower()
    adapter = SEARCH_PROVIDERS.get(provider)
    if not adapter:
        return {"status": "error", "message": f"Unsupported search provider: {provider}", "results": []}
    return adapter.search(
        query=query,
        api_key=str(settings.get("api_key") or ""),
        max_results=int(settings.get("max_results") or 5),
    )


def search_tavily(query: str, api_key: str, max_results: int = 5) -> dict[str, Any]:
    if not api_key.strip():
        return {"status": "error", "message": "Search API key is required.", "results": []}
    body = json.dumps(
        {
            "query": query,
            "search_depth": "basic",
            "max_results": max(1, min(max_results, 10)),
            "include_answer": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.tavily.com/search",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "message": str(exc), "results": []}

    results = []
    for item in payload.get("results", []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or item.get("snippet") or "").strip()
        if title and url:
            results.append(SearchResult(title=title, url=url, content=content).to_dict())
    return {"status": "ok", "results": results}
