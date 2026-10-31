"""Cloudflare Worker entry point.

Routes:
  POST /api/chat   {"session_id", "message"} -> {"reply"}
  POST /api/reset  {"session_id"}            -> clears that customer's history
  GET  /api/inbox  (Bearer ADMIN_TOKEN)      -> leads and handoffs for the team
  anything else    -> static chat UI from public/

Each customer session is one Durable Object (Conversation) holding its own
history and daily quota. A single "__global__" instance keeps the global
daily cap and the team inbox.
"""

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from workers import DurableObject, Response, WorkerEntrypoint, fetch

from agent import run_turn
from prompt import store_now

SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_MESSAGE_CHARS = 500
INBOX_LIMIT = 500
LIMIT_REPLY = (
    "Você atingiu o limite de mensagens por hoje com a assistente virtual. "
    "Fale com a equipe pelo WhatsApp (67) 3341-4444, de segunda a sexta das 09:00 às 18:00 e sábado das 09:00 às 13:00."
)
BUSY_REPLY = "Estamos com muitas mensagens agora. Tente de novo em instantes, por favor."


def escape_chat(value):
    """Neutralize Slack/Discord markup in customer-provided text (<!channel>, @everyone, links)."""
    text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text.replace("@", "@​")


def error(message, status):
    return Response.json({"error": message}, status=status)


class WorkersAI:
    """LLM adapter: Workers AI binding, OpenAI-style chat completion with tools."""

    def __init__(self, env):
        self.env = env

    async def __call__(self, messages, tools):
        out = await self.env.AI.run(self.env.MODEL, {
            "messages": messages,
            "tools": tools,
            "max_tokens": int(self.env.MAX_OUTPUT_TOKENS),
            "temperature": 0.2,
        })
        data = json.loads(json.dumps(out))
        message = data["choices"][0]["message"]
        return {"content": message.get("content"), "tool_calls": message.get("tool_calls") or []}


class Conversation(DurableObject):
    async def _load(self, key, default):
        raw = await self.ctx.storage.get(key)
        return json.loads(raw) if raw else default

    async def _save(self, key, value):
        await self.ctx.storage.put(key, json.dumps(value, ensure_ascii=False))

    async def _consume(self, key, limit):
        """Count one use for today; False once the daily limit is reached."""
        today = store_now().date().isoformat()
        usage = await self._load(key, {})
        if usage.get("day") != today:
            usage = {"day": today, "count": 0}
        if usage["count"] >= limit:
            return False
        usage["count"] += 1
        await self._save(key, usage)
        return True

    async def chat(self, message):
        if not await self._consume("usage", int(self.env.DAILY_LIMIT_PER_SESSION)):
            return json.dumps({"reply": LIMIT_REPLY, "limited": True, "events": []})
        history = await self._load("history", [])
        reply, history, events, trace = await run_turn(WorkersAI(self.env), history, message)
        await self._save("history", history)
        return json.dumps({"reply": reply, "events": events, "trace": trace}, ensure_ascii=False)

    async def reset(self):
        # The daily quota survives a reset, so resetting is not a way around it.
        await self.ctx.storage.delete("history")

    # Methods below are used on the "__global__" instance only.

    async def consume_global(self):
        return await self._consume("global_usage", int(self.env.DAILY_LIMIT_GLOBAL))

    async def add_to_inbox(self, item_json):
        inbox = await self._load("inbox", [])
        inbox.append(json.loads(item_json))
        await self._save("inbox", inbox[-INBOX_LIMIT:])

    async def read_inbox(self):
        return json.dumps(await self._load("inbox", []), ensure_ascii=False)


class Default(WorkerEntrypoint):
    def _stub(self, name):
        return self.env.CONVERSATION.get(self.env.CONVERSATION.idFromName(name))

    async def fetch(self, request):
        path = urlparse(request.url).path
        if path == "/api/chat" and request.method == "POST":
            return await self.chat(request)
        if path == "/api/reset" and request.method == "POST":
            body = await self._body(request)
            if not body or not SESSION_RE.match(str(body.get("session_id", ""))):
                return error("invalid session_id", 400)
            await self._stub(body["session_id"]).reset()
            return Response.json({"ok": True})
        if path == "/api/inbox" and request.method == "GET":
            return await self.inbox(request)
        if path.startswith("/api/"):
            return error("not found", 404)
        return await self.env.ASSETS.fetch(request)

    async def _body(self, request):
        try:
            body = json.loads(await request.text())
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    async def chat(self, request):
        body = await self._body(request)
        if body is None:
            return error("body must be a JSON object", 400)
        session_id = str(body.get("session_id", ""))
        message = str(body.get("message", "")).strip()
        if not SESSION_RE.match(session_id):
            return error("invalid session_id", 400)
        if not message:
            return error("empty message", 400)
        if len(message) > MAX_MESSAGE_CHARS:
            return error(f"message longer than {MAX_MESSAGE_CHARS} characters", 413)

        # Layer 1: burst limits per session and per IP (approximate, per location).
        ip = request.headers.get("cf-connecting-ip") or "local"
        for limiter, key in ((self.env.RATE_LIMIT_SESSION, session_id), (self.env.RATE_LIMIT_IP, ip)):
            outcome = await limiter.limit({"key": key})
            if not outcome.success:
                return Response.json({"reply": BUSY_REPLY, "limited": True}, status=429)

        # Layer 2: global daily cap on model calls, strict (single Durable Object).
        if not await self._stub("__global__").consume_global():
            return Response.json({"reply": LIMIT_REPLY, "limited": True}, status=429)

        # Layer 3: per-session daily quota, inside the session's Durable Object.
        result = json.loads(await self._stub(session_id).chat(message))

        for event in result.pop("events", []):
            item = {**event, "session_id": session_id, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            await self._stub("__global__").add_to_inbox(json.dumps(item, ensure_ascii=False))
            await self.notify(item)

        if str(self.env.SHOW_TRACE) != "true":
            result.pop("trace", None)
        return Response.json(result)

    async def notify(self, item):
        """Optional: push leads/handoffs to a team webhook (Slack/Discord/etc.)."""
        url = getattr(self.env, "TEAM_WEBHOOK_URL", None)
        if not url:
            return
        label = "Novo lead" if item["type"] == "lead" else "Cliente pedindo atendimento humano"
        text = f"{label}: " + ", ".join(f"{k}={escape_chat(v)}" for k, v in item.items() if k != "type")
        # "text" is read by Slack, "content" by Discord; mentions are disabled on both.
        payload = {"text": text, "content": text, "link_names": False, "allowed_mentions": {"parse": []}}
        try:
            await fetch(str(url), method="POST", headers={"content-type": "application/json"},
                        body=json.dumps(payload))
        except Exception as exc:  # a failed notification must not break the chat
            print(f"webhook failed: {exc}")

    async def inbox(self, request):
        token = getattr(self.env, "ADMIN_TOKEN", None)
        if not token or request.headers.get("authorization") != f"Bearer {token}":
            return error("unauthorized", 401)
        return Response(await self._stub("__global__").read_inbox(),
                        headers={"content-type": "application/json; charset=utf-8"})
