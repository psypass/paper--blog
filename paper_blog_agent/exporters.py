from __future__ import annotations

import html
import json
import re
from pathlib import Path


def markdown_to_html(markdown: str, metadata: dict, verification: dict) -> str:
    body_lines = []
    in_list = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("# "):
            body_lines.append(f"<h1>{html.escape(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            section_id = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", stripped[3:]).strip("-")
            body_lines.append(f'<h2 id="{html.escape(section_id)}">{html.escape(stripped[3:])}</h2>')
        elif stripped.startswith(">"):
            body_lines.append(f"<blockquote>{html.escape(stripped.lstrip('> ').strip())}</blockquote>")
        elif stripped.startswith("- "):
            if not in_list:
                body_lines.append("<ul>")
                in_list = True
            body_lines.append(f"<li>{html.escape(stripped[2:])}</li>")
        else:
            body_lines.append(f"<p>{_link_sources(html.escape(stripped))}</p>")
    if in_list:
        body_lines.append("</ul>")

    title = metadata.get("title", "Paper Blog")
    authors = "、".join(metadata.get("authors", [])) or "未知作者"
    source = metadata.get("source", "")
    verification_json = html.escape(json.dumps(verification, ensure_ascii=False, indent=2))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <script>
    (function () {{
      try {{
        var theme = localStorage.getItem("paper-blog-agent.theme");
        if (theme === "dark" || theme === "light") {{
          document.documentElement.dataset.theme = theme;
        }}
      }} catch (error) {{}}
    }})();
  </script>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f7f5;
      --surface: #ffffff;
      --surface-soft: #f1f3f4;
      --text: #202124;
      --muted: #5f6368;
      --border: #dddddd;
      --border-soft: #ececec;
      --quote-text: #4b4f4b;
      --quote-border: #4f6f52;
      --source: #315c9b;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f1115;
        --surface: #171a21;
        --surface-soft: #202632;
        --text: #f4f4f5;
        --muted: #a1a1aa;
        --border: #2a303b;
        --border-soft: #3a4352;
        --quote-text: #d4d4d8;
        --quote-border: #60a5fa;
        --source: #93c5fd;
      }}
    }}
    :root[data-theme="light"] {{
      color-scheme: light;
      --bg: #f7f7f5;
      --surface: #ffffff;
      --surface-soft: #f1f3f4;
      --text: #202124;
      --muted: #5f6368;
      --border: #dddddd;
      --border-soft: #ececec;
      --quote-text: #4b4f4b;
      --quote-border: #4f6f52;
      --source: #315c9b;
    }}
    :root[data-theme="dark"] {{
      color-scheme: dark;
      --bg: #0f1115;
      --surface: #171a21;
      --surface-soft: #202632;
      --text: #f4f4f5;
      --muted: #a1a1aa;
      --border: #2a303b;
      --border-soft: #3a4352;
      --quote-text: #d4d4d8;
      --quote-border: #60a5fa;
      --source: #93c5fd;
    }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--text); background: var(--bg); }}
    main {{ max-width: 920px; margin: 0 auto; padding: 32px 20px 56px; }}
    .paper-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 24px; }}
    .meta {{ color: var(--muted); line-height: 1.7; }}
    article {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 28px; }}
    h1 {{ font-size: 30px; line-height: 1.25; margin: 0 0 18px; }}
    h2 {{ font-size: 21px; margin-top: 30px; border-bottom: 1px solid var(--border-soft); padding-bottom: 8px; }}
    p, blockquote, li {{ font-size: 16px; line-height: 1.75; }}
    blockquote {{ border-left: 4px solid var(--quote-border); margin-left: 0; padding-left: 14px; color: var(--quote-text); }}
    .source-ref {{ color: var(--source); font-weight: 600; }}
    pre {{ white-space: pre-wrap; background: var(--surface-soft); border-radius: 6px; padding: 12px; }}
    details {{ margin-top: 24px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }}
    summary {{ cursor: pointer; padding: 14px 16px; font-weight: 650; }}
    details pre {{ margin: 0; border-radius: 0 0 8px 8px; }}
  </style>
</head>
<body>
  <main>
    <section class="paper-card">
      <h1>{html.escape(title)}</h1>
      <div class="meta">作者：{html.escape(authors)}</div>
      <div class="meta">来源：{html.escape(source)}</div>
      <div class="meta">忠实性检查：{html.escape(verification.get("status", "unknown"))}</div>
    </section>
    <article>
      {''.join(body_lines)}
    </article>
    <details>
      <summary>来源校验</summary>
      <pre>{verification_json}</pre>
    </details>
  </main>
</body>
</html>
"""


def _link_sources(text: str) -> str:
    return re.sub(r"\[来源\s*(\d+)\]", r'<span class="source-ref">[来源 \1]</span>', text)


def write_outputs(output_dir: Path, markdown: str, html_text: str, verification: dict) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "blog.md"
    html_path = output_dir / "blog.html"
    verification_path = output_dir / "verification_report.json"
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    verification_path.write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
        "verification_path": str(verification_path),
    }
