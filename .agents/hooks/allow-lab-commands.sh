#!/usr/bin/env bash
#
# Approves the few commands this lab's agents run for themselves, so a
# subagent writing tests does not stop the room for each one. Everything else
# falls through to the normal prompt: the list is what the lab needs, not a
# blanket yes.
#
# stdin is the PreToolUse payload; stdout is the decision.
set -euo pipefail

cmd=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("toolCall",{}).get("args",{}).get("CommandLine",""))' 2>/dev/null || true)

case "$cmd" in
  pytest*|uv\ run\ pytest*|git\ status*|git\ diff*|ls*)
    printf '{"decision":"allow","reason":"on the lab allow-list"}\n' ;;
  *)
    printf '{"decision":"ask"}\n' ;;
esac
