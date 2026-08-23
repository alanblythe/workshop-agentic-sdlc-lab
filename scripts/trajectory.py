#!/usr/bin/env python3
"""Render an agent's event stream as one line per action.

Reads the newline-delimited JSON that async_stream_query writes, and prints
what the agent said and what it called. Anything it cannot parse it drops:
the branch is the record, and a renderer must never take the follow loop
down with it.
"""

import json
import sys

VERBS = {
    "view_file": "read",
    "find_file": "find",
    "list_directory": "list",
    "run_command": "run",
    "edit_file": "edit",
    "commit_and_push": "push",
    "time_remaining": "clock",
}

WIDTH = 88


def detail(name, args):
    if name == "run_command":
        return args.get("command_line", "")
    if name in ("view_file", "edit_file"):
        return args.get("file_path", "").split("/repo/")[-1]
    if name == "find_file":
        return args.get("query", "")
    if name == "list_directory":
        return args.get("directory_path", "").split("/repo")[-1] or "/"
    if name == "commit_and_push":
        return args.get("message", "").split("\n")[0]
    if name == "time_remaining":
        return ""
    return json.dumps(args)


def clip(text):
    text = " ".join(text.split())
    return text if len(text) <= WIDTH else text[: WIDTH - 1] + "…"


def main():
    tty = sys.stdout.isatty()
    dim = "\033[2m" if tty else ""
    off = "\033[0m" if tty else ""

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            parts = (event.get("content") or {}).get("parts") or []
        except Exception:
            continue

        for part in parts:
            if "text" in part:
                print(f"  {dim}~     {clip(part['text'])}{off}")
            call = part.get("function_call")
            if call:
                name = call.get("name", "?")
                verb = VERBS.get(name, name)
                print(f"  {dim}>{off} {verb:<5} {clip(detail(name, call.get('args') or {}))}")
            response = part.get("function_response")
            # Only the edits: their summary says what changed, which the call
            # -- a bare path -- does not.
            if response and response.get("name") == "edit_file":
                said = (response.get("response") or {}).get("result", "")
                if said:
                    print(f"  {dim}        {clip(said)}{off}")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
