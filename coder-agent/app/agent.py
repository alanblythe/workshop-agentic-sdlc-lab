# ruff: noqa
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

"""The deployed agent: a coding run whose trajectory lives in the session.

This is a custom ``BaseAgent`` rather than an LLM agent with a tool, and the
difference is the whole point. A tool call collapses an entire coding run into
one ``function_response`` -- durable, but a blob. Yielding an ADK event per step
is what makes the trajectory something Agent Platform can render: the Runner
persists each event to Agent Platform Sessions as it arrives.

The coding harness itself runs in a second interpreter (see
``app/coder_client.py``), so the events are rebuilt here from what that process
reports rather than produced in-process the way ``AntigravityAgent`` does it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.apps import App
from google.adk.events.event import Event
from google.genai import types

from app import coder_client

logger = logging.getLogger(__name__)

USAGE = (
    'Send a JSON payload naming the work, for example:\n'
    '  {"repo": "you/your-fork", "sha": "<commit>", "branch": "agent/parse",\n'
    '   "issue": "1"}\n'
    'The sha is pinned deliberately: nothing committed after dispatch is visible.'
)


def _payload(ctx: InvocationContext) -> dict | None:
    """The dispatch payload, or None if the message was not one."""
    for part in (ctx.user_content.parts if ctx.user_content and ctx.user_content.parts else []):
        if not part.text:
            continue
        try:
            parsed = json.loads(part.text.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and {"repo", "sha", "branch"} <= parsed.keys():
            return parsed
    return None


class CoderAgent(BaseAgent):
    """Runs one coding job, reporting every step as an event in the session."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        def say(text: str) -> Event:
            return Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(role="model", parts=[types.Part(text=text)]),
            )

        job = _payload(ctx)
        if job is None:
            yield say(f"I could not read a dispatch payload.\n\n{USAGE}")
            return

        user_id = getattr(ctx.session, "user_id", None) or "coder-agent"
        yield say(
            f"Dispatching {job['repo']} at {job['sha'][:12]} onto {job['branch']}."
        )

        async for event in coder_client.stream(
            repo=job["repo"], sha=job["sha"], branch=job["branch"],
            issue=job.get("issue"), user_id=user_id,
        ):
            kind = event.get("type")
            if kind == "step":
                part = _part_for(event)
                if part is not None:
                    yield Event(
                        invocation_id=ctx.invocation_id,
                        author=self.name,
                        content=types.Content(role="model", parts=[part]),
                    )
            elif kind in ("note", "error"):
                yield say(event.get("text", ""))
            elif kind == "final":
                yield say(
                    f"{event.get('tool_calls')} tool calls in {event.get('elapsed')}s, "
                    f"{event.get('budget_left')}s of budget left."
                )


def _part_for(event: dict) -> types.Part | None:
    """Rebuild one relayed step as the ADK part it was on the other side."""
    kind = event.get("kind")
    if kind == "function_call":
        return types.Part(
            function_call=types.FunctionCall(
                name=event.get("name") or "unknown", args=event.get("args") or {}
            )
        )
    if kind == "function_response":
        response = event.get("response")
        return types.Part(
            function_response=types.FunctionResponse(
                name=event.get("name") or "unknown",
                response=response if isinstance(response, dict) else {"result": response},
            )
        )
    if kind == "text" and event.get("text"):
        return types.Part(text=event["text"])
    return None


root_agent = CoderAgent(
    name="coder",
    description="Implements a pinned commit's contract and pushes the result.",
)

app = App(
    root_agent=root_agent,
    name="app",
)
