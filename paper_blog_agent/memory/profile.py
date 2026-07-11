from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_PROFILE = """# User Profile

- language: 中文
- default_blog_type: learning
- target_reader: 正在学习该方向的读者
- tone: 清晰、可靠、避免营销腔
- structure: 导语、核心问题、方法解释、结果解读、局限、总结
- depth: 中等
- math_level: 保留必要公式并解释直觉
- focus_areas: 方法、核心概念、局限
"""

DEFAULT_PROFILE_SETTINGS: dict[str, Any] = {
    "language": "中文",
    "default_blog_type": "learning",
    "target_reader": "正在学习该方向的读者",
    "tone": "清晰、可靠、避免营销腔",
    "structure": ["导语", "核心问题", "方法解释", "结果解读", "局限", "总结"],
    "depth": "中等",
    "math_level": "保留必要公式并解释直觉",
    "focus_areas": ["方法", "核心概念", "局限"],
}

LIST_FIELDS = {"structure", "focus_areas"}


def load_user_profile(memory_dir: str | Path) -> str:
    path = Path(memory_dir) / "user_profile.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(DEFAULT_PROFILE, encoding="utf-8")
    return path.read_text(encoding="utf-8")


def load_profile_settings(memory_dir: str | Path) -> dict[str, Any]:
    text = load_user_profile(memory_dir)
    settings = dict(DEFAULT_PROFILE_SETTINGS)
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        key = key.strip()
        value = value.strip()
        if key not in settings:
            continue
        if key in LIST_FIELDS:
            settings[key] = _split_list_value(value)
        elif value:
            settings[key] = value
    return settings


def save_profile_settings(settings: dict[str, Any], memory_dir: str | Path) -> dict[str, Any]:
    normalized = normalize_profile_settings(settings)
    path = Path(memory_dir) / "user_profile.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_profile_settings(normalized), encoding="utf-8")
    return normalized


def normalize_profile_settings(settings: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(DEFAULT_PROFILE_SETTINGS)
    for key in normalized:
        value = settings.get(key)
        if value in (None, ""):
            continue
        if key in LIST_FIELDS:
            if isinstance(value, str):
                normalized[key] = _split_list_value(value)
            elif isinstance(value, list):
                normalized[key] = [str(item).strip() for item in value if str(item).strip()]
        else:
            normalized[key] = str(value).strip()
    return normalized


def format_profile_settings(settings: dict[str, Any]) -> str:
    lines = ["# User Profile", ""]
    for key in DEFAULT_PROFILE_SETTINGS:
        value = settings.get(key, DEFAULT_PROFILE_SETTINGS[key])
        if isinstance(value, list):
            value_text = "、".join(str(item) for item in value)
        else:
            value_text = str(value)
        lines.append(f"- {key}: {value_text}")
    return "\n".join(lines) + "\n"


def _split_list_value(value: str) -> list[str]:
    import re

    return [item.strip() for item in re.split(r"[,，、]", value) if item.strip()]
