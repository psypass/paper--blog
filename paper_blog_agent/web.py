from __future__ import annotations

import json
import mimetypes
import urllib.parse
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from paper_blog_agent.llm_settings import DEFAULT_PROVIDERS, fetch_and_store_models
from paper_blog_agent.web_api import (
    chat_with_paper,
    delete_history_item,
    generate_from_submission,
    iter_chat_events,
    iter_generate_events,
    list_history,
    load_llm_config_settings,
    load_profile_settings,
    profile_from_fields,
    safe_int,
    save_llm_config_settings,
    save_profile_settings,
    search_settings_from_fields,
)


APP_ROOT = Path(__file__).resolve().parent
WEB_DIR = APP_ROOT.parent / "web"


class PaperBlogRequestHandler(BaseHTTPRequestHandler):
    server_version = "PaperBlogAgent/0.1"

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/api/history":
            self._send_json({"status": "ok", "items": list_history(self.server.memory_dir)})  # type: ignore[attr-defined]
            return
        if parsed.path == "/api/llm/providers":
            self._send_json({"status": "ok", "providers": DEFAULT_PROVIDERS})
            return
        if parsed.path == "/api/llm/config":
            self._send_json(load_llm_config_settings(self.server.memory_dir))  # type: ignore[attr-defined]
            return
        if parsed.path == "/api/profile":
            self._send_json(load_profile_settings(self.server.memory_dir))  # type: ignore[attr-defined]
            return
        if parsed.path.startswith("/assets/"):
            asset = WEB_DIR / parsed.path.removeprefix("/assets/")
            content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
            self._send_file(asset, content_type)
            return
        if parsed.path.startswith("/generated/"):
            self._send_generated_file(parsed.path)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed_path = urllib.parse.urlparse(self.path).path
        if parsed_path == "/api/generate/stream":
            self._post_generate_stream()
            return
        if parsed_path == "/api/chat/stream":
            self._post_chat_stream()
            return
        if parsed_path == "/api/chat":
            self._post_chat()
            return
        if parsed_path == "/api/llm/models":
            self._post_llm_models()
            return
        if parsed_path == "/api/llm/config":
            self._post_llm_config()
            return
        if parsed_path == "/api/history/delete":
            self._post_history_delete()
            return
        if parsed_path == "/api/profile":
            self._post_profile()
            return
        if parsed_path == "/api/generate":
            self._post_generate()
            return
        self.send_error(404)

    def _send_generated_file(self, path: str) -> None:
        parts = [part for part in path.removeprefix("/generated/").split("/") if part]
        if len(parts) != 2:
            self.send_error(404)
            return
        paper_id, filename = parts
        if filename not in {"blog.html", "blog.md", "verification_report.json"}:
            self.send_error(404)
            return
        output_root = self.server.output_dir.resolve()  # type: ignore[attr-defined]
        target = (output_root / paper_id / filename).resolve()
        if output_root not in target.parents:
            self.send_error(403)
            return
        content_type = mimetypes.guess_type(filename)[0] or "text/plain"
        if filename == "blog.html":
            content_type = "text/html; charset=utf-8"
        elif filename == "blog.md":
            content_type = "text/markdown; charset=utf-8"
        elif filename.endswith(".json"):
            content_type = "application/json; charset=utf-8"
        self._send_file(target, content_type)

    def _post_generate_stream(self) -> None:
        try:
            fields, files = self._parse_post()
            events = iter_generate_events(
                fields,
                files,
                memory_dir=self.server.memory_dir,  # type: ignore[attr-defined]
                output_dir=self.server.output_dir,  # type: ignore[attr-defined]
                upload_dir=self.server.upload_dir,  # type: ignore[attr-defined]
            )
        except Exception as exc:  # pragma: no cover
            self._send_sse([{"type": "error", "message": str(exc)}])
            return
        self._send_sse(events)

    def _post_chat_stream(self) -> None:
        try:
            fields, _ = self._parse_post()
            events = iter_chat_events(
                paper_id=fields.get("paper_id", ""),
                question=fields.get("question", ""),
                output_dir=self.server.output_dir,  # type: ignore[attr-defined]
                memory_dir=self.server.memory_dir,  # type: ignore[attr-defined]
                llm_settings=_llm_settings_from_fields(fields),
                web_search_settings=search_settings_from_fields(fields),
            )
        except Exception as exc:  # pragma: no cover
            self._send_sse([{"type": "error", "message": str(exc)}])
            return
        self._send_sse(events)

    def _post_chat(self) -> None:
        try:
            fields, _ = self._parse_post()
            result = chat_with_paper(
                paper_id=fields.get("paper_id", ""),
                question=fields.get("question", ""),
                output_dir=self.server.output_dir,  # type: ignore[attr-defined]
                memory_dir=self.server.memory_dir,  # type: ignore[attr-defined]
                llm_settings=_llm_settings_from_fields(fields),
                web_search_settings=search_settings_from_fields(fields),
            )
            self._send_json(result, status=200 if result.get("status") == "ok" else 400)
        except Exception as exc:  # pragma: no cover
            self._send_json({"status": "error", "message": str(exc)}, status=500)

    def _post_llm_models(self) -> None:
        try:
            fields, _ = self._parse_post()
            result = fetch_and_store_models(
                base_url=fields.get("base_url", ""),
                api_key=fields.get("api_key", ""),
                models_path=fields.get("models_path", "/models") or "/models",
                memory_dir=self.server.memory_dir,  # type: ignore[attr-defined]
                provider_id=fields.get("provider_id", ""),
                model=fields.get("model", ""),
            )
            self._send_json(result, status=200 if result.get("status") == "ok" else 400)
        except Exception as exc:  # pragma: no cover
            self._send_json({"status": "error", "message": str(exc), "models": []}, status=500)

    def _post_llm_config(self) -> None:
        try:
            fields, _ = self._parse_post()
            result = save_llm_config_settings(
                {
                    "llm": {
                        "providerId": fields.get("provider_id", ""),
                        "baseUrl": fields.get("base_url", ""),
                        "modelsPath": fields.get("models_path", "/models") or "/models",
                        "apiKey": fields.get("api_key", ""),
                        "model": fields.get("model", ""),
                        "models": json.loads(fields.get("models", "[]")),
                    },
                    "search": {
                        "mode": fields.get("web_search_mode", "auto") or "auto",
                        "provider": fields.get("search_provider", "tavily") or "tavily",
                        "apiKey": fields.get("search_api_key", ""),
                        "maxResults": safe_int(fields.get("max_search_results", "5"), 5),
                    },
                },
                memory_dir=self.server.memory_dir,  # type: ignore[attr-defined]
            )
            self._send_json(result, status=200 if result.get("status") == "ok" else 400)
        except Exception as exc:  # pragma: no cover
            self._send_json({"status": "error", "message": str(exc)}, status=500)

    def _post_history_delete(self) -> None:
        try:
            fields, _ = self._parse_post()
            result = delete_history_item(
                paper_id=fields.get("paper_id", ""),
                memory_dir=self.server.memory_dir,  # type: ignore[attr-defined]
                output_dir=self.server.output_dir,  # type: ignore[attr-defined]
            )
            self._send_json(result, status=200 if result.get("status") == "ok" else 400)
        except Exception as exc:  # pragma: no cover
            self._send_json({"status": "error", "message": str(exc), "deleted": False}, status=500)

    def _post_profile(self) -> None:
        try:
            fields, _ = self._parse_post()
            result = save_profile_settings(profile_from_fields(fields), memory_dir=self.server.memory_dir)  # type: ignore[attr-defined]
            self._send_json(result, status=200 if result.get("status") == "ok" else 400)
        except Exception as exc:  # pragma: no cover
            self._send_json({"status": "error", "message": str(exc)}, status=500)

    def _post_generate(self) -> None:
        try:
            fields, files = self._parse_post()
            result = generate_from_submission(
                fields,
                files,
                memory_dir=self.server.memory_dir,  # type: ignore[attr-defined]
                output_dir=self.server.output_dir,  # type: ignore[attr-defined]
                upload_dir=self.server.upload_dir,  # type: ignore[attr-defined]
            )
            self._send_json(result, status=200 if result.get("status") == "ok" else 400)
        except Exception as exc:  # pragma: no cover
            self._send_json({"status": "error", "message": str(exc)}, status=500)

    def _parse_post(self) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        if content_type.startswith("multipart/form-data"):
            message = BytesParser(policy=default).parsebytes(
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8") + body
            )
            fields: dict[str, str] = {}
            files: dict[str, dict[str, Any]] = {}
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                filename = part.get_filename()
                payload = part.get_payload(decode=True) or b""
                if not name:
                    continue
                if filename:
                    files[name] = {"filename": filename, "content": payload}
                else:
                    fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            return fields, files

        if content_type.startswith("application/json"):
            payload = json.loads(body.decode("utf-8"))
            fields = {}
            for key, value in payload.items():
                if isinstance(value, (list, dict)):
                    fields[str(key)] = json.dumps(value, ensure_ascii=False)
                else:
                    fields[str(key)] = str(value)
            return fields, {}
        params = urllib.parse.parse_qs(body.decode("utf-8"))
        return {key: values[0] for key, values in params.items()}, {}

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_sse(self, events) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for event in events:
                data = json.dumps(event, ensure_ascii=False).encode("utf-8")
                self.wfile.write(b"data: " + data + b"\n\n")
                self.wfile.flush()
        except BrokenPipeError:
            pass
        except Exception as exc:  # pragma: no cover - defensive SSE boundary
            data = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False).encode("utf-8")
            try:
                self.wfile.write(b"data: " + data + b"\n\n")
                self.wfile.flush()
            except BrokenPipeError:
                pass
        self.close_connection = True


def _llm_settings_from_fields(fields: dict[str, str]) -> dict[str, str]:
    return {
        "base_url": fields.get("base_url", ""),
        "api_key": fields.get("api_key", ""),
        "model": fields.get("model", ""),
    }


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    memory_dir: str | Path = "memory",
    output_dir: str | Path = "outputs",
    upload_dir: str | Path = "uploads",
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), PaperBlogRequestHandler)
    server.memory_dir = Path(memory_dir)  # type: ignore[attr-defined]
    server.output_dir = Path(output_dir)  # type: ignore[attr-defined]
    server.upload_dir = Path(upload_dir)  # type: ignore[attr-defined]
    return server


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Paper Blog Agent web interface.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--memory-dir", default="memory")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--upload-dir", default="uploads")
    args = parser.parse_args()
    server = create_server(args.host, args.port, args.memory_dir, args.output_dir, args.upload_dir)
    print(f"Paper Blog Agent running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
