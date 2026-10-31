"""Terminal client for the agent. Standard library only.

  python scripts/chat.py                          # local: http://localhost:8787
  python scripts/chat.py https://<worker>.workers.dev
  python scripts/chat.py URL -m "msg 1" -m "msg 2"   # scripted, prints a transcript
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid


def post(base_url, path, payload):
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode(),
        # Cloudflare's browser integrity check rejects the default Python-urllib agent (error 1010).
        headers={"content-type": "application/json", "user-agent": "emporio-agent-cli/0.1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return json.loads(body)
        except ValueError:
            return {"error": f"HTTP {exc.code}: {body[:200].decode(errors='replace')}"}


def ask(base_url, session_id, message):
    data = post(base_url, "/api/chat", {"session_id": session_id, "message": message})
    return data.get("reply") or data.get("error", "(no reply)"), data.get("trace") or []


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", nargs="?", default="http://localhost:8787")
    parser.add_argument("-m", "--message", action="append", help="send scripted messages instead of interactive mode")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    session_id = f"cli-{uuid.uuid4()}"

    if args.message:
        for message in args.message:
            reply, trace = ask(args.url, session_id, message)
            print(f"**Cliente:** {message}\n")
            if trace:
                print("> tools: " + "; ".join(f"`{t['tool']}({json.dumps(t['arguments'], ensure_ascii=False)})`" for t in trace) + "\n")
            print(f"**Lia:** {reply}\n")
        return

    print("Empório da Música (Ctrl+C para sair, /reset para nova conversa)\n")
    while True:
        try:
            message = input("você> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not message:
            continue
        if message == "/reset":
            post(args.url, "/api/reset", {"session_id": session_id})
            session_id = f"cli-{uuid.uuid4()}"
            print("(conversa reiniciada)\n")
            continue
        reply, trace = ask(args.url, session_id, message)
        if trace:
            print("  [consultou: " + ", ".join(t["tool"] for t in trace) + "]")
        print(f"lia> {reply}\n")


if __name__ == "__main__":
    main()
