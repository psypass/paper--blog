from __future__ import annotations

import argparse
import json

from paper_blog_agent.workflow import run_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a Markdown and HTML blog from a paper-like source.")
    parser.add_argument("input", help="Local .pdf/.md/.docx path, arXiv ID, or arXiv URL.")
    parser.add_argument("--memory-dir", default="memory", help="Directory for SQLite memory and user_profile.md.")
    parser.add_argument("--output-dir", default="outputs", help="Directory for generated outputs.")
    parser.add_argument(
        "--blog-type",
        default="learning",
        choices=["popular", "learning", "technical"],
        help="Target blog version.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_workflow(
        input_value=args.input,
        memory_dir=args.memory_dir,
        output_dir=args.output_dir,
        blog_type=args.blog_type,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
