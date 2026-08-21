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

"""Drives the coding run, which lives in its own interpreter.

Agent Platform is where an agent lives; the SDK is what an agent can do -- and
here they are literally two processes. ``google-antigravity`` needs
protobuf >= 7.35 at runtime while ``google-cloud-aiplatform`` -- which serves
the reasoning-engine routes ``:streamQuery`` dispatches to -- caps protobuf
below 7.0.0. They cannot be imported into one interpreter, so the coding
harness gets its own venv at ``/opt/antigravity`` and this module talks to it
over a pipe.

The child streams NDJSON so a run that is cut off at the 600s cap has still
reported everything up to that point.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)

RUNTIME_DIR = os.environ.get("CODER_RUNTIME_DIR", "/opt/antigravity")
RUNTIME_PYTHON = os.path.join(RUNTIME_DIR, ".venv", "bin", "python")
RUNTIME_ENTRY = os.path.join(RUNTIME_DIR, "run.py")

# The invocation cap is ~600s and hard. The child gets less than that so its
# final push lands on the right side of the deadline, and this process keeps a
# little more so it can still report when the child is killed.
BUDGET_SECONDS = float(os.environ.get("INVOCATION_BUDGET_SECONDS", "500"))
KILL_AFTER = BUDGET_SECONDS + 30


def _child_env() -> dict[str, str]:
    """The parent's environment minus anything that would point the child back
    at the ADK venv. ``uv run`` and the venv activation both export these, and
    an inherited ``PYTHONPATH`` is enough to make the child import protobuf 6
    and die at ``localharness_pb2``."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT")}
    env["PYTHONUNBUFFERED"] = "1"
    return env


async def run(repo: str, sha: str, branch: str) -> str:
    """Run one coding job and return a report of what happened."""
    if not os.path.exists(RUNTIME_PYTHON):
        return (
            f"the coding environment is missing at {RUNTIME_PYTHON}. The image "
            "builds it from coder_runtime/; a deploy that skipped that layer "
            "produces exactly this."
        )

    job = json.dumps(
        {"repo": repo, "sha": sha, "branch": branch, "budget_seconds": BUDGET_SECONDS}
    ).encode()

    proc = await asyncio.create_subprocess_exec(
        RUNTIME_PYTHON, RUNTIME_ENTRY,
        cwd=RUNTIME_DIR,
        env=_child_env(),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(job)
    await proc.stdin.drain()
    proc.stdin.close()

    notes: list[str] = []
    tools: list[str] = []
    final = ""
    errors: list[str] = []

    async def read_events() -> None:
        nonlocal final
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.info("coder (unparsed): %s", line)
                continue
            kind = event.get("type")
            if kind == "tool":
                tools.append(f"[{event.get('at', 0):>6}s] {event.get('name')}")
                logger.info("coder tool: %s", event.get("name"))
            elif kind == "note":
                notes.append(str(event.get("text", "")))
            elif kind == "final":
                final = str(event.get("text", ""))
                notes.append(
                    f"{event.get('tool_calls')} tool calls in "
                    f"{event.get('elapsed')}s, {event.get('budget_left')}s of budget left"
                )
            elif kind == "error":
                errors.append(str(event.get("text", "")))

    try:
        await asyncio.wait_for(read_events(), timeout=KILL_AFTER)
        await proc.wait()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        errors.append(
            f"the coding run was killed at {KILL_AFTER:.0f}s. Whatever it pushed "
            "before then is on the branch -- that is the point of pushing every "
            "iteration."
        )

    stderr = (await proc.stderr.read()).decode(errors="replace") if proc.stderr else ""
    if proc.returncode not in (0, None) and stderr:
        errors.append(f"the coding environment exited {proc.returncode}:\n{stderr[-1500:]}")

    parts = ["\n".join(notes) or "(no progress reported)"]
    parts.append("--- trajectory ---\n" + ("\n".join(tools[-40:]) or "(no tool calls)"))
    if final:
        parts.append("--- the coder's own account ---\n" + final)
    if errors:
        parts.append("--- errors ---\n" + "\n\n".join(errors))
    return "\n\n".join(parts)
