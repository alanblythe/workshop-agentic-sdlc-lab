#!/usr/bin/env python3
"""Approve the commands the lab runs for itself; ask about everything else.

Reads a PreToolUse payload on stdin and prints a decision on stdout. The list
lives in allowed-commands.yaml so changing it does not mean editing code.
"""
import json
import pathlib
import sys

RULES = pathlib.Path(__file__).with_name("allowed-commands.yaml")


def allowed_prefixes():
    text = RULES.read_text()
    try:
        import yaml

        return yaml.safe_load(text).get("allow") or []
    except ImportError:
        # The file is a flat list under one key, so this subset is enough when
        # PyYAML is absent.
        return [
            line.strip()[2:].strip().strip("\"'")
            for line in text.splitlines()
            if line.strip().startswith("- ")
        ]


def main():
    # Any failure here means we could not establish that the command is on the
    # list, and the honest answer to that is to ask.
    try:
        payload = json.load(sys.stdin)
        command = payload["toolCall"]["args"]["CommandLine"].strip()
        prefixes = allowed_prefixes()
    except Exception:
        print(json.dumps({"decision": "ask"}))
        return

    for prefix in prefixes:
        if command == prefix or command.startswith(prefix + " "):
            print(json.dumps({"decision": "allow", "reason": f"{prefix} is on the lab allow-list"}))
            return

    print(json.dumps({"decision": "ask"}))


main()
