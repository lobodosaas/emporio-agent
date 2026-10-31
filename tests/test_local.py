import asyncio
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from local.llm import Claude, OpenAICompatible, from_env
from local.server import Store, make_handler

TOOLS = [{"type": "function", "function": {
    "name": "get_store_policy", "description": "Read a policy",
    "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}}}}]


def test_provider_picked_from_first_key_and_overrides():
    name, model, llm = from_env({"GROQ_API_KEY": "g"})
    assert (name, model) == ("groq", "openai/gpt-oss-20b")
    assert llm.url == "https://api.groq.com/openai/v1/chat/completions"
    name, model, llm = from_env({"OPENAI_API_KEY": "o", "LLM_MODEL": "x", "LLM_BASE_URL": "https://proxy.test/v1"})
    assert (name, model, llm.url) == ("openai", "x", "https://proxy.test/v1/chat/completions")
    with pytest.raises(SystemExit):
        from_env({})
    with pytest.raises(SystemExit):
        from_env({"LLM_PROVIDER": "deepseek"})  # provider chosen but its key missing


def test_openai_compatible_strips_private_keys_and_adds_provider_extras():
    llm = OpenAICompatible("https://api.deepseek.com", "k", "deepseek-flash", {"thinking": {"type": "disabled"}})
    sent = {}

    def fake_post(body):
        sent.update(body)
        return {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "1", "type": "function", "function": {"name": "get_store_policy", "arguments": "{}"}}]}}]}

    llm._post = fake_post
    history = [{"role": "assistant", "content": "x", "_raw": object()}]
    out = asyncio.run(llm(history, TOOLS))
    assert "_raw" not in sent["messages"][0]
    assert sent["thinking"] == {"type": "disabled"}
    assert out["tool_calls"][0]["function"]["name"] == "get_store_policy"


def test_claude_conversion_groups_tool_results_and_keeps_raw_blocks():
    raw = [{"type": "thinking", "thinking": "", "signature": "s"}, {"type": "tool_use", "id": "a"}]
    system, messages = Claude.convert([
        {"role": "system", "content": "persona"},
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "", "tool_calls": [], "_raw": raw},
        {"role": "tool", "tool_call_id": "a", "content": "{}"},
        {"role": "tool", "tool_call_id": "b", "content": "{}"},
    ])
    assert system == "persona"
    assert messages[1] == {"role": "assistant", "content": raw}
    assert [b["tool_use_id"] for b in messages[2]["content"]] == ["a", "b"]
    assert Claude.convert_tools(TOOLS)[0]["input_schema"]["type"] == "object"


class FakeAnthropic:
    def __init__(self, response):
        self.calls = []

        async def create(**kwargs):
            self.calls.append(kwargs)
            return response

        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create))


def test_claude_call_maps_tool_use_and_enables_fallbacks():
    blocks = [SimpleNamespace(type="text", text="vou ver"),
              SimpleNamespace(type="tool_use", id="t1", name="get_store_policy", input={"topic": "payment"})]
    client = FakeAnthropic(SimpleNamespace(stop_reason="tool_use", content=blocks))
    out = asyncio.run(Claude("k", "claude-opus-5-5", client=client)([{"role": "user", "content": "oi"}], TOOLS))
    assert out["tool_calls"][0]["function"] == {"name": "get_store_policy", "arguments": '{"topic": "payment"}'}
    assert out["_raw"] is blocks
    assert client.calls[0]["fallbacks"] == "default"

    other = FakeAnthropic(SimpleNamespace(stop_reason="end_turn", content=[]))
    asyncio.run(Claude("k", "claude-haiku-5-5", client=other)([{"role": "user", "content": "oi"}], TOOLS))
    assert "fallbacks" not in other.calls[0]


def test_claude_refusal_becomes_polite_reply():
    client = FakeAnthropic(SimpleNamespace(stop_reason="refusal", content=[]))
    out = asyncio.run(Claude("k", "claude-opus-5-5", client=client)([{"role": "user", "content": "x"}], TOOLS))
    assert "WhatsApp" in out["content"] and out["tool_calls"] == []


@pytest.fixture
def local_server(tmp_path):
    async def fake_llm(messages, tools):
        return {"content": f"eco: {messages[-1]['content']}", "tool_calls": []}

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Store(tmp_path / "t.db"), fake_llm))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def call(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_local_server_chat_memory_and_pages(local_server):
    sid = {"session_id": "test-local-123"}
    status, body = call(local_server, "/api/chat", {**sid, "message": "oi"})
    assert status == 200 and json.loads(body)["reply"] == "eco: oi"
    history = json.loads(call(local_server, "/api/history", sid)[1])
    assert [m["role"] for m in history] == ["user", "assistant"]
    call(local_server, "/api/reset", sid)
    assert json.loads(call(local_server, "/api/history", sid)[1]) == []

    assert call(local_server, "/api/chat", {"session_id": "bad id", "message": "oi"})[0] == 400
    assert call(local_server, "/api/chat", {**sid, "message": "a" * 501})[0] == 413
    status, page = call(local_server, "/politicas")
    assert status == 200 and b"<title>" in page
    assert call(local_server, "/../pyproject.toml")[0] == 404
    assert len(json.loads(call(local_server, "/api/home")[1])["featured"]) > 0
