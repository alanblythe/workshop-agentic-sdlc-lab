# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Entry point for the isolated coding environment.

Reads one job as JSON on stdin, streams NDJSON events on stdout, exits 0 even
when the coding run failed -- the failure is an event, not a crash. The parent
in ``app/coder_client.py`` is the only caller.

Keeping this a subprocess is not an aesthetic choice. ``google-antigravity``
needs protobuf >= 7.35 and ``google-cloud-aiplatform`` caps it below 7.0.0, so
the coding harness and the ADK serving surface cannot be imported into the same
interpreter. See ``coder_runtime/pyproject.toml``.
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback

import coder


def emit(kind: str, **fields: object) -> None:
    """Write one NDJSON event and flush -- the parent reads these live."""
    sys.stdout.write(json.dumps({"type": kind, **fields}, default=str) + "\n")
    sys.stdout.flush()


async def main() -> None:
    try:
        job = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        emit("error", text=f"could not parse the job on stdin: {exc}")
        return

    try:
        await coder.run(
            repo=job["repo"],
            sha=job["sha"],
            branch=job["branch"],
            budget_seconds=float(job.get("budget_seconds", 500)),
            user_id=str(job.get("user_id") or "coder-agent"),
            emit=emit,
        )
    except Exception:  # noqa: BLE001 - the traceback is the diagnostic
        emit("error", text=traceback.format_exc(limit=6))


if __name__ == "__main__":
    asyncio.run(main())
