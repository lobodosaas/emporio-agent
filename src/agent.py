"""Agent loop: model decides, tools execute, repeat until a text answer.

The LLM is injected as an async callable so the loop runs the same in the
Worker (Workers AI) and in tests (a fake model).
"""

import json

from prompt import build_system_prompt, store_now
from tools import SCHEMAS, run_tool

MAX_STEPS = 5
HISTORY_LIMIT = 20  # messages kept per customer (user + assistant)
FALLBACK = (
    "Desculpe, tive um problema para concluir sua solicitação agora. "
    "Pode tentar de novo ou falar com a equipe pelo WhatsApp (67) 3341-4444?"
)


def _parse_arguments(raw):
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None


async def run_turn(llm, history, user_message, now=None):
    """Answer one customer message.

    llm(messages, tools) -> {"content": str | None, "tool_calls": [...]}
    history: previous [{"role": "user"|"assistant", "content": str}]
    Returns (reply, new_history, events, trace).
    """
    now = store_now(now)
    messages = [{"role": "system", "content": build_system_prompt(now)}, *history,
                {"role": "user", "content": user_message}]
    events, trace = [], []

    for _ in range(MAX_STEPS):
        try:
            message = await llm(messages, SCHEMAS)
        except Exception as exc:  # provider down, rate limited, bad response: answer anyway
            print(f"llm call failed: {exc}")
            reply = FALLBACK
            break
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            reply = (message.get("content") or "").strip() or FALLBACK
            break
        assistant = {"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls}
        if "_raw" in message:  # provider-native blocks (e.g. Claude thinking) to send back unchanged
            assistant["_raw"] = message["_raw"]
        messages.append(assistant)
        for call in tool_calls:
            name = call["function"]["name"]
            args = _parse_arguments(call["function"].get("arguments"))
            result, event = run_tool(name, args, today=now.date())
            trace.append({"tool": name, "arguments": args})
            if event:
                events.append(event)
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "content": json.dumps(result, ensure_ascii=False),
            })
    else:
        reply = FALLBACK

    new_history = [*history, {"role": "user", "content": user_message},
                   {"role": "assistant", "content": reply}][-HISTORY_LIMIT:]
    return reply, new_history, events, trace
