"""LLM adapters for running the agent on your own machine, with your own API key.

Same contract as the Workers AI adapter in src/entry.py:
    await llm(messages, tools) -> {"content": str | None, "tool_calls": [...], "_raw"?: ...}
`messages` and `tools` use the OpenAI chat format that src/agent.py speaks.

- OpenAI, OpenRouter, Groq and DeepSeek expose an OpenAI-compatible chat API,
  so one adapter (standard library HTTP) covers them.
- Claude goes through the official Anthropic SDK (`uv sync --group local`).
"""

import asyncio
import json
import os
import urllib.error
import urllib.request

PROVIDERS = {
    # name: base URL, env var with the key, default model (override with LLM_MODEL)
    "anthropic": {"key_env": "ANTHROPIC_API_KEY", "model": "claude-opus-5-5"},
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY", "model": "gpt-6-luna"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY", "model": "openai/gpt-6-luna"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY", "model": "openai/gpt-oss-20b"},
    # DeepSeek's tool-calling guide runs with thinking disabled.
    "deepseek": {"base_url": "https://api.deepseek.com", "key_env": "DEEPSEEK_API_KEY", "model": "deepseek-flash",
                 "extra": {"thinking": {"type": "disabled"}}},
}

REFUSAL_REPLY = (
    "Desculpe, não consigo ajudar com isso por aqui. "
    "Se precisar, fale com a equipe pelo WhatsApp (67) 3341-4444."
)


def public_messages(messages):
    """Drop adapter-private keys (like "_raw") before sending to an OpenAI-style API."""
    return [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]


class OpenAICompatible:
    def __init__(self, base_url, api_key, model, extra=None):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.extra = extra or {}

    def _post(self, body):
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode(),
            headers={
                "authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
                "user-agent": "emporio-agent/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"LLM HTTP {exc.code}: {exc.read()[:300].decode(errors='replace')}") from exc

    async def __call__(self, messages, tools):
        body = {"model": self.model, "messages": public_messages(messages), "tools": tools, **self.extra}
        data = await asyncio.to_thread(self._post, body)
        message = data["choices"][0]["message"]
        return {"content": message.get("content"), "tool_calls": message.get("tool_calls") or []}


class Claude:
    # Models that accept server-side refusal fallbacks ("default" routing).
    FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}

    def __init__(self, api_key, model, client=None):
        if client is None:
            from anthropic import AsyncAnthropic  # optional dependency: uv sync --group local
            client = AsyncAnthropic(api_key=api_key)
        self.client = client
        self.model = model

    @staticmethod
    def convert(messages):
        """OpenAI-style history -> (system, Claude messages).

        Tool results that follow one assistant turn go back in a single user
        message, as the Messages API expects for parallel tool calls.
        """
        system, out = [], []
        for m in messages:
            role = m["role"]
            if role == "system":
                system.append(m["content"])
            elif role == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                last = out[-1] if out else None
                if last and last["role"] == "user" and isinstance(last["content"], list) \
                        and last["content"] and last["content"][0].get("type") == "tool_result":
                    last["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
            elif role == "assistant":
                out.append({"role": "assistant", "content": m.get("_raw") or m.get("content") or ""})
            else:
                out.append({"role": "user", "content": m["content"]})
        return "\n\n".join(system), out

    @staticmethod
    def convert_tools(tools):
        return [
            {"name": t["function"]["name"], "description": t["function"]["description"],
             "input_schema": t["function"]["parameters"]}
            for t in tools
        ]

    async def __call__(self, messages, tools):
        system, converted = self.convert(messages)
        kwargs = {
            "model": self.model,
            "max_tokens": 16000,
            "system": system,
            "messages": converted,
            "tools": self.convert_tools(tools),
        }
        if self.model in self.FALLBACK_MODELS:
            # If a safety classifier declines, the API re-runs the request on a fallback model.
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        response = await self.client.beta.messages.create(**kwargs)
        if response.stop_reason == "refusal":
            return {"content": REFUSAL_REPLY, "tool_calls": []}
        text = "".join(b.text for b in response.content if b.type == "text")
        calls = [
            {"id": b.id, "type": "function", "function": {"name": b.name, "arguments": json.dumps(b.input)}}
            for b in response.content if b.type == "tool_use"
        ]
        # Full content (thinking blocks included) goes back unchanged on the next loop step.
        return {"content": text, "tool_calls": calls, "_raw": response.content}


def from_env(environ=os.environ):
    """Pick the provider from LLM_PROVIDER, or the first API key found in the environment."""
    name = environ.get("LLM_PROVIDER")
    if not name:
        name = next((n for n, p in PROVIDERS.items() if environ.get(p["key_env"])), None)
    if name not in PROVIDERS:
        keys = ", ".join(p["key_env"] for p in PROVIDERS.values())
        raise SystemExit(f"No LLM configured. Set one of: {keys} (or LLM_PROVIDER). See .env.example.")
    preset = PROVIDERS[name]
    api_key = environ.get(preset["key_env"])
    if not api_key:
        raise SystemExit(f"LLM_PROVIDER={name} needs {preset['key_env']}.")
    model = environ.get("LLM_MODEL") or preset["model"]
    if name == "anthropic":
        return name, model, Claude(api_key, model)
    base_url = environ.get("LLM_BASE_URL") or preset["base_url"]
    return name, model, OpenAICompatible(base_url, api_key, model, preset.get("extra"))
