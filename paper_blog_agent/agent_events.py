from __future__ import annotations

from typing import Any


def status_event(text: str, stage: str = "", **extra: Any) -> dict[str, Any]:
    event = {"type": "status", "text": text}
    if stage:
        event["stage"] = stage
    event.update(extra)
    return event


def state_event(**state: Any) -> dict[str, Any]:
    return {"type": "state", **state}


def done_event(**payload: Any) -> dict[str, Any]:
    return {"type": "done", **payload}


def error_event(message: str, **extra: Any) -> dict[str, Any]:
    return {"type": "error", "message": message, **extra}
