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

"""The coding loop: an Antigravity SDK agent, run as an ADK agent.

Agent Platform is where an agent lives; the SDK is what an agent can do.
``AntigravityAgent`` is the seam between them -- it wraps a
``google.antigravity.Agent`` as a native ADK ``BaseAgent`` and turns the SDK's
trajectory into ADK events, which the session service then persists. So the
reasoning is recorded by the platform rather than by a string this module
assembles.

Three measured facts shape what follows, and none is guessable:

1. ``LocalAgentConfig``'s default policy is ``confirm_run_command``, and with no
   handler it **denies ``run_command`` outright**. Unattended that means the
   agent cannot run the tests -- and it will report them as passing anyway.
   ``allow_all()`` is required, not a convenience.
2. ``workspace_only()`` restricts the **file tools only** -- its own docstring
   says "Other tools are unaffected". Measured: refused ``write_to_file``
   outside the tree, then wrote the same path through the shell. It is a
   guardrail against a stray edit, not a sandbox. The disposable container is
   the boundary.
3. ``AntigravityAgent`` is **root-only**, requires ``save_dir``, and its resume
   does not work against SDK 0.1.13 -- an ADK-side bug, not an SDK one. The
   SDK persists a conversation to ``<conversation_id>.db`` and resumes it
   correctly when the id is passed back with ``CREATE_OR_RESUME`` (verified
   directly: it recalled a word across two ``Agent`` instances). ADK's
   ``_trajectory_files`` looks for ``traj-<conversation_id>`` instead, which the
   harness never writes, so ``has_trajectory()`` is always False,
   ``rename_trajectory()`` is a no-op, and each turn starts a fresh
   conversation beside an orphaned ``traj-<sha256>.resume`` sidecar.

Resuming for real would mean driving the SDK directly and remembering the
harness's conversation id -- and it would still only work while the same
instance serves the next dispatch, since the ``.db`` is on the container's
local disk. **The branch is the durable record**, which is why the agent is
told to push after every iteration rather than at the end.
"""

from __future__ import annotations

import os
import time

import workspace

MODEL = os.environ.get("CODER_MODEL", "gemini-3.6-flash")
# The whole Gemini 3 family answers only from `global`; a regional endpoint
# returns a 404 that names the model and reads like a typo.
MODEL_LOCATION = os.environ.get("MODEL_LOCATION", "global")

APP_NAME = "coder"
AGENT_NAME = "coder"
# Outside the workspace root on purpose: start_work wipes that directory, and
# this is where the resumable trajectory lives.
SAVE_DIR = "/tmp/agentic-sdlc-trajectories"

TASK = """\
You are finishing an implementation in this repository, against a contract you \
did not write and may not change.

1. Read `docs/spec.md`. It is the specification, and it has already been \
   argued over -- treat it as settled.
2. Read the contract tests (`tests/`, especially any `test_*_contract.py`). \
   They encode the spec's resolved ambiguities. **Do not edit any test file.**
3. Write the implementation until the tests pass. Run `python -m pytest -q` \
   yourself after every change; do not assume a change worked.
4. Call `commit_and_push` after every iteration that changes a file, with a \
   message a reviewer could follow. The branch is the only durable record of \
   this run -- if you are cut off, whatever you last pushed is all that survives.
5. Call `time_remaining` when you are unsure how much room is left. When it is \
   nearly gone, push and report honestly where you got to. A truthful partial \
   result is worth more than a claim of success.

Never report tests as passing unless you ran them and saw them pass.
"""

# The issue is the team's record of this work, so the commits reference it and
# merging the branch closes it. Every commit carries the trailer rather than
# only the last: the invocation is capped, so any push could be the final one,
# and a repeated Closes line costs nothing.
ISSUE_RULE = """\
This work is tracked by issue #{issue}. End every commit message with a line \
reading `Closes #{issue}`.
"""


# pytest output and file contents both arrive here, and the pipe to the parent
# is not the place to move a megabyte.
MAX_FIELD = 4000


def _trim(value):
    if isinstance(value, dict):
        return {k: _trim(v) for k, v in value.items()}
    text = value if isinstance(value, str) else str(value)
    if len(text) <= MAX_FIELD:
        return value
    return text[:MAX_FIELD] + f"\n...(trimmed {len(text) - MAX_FIELD} chars)"


def _session_service(emit):
    """The coding run's sessions are in-memory, and that is forced.

    Agent Platform Sessions is reachable only through
    ``VertexAiSessionService``, whose ``__init__`` does ``import vertexai`` --
    that is ``google-cloud-aiplatform``, which caps protobuf below 7.0.0 and so
    cannot exist in this environment. The import is inside the constructor, not
    at the top of the module, so it does not show up in the module's imports
    and fails only when the service is built.

    Durability is not lost, it just lives elsewhere: the branch holds the code,
    and the parent -- which does have aiplatform -- is itself an ADK agent in an
    Agent Platform Session, so the report of this run is persisted there as its
    tool result. What the in-memory service costs is per-step events in that
    session, and cross-instance replay of the SDK trajectory.
    """
    from google.adk.sessions.in_memory_session_service import InMemorySessionService

    return InMemorySessionService(), False


async def run(
    repo: str,
    sha: str,
    branch: str,
    issue: str | None = None,
    budget_seconds: float = 500.0,
    user_id: str = "coder-agent",
    emit=lambda event_type, **f: None,
) -> None:
    """Prepare the workspace and run the coding agent over it.

    Streams progress through ``emit`` rather than returning it, so a run cut off
    at the invocation cap has still reported everything up to that point.
    """
    workspace.set_budget(budget_seconds)
    tree, note = await workspace.prepare(repo, sha, branch)
    if tree is None:
        emit("error", text=note)
        return
    emit("note", text=note)

    from google.adk.apps import App
    from google.adk.labs.antigravity import AntigravityAgent
    from google.adk.runners import Runner
    from google.antigravity import CapabilitiesConfig, LocalAgentConfig
    from google.antigravity.hooks import policy
    from google.genai import types

    os.makedirs(SAVE_DIR, exist_ok=True)

    config = LocalAgentConfig(
        workspaces=[tree],
        capabilities=CapabilitiesConfig(),
        policies=[policy.allow_all(), *policy.workspace_only([tree])],
        tools=[workspace.commit_and_push, workspace.time_remaining],
        vertex=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=MODEL_LOCATION,
        model=MODEL,
        save_dir=SAVE_DIR,
        system_instructions=(
            "You are a careful engineer working alone against a deadline. You "
            "verify by running things, never by reasoning about what would "
            "happen. You push your work as you go."
        ),
    )

    service, durable = _session_service(emit)
    runner = Runner(
        app=App(root_agent=AntigravityAgent(name=AGENT_NAME, config=config), name=APP_NAME),
        session_service=service,
    )

    # One session per repository and branch, named rather than generated, so a
    # second dispatch of the same work continues the same conversation instead
    # of opening a new one beside it.
    session_id = f"coder-{workspace.slug(repo, branch)}"
    session = await service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    resumed = session is not None
    if session is None:
        session = await service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
    # Reported rather than assumed: with SDK 0.1.13 this is always a fresh
    # conversation (see the module docstring), and a claim of resumption that
    # never happens is worse than no claim.
    replayed = os.path.exists(os.path.join(SAVE_DIR, f"traj-{session_id}_{AGENT_NAME}"))
    emit(
        "note",
        text=(
            f"session {session_id} ({'resumed' if resumed else 'new'}); "
            f"SDK conversation {'replayed' if replayed else 'fresh'}"
        ),
    )

    task = TASK + ("\n" + ISSUE_RULE.format(issue=issue) if issue else "")

    started = time.monotonic()
    calls = 0
    final = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=task)]),
    ):
        # Each part is relayed as its own step so the parent can rebuild it as
        # an ADK event. Collapsing them into a summary here is what would make
        # the trajectory unviewable in Agent Platform.
        for part in (event.content.parts if event.content and event.content.parts else []):
            at = round(time.monotonic() - started, 1)
            if getattr(part, "function_call", None):
                calls += 1
                emit("step", kind="function_call", at=at,
                     name=part.function_call.name,
                     args=_trim(dict(part.function_call.args or {})))
            elif getattr(part, "function_response", None):
                emit("step", kind="function_response", at=at,
                     name=part.function_response.name,
                     response=_trim(part.function_response.response))
            elif getattr(part, "text", None):
                final = part.text
                emit("step", kind="text", at=at, text=part.text)

    # What the model says it did and what is on the branch are two different
    # claims. It is told when a push is rejected and can carry on regardless, so
    # the last word belongs to the remote.
    unlanded = await workspace.verify_pushed()
    if unlanded:
        emit("error", text=f"THE WORK DID NOT LAND: {unlanded}")

    emit(
        "final",
        text=final,
        tool_calls=calls,
        elapsed=round(time.monotonic() - started, 1),
        budget_left=round(workspace.seconds_left()),
        session_id=session_id,
        durable_session=durable,
    )
