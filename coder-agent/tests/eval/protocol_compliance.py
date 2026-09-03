"""Deterministic evaluation metric for dispatch protocol compliance.

Checks whether coder-agent adheres to its contract:
- Rejects plain text and incomplete JSON payloads with the usage instructions.
- Accepts valid JSON payloads ({repo, sha, branch}) with the dispatch banner.
Score is 1 (pass) or 0 (fail).
"""

from __future__ import annotations

import json


def evaluate(instance: dict) -> dict:
    prompt = instance.get("prompt", "")
    response = instance.get("response", "")

    # Determine if prompt is valid dispatch payload
    is_valid_payload = False
    if prompt:
        try:
            parsed = json.loads(prompt.strip())
            if isinstance(parsed, dict) and {"repo", "sha", "branch"} <= parsed.keys():
                is_valid_payload = True
        except (json.JSONDecodeError, AttributeError):
            is_valid_payload = False

    if is_valid_payload:
        # Expected to acknowledge dispatching repo and branch
        if "Dispatching " in response and "onto " in response:
            return {"score": 1, "explanation": "Valid dispatch payload acknowledged correctly."}
        return {
            "score": 0,
            "explanation": f"Expected dispatch acknowledgment in response, got: {response[:120]}...",
        }
    else:
        # Expected to reject with usage instructions
        if "I could not read a dispatch payload" in response and "Send a JSON payload" in response:
            return {"score": 1, "explanation": "Invalid or incomplete payload rejected with usage instructions."}
        return {
            "score": 0,
            "explanation": f"Expected usage rejection message for non-dispatch payload, got: {response[:120]}...",
        }
