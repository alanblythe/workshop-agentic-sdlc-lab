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

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.genai import types


MODEL = "gemini-3.6-flash"


def probe_image() -> str:
    """Reports whether the container has what an agent that clones and pushes needs.

    Returns:
        One line per check, each PASS or FAIL.
    """
    import shutil
    import subprocess

    out = []

    for binary, flag in (("git", "--version"), ("ssh", "-V")):
        path = shutil.which(binary)
        if not path:
            out.append(f"{binary}=FAIL not on PATH")
            continue
        try:
            res = subprocess.run([binary, flag], capture_output=True, text=True, timeout=15)
            version = (res.stdout or res.stderr).strip().splitlines()[0]
        except Exception as exc:
            version = f"unreadable: {exc}"
        out.append(f"{binary}=PASS {version}")

    try:
        res = subprocess.run(["git", "config", "--get", "user.email"],
                             capture_output=True, text=True, timeout=15)
        email = res.stdout.strip()
        out.append(f"git_identity={'PASS ' + email if email else 'FAIL unset'}")
    except Exception as exc:
        out.append(f"git_identity=FAIL {exc}")

    try:
        with open("/etc/ssh/ssh_known_hosts") as fh:
            hosts = [line.split()[1] for line in fh if line.strip() and not line.startswith("#")]
        out.append(f"known_hosts=PASS {len(hosts)} keys, types {sorted(set(hosts))}")
    except Exception as exc:
        out.append(f"known_hosts=FAIL {exc}")

    # Strict host checking stays on. If the pinned keys are right this
    # authenticates far enough for GitHub to reject the (absent) key, which is
    # a different failure from an unknown host.
    try:
        res = subprocess.run(
            ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
             "-o", "StrictHostKeyChecking=yes", "git@github.com"],
            capture_output=True, text=True, timeout=45)
        err = res.stderr.strip().replace("\n", " ")[:160]
        verified = "Host key verification failed" not in err
        out.append(f"host_key_trusted={'PASS' if verified else 'FAIL'} rc={res.returncode} {err}")
    except Exception as exc:
        out.append(f"host_key_trusted=FAIL {exc}")

    try:
        res = subprocess.run(["python", "-m", "pytest", "--version"],
                             capture_output=True, text=True, timeout=30)
        out.append(f"pytest={'PASS ' + (res.stdout or res.stderr).strip() if res.returncode == 0 else 'FAIL'}")
    except Exception as exc:
        out.append(f"pytest=FAIL {exc}")

    return " | ".join(out)


async def start_coding_run(
    repo: str, sha: str, branch: str, tool_context: ToolContext = None
) -> str:
    """Runs the coding agent against a repository, at an exact commit.

    Call this once per dispatch, including a dispatch that resumes earlier
    work: the previous run's files are gone even though this conversation is
    not. Prior work is recovered from the branch, not from disk.

    Args:
        repo: owner/name of the GitHub repository, e.g. "octocat/hello".
        sha: the exact commit dispatched. Nothing committed after it is visible.
        branch: the branch to push work to, e.g. "agent/parse".

    Returns:
        What was checked out, the tool calls the coder made, and its own account
        of where it got to.
    """
    from app import coder_client

    # Attribution only -- the coding run gets its own session, named after the
    # repository and branch rather than after this conversation.
    user_id = getattr(
        getattr(getattr(tool_context, "_invocation_context", None), "session", None),
        "user_id", None,
    ) or "coder-agent"
    return await coder_client.run(repo=repo, sha=sha, branch=branch, user_id=user_id)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You dispatch and report on unattended coding runs.\n\n"
        "When given a repository, a commit and a branch, call "
        "start_coding_run exactly once and report what it returns verbatim. "
        "Do not summarise the trajectory and do not soften the result: if the "
        "coder ran out of time with tests still failing, say so plainly.\n\n"
        "This conversation may span several dispatches. Earlier turns tell you "
        "what has already been tried; the code itself lives on the branch, not "
        "in this container. On a second dispatch, call start_coding_run again "
        "with the same arguments -- it resumes from the branch.\n\n"
        "When asked to run a diagnostic probe, call probe_image once and report "
        "its raw output verbatim. Never invent values."
    ),
    tools=[start_coding_run, probe_image],
)

app = App(
    root_agent=root_agent,
    name="app",
)
