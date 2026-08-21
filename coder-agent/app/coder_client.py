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


async def stream(
    repo: str, sha: str, branch: str,
    issue: str | None = None, user_id: str = "coder-agent",
):
    """Run one coding job, yielding the child's events as they arrive.

    A generator rather than a report, because the caller turns each event into
    an ADK event: that is what puts the trajectory in Agent Platform Sessions
    instead of collapsing it into one tool result.
    """
    if not os.path.exists(RUNTIME_PYTHON):
        yield {"type": "error", "text": (
            f"the coding environment is missing at {RUNTIME_PYTHON}. The image "
            "builds it from coder_runtime/; a deploy that skipped that layer "
            "produces exactly this."
        )}
        return

    job = json.dumps({
        "repo": repo, "sha": sha, "branch": branch, "issue": issue,
        "budget_seconds": BUDGET_SECONDS, "user_id": user_id,
    }).encode()

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

    deadline = asyncio.get_running_loop().time() + KILL_AFTER
    try:
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            raw = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            if not raw:
                break
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                logger.info("coder (unparsed): %s", line)
        await proc.wait()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        yield {"type": "error", "text": (
            f"the coding run was killed at {KILL_AFTER:.0f}s. Whatever it pushed "
            "before then is on the branch."
        )}

    if proc.returncode not in (0, None):
        stderr = (await proc.stderr.read()).decode(errors="replace") if proc.stderr else ""
        yield {"type": "error",
               "text": f"the coding environment exited {proc.returncode}:\n{stderr[-1500:]}"}
