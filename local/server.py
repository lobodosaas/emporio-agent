"""Run the whole project on your machine with only an LLM API key: no Cloudflare.

    cp .env.example .env        # put one API key in it
    uv run --group local python -m local.server
    open http://localhost:8787

Serves the same website (public/) and the same API routes as the Worker,
using the same agent and tools (src/). Conversation memory goes to a local
SQLite file (.local/emporio.db) instead of Durable Objects. Leads and
handoffs are printed in this terminal and kept in the same database.
"""

import argparse
import asyncio
import json
import mimetypes
import os
import re
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import site_data  # noqa: E402
from agent import run_turn  # noqa: E402
from local.llm import from_env  # noqa: E402

PUBLIC = ROOT / "public"
DB_PATH = ROOT / ".local" / "emporio.db"
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_MESSAGE_CHARS = 500


def load_dotenv(path=ROOT / ".env"):
    """Minimal .env reader (KEY=value lines); real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Store:
    """Conversation history and team inbox, the local stand-in for Durable Objects."""

    def __init__(self, path=DB_PATH):
        path.parent.mkdir(exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.db.execute("CREATE TABLE IF NOT EXISTS history (session_id TEXT PRIMARY KEY, messages TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS inbox (id INTEGER PRIMARY KEY, item TEXT NOT NULL)")
            self.db.commit()

    def history(self, session_id):
        with self.lock:
            row = self.db.execute("SELECT messages FROM history WHERE session_id = ?", (session_id,)).fetchone()
        return json.loads(row[0]) if row else []

    def save_history(self, session_id, messages):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO history VALUES (?, ?)",
                            (session_id, json.dumps(messages, ensure_ascii=False)))
            self.db.commit()

    def reset(self, session_id):
        with self.lock:
            self.db.execute("DELETE FROM history WHERE session_id = ?", (session_id,))
            self.db.commit()

    def add_to_inbox(self, item):
        with self.lock:
            self.db.execute("INSERT INTO inbox (item) VALUES (?)", (json.dumps(item, ensure_ascii=False),))
            self.db.commit()

    def inbox(self):
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute("SELECT item FROM inbox ORDER BY id")]


def make_handler(store, llm):
    class Handler(BaseHTTPRequestHandler):
        server_version = "emporio-local"

        def log_message(self, fmt, *args):  # quieter console: only errors and events
            pass

        def send_json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def read_json(self):
            try:
                length = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(length) or b"null")
            except ValueError:
                return None
            return body if isinstance(body, dict) else None

        def do_GET(self):
            path = self.path.split("?")[0].split("#")[0]
            if path == "/api/home":
                return self.send_json(site_data.home())
            if path == "/api/policies":
                return self.send_json(site_data.policies())
            if path == "/api/inbox":  # local only: no token, the server listens on 127.0.0.1
                return self.send_json(store.inbox())
            if path.startswith("/api/"):
                return self.send_json({"error": "not found"}, 404)
            self.serve_static(path)

        def serve_static(self, path):
            # Same pretty URLs as Cloudflare assets: /politicas -> politicas.html
            relative = "index.html" if path == "/" else path.lstrip("/")
            target = (PUBLIC / relative).resolve()
            if target.suffix == "" and target.with_suffix(".html").exists():
                target = target.with_suffix(".html")
            if PUBLIC not in target.parents or not target.is_file():
                self.send_response(404)
                self.end_headers()
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("content-type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            body = self.read_json()
            if body is None:
                return self.send_json({"error": "body must be a JSON object"}, 400)
            session_id = str(body.get("session_id", ""))
            if not SESSION_RE.match(session_id):
                return self.send_json({"error": "invalid session_id"}, 400)
            if self.path == "/api/history":
                return self.send_json(store.history(session_id))
            if self.path == "/api/reset":
                store.reset(session_id)
                return self.send_json({"ok": True})
            if self.path != "/api/chat":
                return self.send_json({"error": "not found"}, 404)

            message = str(body.get("message", "")).strip()
            if not message:
                return self.send_json({"error": "empty message"}, 400)
            if len(message) > MAX_MESSAGE_CHARS:
                return self.send_json({"error": f"message longer than {MAX_MESSAGE_CHARS} characters"}, 413)

            reply, history, events, trace = asyncio.run(run_turn(llm, store.history(session_id), message))
            store.save_history(session_id, history)
            for event in events:
                item = {**event, "session_id": session_id,
                        "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                store.add_to_inbox(item)
                print(f"[{event['type'].upper()}] " + ", ".join(f"{k}={v}" for k, v in event.items() if k != "type"))
            self.send_json({"reply": reply, "trace": trace})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    load_dotenv()
    provider, model, llm = from_env()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(Store(), llm))
    print(f"Empório da Música running locally with {provider} ({model})")
    print(f"Open http://localhost:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
