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

"""The coding loop, run by the Antigravity SDK.

Agent Platform is where an agent lives; the SDK is what an agent can do. The
ADK agent in ``agent.py`` is the deployed surface -- it is what Agent Runtime
knows how to invoke. The actual read-edit-run-test loop is the SDK's, whose
built-in tools (``VIEW_FILE``, ``EDIT_FILE``, ``CREATE_FILE``, ``RUN_COMMAND``,
``LIST_DIR``) are the coding harness this agent would otherwise hand-roll.

Two measured facts shape the configuration below, and neither is guessable:

1. ``LocalAgentConfig``'s default policy is ``confirm_run_command``, and with
   no handler it **denies ``run_command`` outright**. Unattended, that turns
   every test run into a denial -- and a model that cannot run the tests will
   still cheerfully report that they pass. ``allow_all()`` is therefore
   mandatory here, not a convenience.
2. ``workspace_only()`` restricts the **file tools only** -- its own docstring
   says "Other tools are unaffected". Measured: with ``run_command`` allowed,
   the agent was refused ``write_to_file`` outside the tree and then wrote the
   same path through the shell instead. It is a guardrail against a stray edit,
   **not** a sandbox. The disposable container is the only real boundary, and
   neither 0.1.12 nor 0.1.13 offers a way to confine ``run_command`` to a path.
"""

from __future__ import annotations

import os
import time

import workspace

MODEL = os.environ.get("CODER_MODEL", "gemini-3.6-flash")
# The whole Gemini 3 family answers only from `global`; a regional endpoint
# returns a 404 that names the model and reads like a typo.
MODEL_LOCATION = os.environ.get("MODEL_LOCATION", "global")

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


async def run(
    repo: str,
    sha: str,
    branch: str,
    budget_seconds: float = 540.0,
    emit=lambda kind, **f: None,
) -> None:
    """Prepare the workspace and hand it to the Antigravity coding agent.

    Streams progress through ``emit`` rather than returning it: the parent
    relays events as they happen, and a run that is cut off mid-flight has
    still reported everything up to that point.
    """
    workspace.set_budget(budget_seconds)
    tree, note = await workspace.prepare(repo, sha, branch)
    if tree is None:
        emit("error", text=note)
        return
    emit("note", text=note)

    from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
    from google.antigravity.hooks import policy

    config = LocalAgentConfig(
        workspaces=[tree],
        capabilities=CapabilitiesConfig(),
        # Without allow_all the agent cannot run the tests at all. workspace_only
        # keeps the file tools pointed at the checkout; it does not fence the
        # shell, so the container is what actually bounds this agent.
        policies=[policy.allow_all(), *policy.workspace_only([tree])],
        tools=[workspace.commit_and_push, workspace.time_remaining],
        vertex=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=MODEL_LOCATION,
        model=MODEL,
        system_instructions=(
            "You are a careful engineer working alone against a deadline. You "
            "verify by running things, never by reasoning about what would "
            "happen. You push your work as you go."
        ),
    )

    started = time.monotonic()
    calls = 0
    async with Agent(config) as agent:
        response = await agent.chat(TASK)
        async for call in response.tool_calls:
            calls += 1
            emit("tool", name=call.name, at=round(time.monotonic() - started, 1))
        final = await response.text()

    emit(
        "final",
        text=final,
        tool_calls=calls,
        elapsed=round(time.monotonic() - started, 1),
        budget_left=round(workspace.seconds_left()),
    )
