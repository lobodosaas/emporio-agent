import asyncio
import json
from datetime import datetime, timezone

from agent import FALLBACK, HISTORY_LIMIT, MAX_STEPS, run_turn
from prompt import build_system_prompt, is_open, store_now

# 2026-11-02 is a Monday. 14:00 UTC = 10:00 in Campo Grande.
MONDAY_10AM = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)
SUNDAY_10AM = datetime(2026, 11, 1, 14, 0, tzinfo=timezone.utc)


def scripted_llm(*responses):
    """Fake model that returns the given messages in order and records calls."""
    calls = []
    queue = list(responses)

    async def llm(messages, tools):
        calls.append([dict(m) for m in messages])
        return queue.pop(0)

    llm.calls = calls
    return llm


def tool_call(name, args, call_id="c1"):
    return {"content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def test_store_hours():
    assert is_open(store_now(MONDAY_10AM))
    assert not is_open(store_now(SUNDAY_10AM))
    assert "ABERTA" in build_system_prompt(MONDAY_10AM)
    assert "FECHADA" in build_system_prompt(SUNDAY_10AM)


def test_tool_result_is_fed_back_and_final_text_returned():
    llm = scripted_llm(tool_call("search_products", {"query": "Takamine GD20"}),
                       {"content": "O Takamine GD20 custa R$ 2.199,00."})
    reply, history, events, trace = asyncio.run(run_turn(llm, [], "quanto custa o takamine gd20?", MONDAY_10AM))
    assert reply == "O Takamine GD20 custa R$ 2.199,00."
    assert trace == [{"tool": "search_products", "arguments": {"query": "Takamine GD20"}}]
    tool_msg = llm.calls[1][-1]
    assert tool_msg["role"] == "tool" and "2199" in tool_msg["content"]
    assert history[-2:] == [{"role": "user", "content": "quanto custa o takamine gd20?"},
                            {"role": "assistant", "content": reply}]
    assert events == []


def test_side_effect_events_are_collected():
    llm = scripted_llm(tool_call("handoff_to_human", {"reason": "complaint", "summary": "violão chegou trincado"}),
                       {"content": "Encaminhei para a equipe."})
    _, _, events, _ = asyncio.run(run_turn(llm, [], "meu violão chegou trincado", MONDAY_10AM))
    assert events[0]["type"] == "handoff"


def test_loop_stops_after_max_steps():
    llm = scripted_llm(*[tool_call("get_store_policy", {"topic": "payment"})] * MAX_STEPS)
    reply, _, _, trace = asyncio.run(run_turn(llm, [], "?", MONDAY_10AM))
    assert reply == FALLBACK
    assert len(trace) == MAX_STEPS


def test_malformed_arguments_do_not_crash():
    bad = {"content": None, "tool_calls": [
        {"id": "x", "type": "function", "function": {"name": "search_products", "arguments": "{not json"}}]}
    llm = scripted_llm(bad, {"content": "ok"})
    reply, _, _, _ = asyncio.run(run_turn(llm, [], "?", MONDAY_10AM))
    assert reply == "ok"
    assert "error" in llm.calls[1][-1]["content"]


def test_llm_failure_returns_fallback_instead_of_crashing():
    async def broken_llm(messages, tools):
        raise RuntimeError("AiError: 3021: rate limiting")

    reply, history, _, _ = asyncio.run(run_turn(broken_llm, [], "oi", MONDAY_10AM))
    assert reply == FALLBACK
    assert history[-1] == {"role": "assistant", "content": FALLBACK}


def test_history_is_capped():
    history = [{"role": "user", "content": str(i)} for i in range(HISTORY_LIMIT)]
    llm = scripted_llm({"content": "oi"})
    _, new_history, _, _ = asyncio.run(run_turn(llm, history, "olá", MONDAY_10AM))
    assert len(new_history) == HISTORY_LIMIT
    assert new_history[-1] == {"role": "assistant", "content": "oi"}
