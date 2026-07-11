from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


DEFAULT_PROVIDERS = [
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models_path": "/models",
        "default_model": "deepseek-chat",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models_path": "/models",
        "default_model": "gpt-5.2",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models_path": "/models",
        "default_model": "openai/gpt-5.2",
    },
    {
        "id": "kimi",
        "name": "Moonshot Kimi Global",
        "base_url": "https://api.moonshot.ai/v1",
        "models_path": "/models",
        "default_model": "kimi-k2-0711-preview",
    },
    {
        "id": "kimi-cn",
        "name": "Moonshot Kimi China",
        "base_url": "https://api.moonshot.cn/v1",
        "models_path": "/models",
        "default_model": "kimi-k2-0711-preview",
    },
    {
        "id": "dashscope",
        "name": "Alibaba DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models_path": "/models",
        "default_model": "qwen-plus",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models_path": "/models",
        "default_model": "gemini-2.5-pro",
    },
    {
        "id": "groq",
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models_path": "/models",
        "default_model": "llama-3.3-70b-versatile",
    },
    {
        "id": "custom",
        "name": "Custom",
        "base_url": "",
        "models_path": "/models",
        "default_model": "",
    },
]


DEFAULT_LLM_CONFIG = {
    "version": 1,
    "llm": {
        "providerId": "deepseek",
        "baseUrl": "https://api.deepseek.com",
        "modelsPath": "/models",
        "apiKey": "",
        "model": "deepseek-chat",
        "models": [],
    },
    "search": {
        "mode": "auto",
        "provider": "tavily",
        "apiKey": "",
        "maxResults": 5,
    },
}


def _config_path(memory_dir: str | Path = "memory") -> Path:
    return Path(memory_dir) / "llm_config.json"


def load_llm_config(memory_dir: str | Path = "memory") -> dict[str, Any]:
    path = _config_path(memory_dir)
    config = json.loads(json.dumps(DEFAULT_LLM_CONFIG))
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                config["llm"].update(payload.get("llm") or {})
                config["search"].update(payload.get("search") or {})
        except json.JSONDecodeError:
            pass
    return config


def save_llm_config(settings: dict[str, Any], memory_dir: str | Path = "memory") -> dict[str, Any]:
    current = load_llm_config(memory_dir)
    llm = settings.get("llm") or {}
    search = settings.get("search") or {}
    if isinstance(llm, dict):
        current["llm"].update(llm)
    if isinstance(search, dict):
        current["search"].update(search)
    path = _config_path(memory_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def fetch_and_store_models(
    base_url: str,
    api_key: str,
    models_path: str = "/models",
    memory_dir: str | Path = "memory",
    provider_id: str = "",
    model: str = "",
) -> dict[str, Any]:
    result = fetch_models(base_url=base_url, api_key=api_key, models_path=models_path)
    if result.get("status") != "ok":
        return result
    models = result.get("models", [])
    selected_model = model if model in models else models[0] if models else model
    config = save_llm_config(
        {
            "llm": {
                "providerId": provider_id,
                "baseUrl": base_url,
                "modelsPath": models_path,
                "apiKey": api_key,
                "model": selected_model,
                "models": models,
            }
        },
        memory_dir=memory_dir,
    )
    return result | {"model": selected_model, "config": config}


def normalize_models_response(payload: dict[str, Any]) -> list[str]:
    models = []
    for item in payload.get("data", []):
        model_id = item.get("id") if isinstance(item, dict) else None
        if model_id:
            models.append(str(model_id))
    return sorted(set(models), key=str.lower)


def build_endpoint(base_url: str, endpoint_path: str) -> str:
    base = base_url.strip().rstrip("/")
    path = endpoint_path.strip()
    if not base:
        return ""
    parsed = urlsplit(base)
    parsed_path = parsed.path.rstrip("/")
    wanted = "/" + path.lstrip("/")
    wanted_no_slash = wanted.lstrip("/")
    if parsed_path.endswith(wanted) or parsed_path.endswith(wanted_no_slash):
        return base
    if parsed.query and ("chat/completions" in parsed_path or "models" in parsed_path):
        return base
    return base + wanted


def fetch_models(base_url: str, api_key: str, models_path: str = "/models") -> dict[str, Any]:
    if not base_url.strip():
        return {"status": "error", "message": "Base URL is required.", "models": []}
    if not api_key.strip():
        return {"status": "error", "message": "API key is required.", "models": []}

    url = build_endpoint(base_url, models_path)
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"status": "ok", "models": normalize_models_response(payload)}
    except Exception as exc:
        return {"status": "error", "message": str(exc), "models": []}


def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
) -> dict[str, Any]:
    if not base_url.strip() or not api_key.strip() or not model.strip():
        return {"status": "error", "message": "LLM base_url, api_key and model are required."}
    url = build_endpoint(base_url, "/chat/completions")
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        return {"status": "ok", "content": content}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def stream_chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
):
    if not base_url.strip() or not api_key.strip() or not model.strip():
        raise ValueError("LLM base_url, api_key and model are required.")
    url = build_endpoint(base_url, "/chat/completions")
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                break
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = payload.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content")
            if content:
                yield str(content)
