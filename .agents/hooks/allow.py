#!/usr/bin/env python3
"""Approve what the lab does for itself; ask about everything else.

Reads a PreToolUse payload on stdin and prints a decision on stdout. The lists
live in allowed.yaml so changing them does not mean editing code.

The tool's arguments differ per tool -- run_command carries CommandLine and
write_to_file carries TargetFile -- so each is read by name.
"""
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
RULES = HERE / "allowed.yaml"
# .agents/hooks/allow.py, so the repository is two directories up. Derived from
# this file rather than from the working directory, which is not the clone.
REPO = HERE.parent.parent


def rules():
    text = RULES.read_text()
    try:
        import yaml

        loaded = yaml.safe_load(text) or {}
    except ImportError:
        # Flat lists under one key each, so this subset is enough without PyYAML.
        loaded, key = {}, None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.endswith(":") and not stripped.startswith("#"):
                key = stripped[:-1]
                loaded[key] = []
            elif stripped.startswith("- ") and key:
                loaded[key].append(stripped[2:].strip().strip("\"'"))
    return loaded.get("commands") or [], loaded.get("writes") or []


def verdict(tool, args, commands, writes):
    if tool == "run_command":
        command = (args.get("CommandLine") or "").strip()
        for prefix in commands:
            if command == prefix or command.startswith(prefix + " "):
                return prefix
        return None

    if tool == "write_to_file":
        # The path arrives as the agent wrote it, which may start with ~ or a
        # variable. resolve() does not expand either -- it would take ~ for a
        # directory of that name -- so both are expanded first.
        raw = os.path.expandvars(os.path.expanduser((args.get("TargetFile") or "").strip()))
        target = pathlib.Path(raw).resolve()
        for directory in writes:
            allowed = (REPO / directory).resolve()
            if allowed == target or allowed in target.parents:
                return str(directory)
        return None

    return None


def main():
    # Any failure means the call could not be shown to be on a list, and the
    # honest answer to that is to ask.
    try:
        payload = json.load(sys.stdin)
        call = payload["toolCall"]
        matched = verdict(call["name"], call.get("args") or {}, *rules())
    except Exception:
        print(json.dumps({"decision": "ask"}))
        return

    if matched:
        print(json.dumps({"decision": "allow", "reason": f"{matched} is on the lab allow-list"}))
    else:
        # The reason is shown with the prompt, so say which list was consulted
        # and what was compared. A hook that only ever says ask is otherwise
        # indistinguishable from one that is not running.
        print(json.dumps({"decision": "ask", "reason": f"not on the lab allow-list in {RULES}"}))


main()
