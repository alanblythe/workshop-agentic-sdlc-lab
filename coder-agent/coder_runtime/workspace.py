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

"""The git workspace the coder agent writes in, and the two tools it needs there.

Runs in the isolated coding environment, not in the ADK serving one -- see
``pyproject.toml`` in this directory for why they are separate.

Reading, editing and running commands are the Antigravity SDK's job -- see
``coder.py``. What is left here is everything the SDK has no opinion about:
getting a private repository onto disk at an exact commit, getting the work
back off again, and knowing how long is left.

Three stores, and the run needs all three:

* **Agent Platform Sessions** holds the reasoning across dispatches. It is what
  makes a second dispatch a continuation rather than a restart.
* **The branch** holds the code. It is the only durable artifact; the deadline
  can arrive at any moment and whatever is pushed is what survives.
* **This workspace** holds neither. ``/tmp`` is on the instance's overlay and
  does not outlive the invocation, so every dispatch rebuilds it.

Nothing here blocks the event loop: every subprocess goes through
``asyncio.create_subprocess_exec``.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import time

# 600s is a hard cap on total invocation, measured, and it arrives as a 503
# injected into the stream rather than as anything the agent can catch. The
# reserve is for the last commit and push, which have to happen on the right
# side of the deadline to be worth anything.
_budget_seconds = 540.0

_state: dict[str, object] = {}


def set_budget(seconds: float) -> None:
    """Set how long this run gets. The parent owns the number; it knows when the
    invocation started, and this process did not."""
    global _budget_seconds
    _budget_seconds = seconds


def slug(*parts: str) -> str:
    """Stable short id for a repo+branch pair. Names the workspace and the session,
    so a second dispatch of the same work lands on both."""
    return hashlib.sha1("/".join(parts).encode()).hexdigest()[:12]


async def _run(
    *argv: str,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> tuple[int, str]:
    """Run a command without blocking the event loop. Returns (rc, merged output)."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, f"timed out after {timeout:.0f}s: {' '.join(argv)}"
    return proc.returncode or 0, (out or b"").decode(errors="replace")


async def _read_deploy_key() -> str:
    """Read the deploy key from Secret Manager with the generated client.

    The generated client and nothing else. A hand-built request carrying
    ``Authorization: Bearer creds.token`` is refused **401 even when the
    identity is fully authorized** -- measured. A 401 here reads as a
    permissions problem and is not one; a real permissions problem is a 403.
    """
    from google.cloud import secretmanager

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is unset, so the secret cannot be named")
    secret = os.environ.get("DEPLOY_KEY_SECRET_ID", "agentic-sdlc-deploy-key")

    client = secretmanager.SecretManagerServiceAsyncClient()
    resp = await client.access_secret_version(
        name=f"projects/{project}/secrets/{secret}/versions/latest"
    )
    return resp.payload.data.decode()


async def prepare(repo: str, sha: str, branch: str) -> tuple[str | None, str]:
    """Fetch ``repo`` at ``sha`` (or resume ``branch``) into a fresh workspace.

    Returns (tree, message). ``tree`` is None when the message is a failure.
    """
    root = f"/tmp/agentic-sdlc-{slug(repo, branch)}"
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root, mode=0o700, exist_ok=True)

    tree = os.path.join(root, "repo")
    key_path = os.path.join(root, "deploy_key")

    try:
        key = await _read_deploy_key()
    except Exception as exc:  # noqa: BLE001 - the message is the whole point
        return None, (
            f"FAILED to read the deploy key: {type(exc).__name__}: {exc}\n"
            "403 means the grant is missing. 401 means something built a request "
            "by hand instead of using the client library."
        )

    # ssh refuses a private key that anyone else can read, and says so in terms
    # of file modes without ever mentioning credentials.
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w") as fh:
        fh.write(key if key.endswith("\n") else key + "\n")

    ssh = (
        f"ssh -i {key_path} -o IdentitiesOnly=yes "
        "-o UserKnownHostsFile=/etc/ssh/ssh_known_hosts "  # pinned at image build
        "-o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=20"
    )
    env = {"GIT_SSH_COMMAND": ssh, "GIT_TERMINAL_PROMPT": "0"}
    url = f"git@github.com:{repo}.git"

    os.makedirs(tree, exist_ok=True)
    rc, out = await _run("git", "init", "-q", cwd=tree, env=env)
    if rc:
        return None, f"FAILED git init: {out}"
    await _run("git", "remote", "add", "origin", url, cwd=tree, env=env)

    # A resumed dispatch continues from what the last one pushed. The branch
    # descends from the dispatched SHA, so the pin still holds: work carries
    # forward, but nothing committed to main after dispatch becomes reachable.
    rc, _ = await _run("git", "fetch", "--depth", "50", "origin", branch, cwd=tree, env=env)
    resumed = rc == 0
    if not resumed:
        # `clone --depth 1` then `checkout <sha>` does NOT work: a depth-1 clone
        # holds only the tip, and by the time the agent runs the dispatched SHA
        # is usually behind it -- `fatal: unable to read tree`. Fetching the SHA
        # by name is the recipe that does work.
        rc, out = await _run("git", "fetch", "--depth", "1", "origin", sha, cwd=tree, env=env)
        if rc:
            return None, (
                f"FAILED to fetch {sha} from {repo}: {out}\n"
                "'Permission denied (publickey)' means the deploy key is not on "
                "this repository. 'Host key verification failed' means the "
                "image's pinned host keys are wrong."
            )

    rc, out = await _run("git", "checkout", "-q", "-B", branch, "FETCH_HEAD", cwd=tree, env=env)
    if rc:
        return None, f"FAILED to check out FETCH_HEAD: {out}"

    _, head = await _run("git", "rev-parse", "HEAD", cwd=tree, env=env)
    _state.update(
        {
            "tree": tree,
            "env": env,
            "branch": branch,
            "repo": repo,
            "deadline": time.monotonic() + _budget_seconds,
        }
    )
    return tree, (
        f"{'resumed ' + branch if resumed else 'started at ' + sha[:12]}, "
        f"HEAD={head.strip()[:12]}, {seconds_left():.0f}s of budget"
    )


def seconds_left() -> float:
    deadline = _state.get("deadline")
    if deadline is None:
        return 0.0
    return max(0.0, float(deadline) - time.monotonic())  # type: ignore[arg-type]


# --- the two tools handed to the Antigravity agent -------------------------
# Plain callables. The SDK reads the signature and the docstring, so both are
# part of the contract the model sees.


async def commit_and_push(message: str) -> str:
    """Commit everything in the repository and push it to the working branch.

    Do this after every iteration, not only at the end. The branch is the only
    state that survives the deadline, so pushing often costs one iteration
    instead of the whole run.

    Args:
        message: the commit message -- what changed and why, as a person would write it.

    Returns:
        The commit that was pushed, or a note that there was nothing to commit.
    """
    tree = _state.get("tree")
    if not tree:
        return "no workspace: the run was not prepared."
    env: dict[str, str] = _state["env"]  # type: ignore[assignment]
    branch = str(_state["branch"])

    await _run("git", "add", "-A", cwd=str(tree), env=env)
    rc, out = await _run("git", "commit", "-m", message, cwd=str(tree), env=env)
    if rc and "nothing to commit" in out:
        return "nothing to commit -- the tree matches the last push."
    if rc:
        return f"FAILED to commit: {out}"

    rc, out = await _run(
        "git", "push", "origin", f"HEAD:refs/heads/{branch}",
        cwd=str(tree), env=env, timeout=90.0,
    )
    if rc:
        return (
            f"FAILED to push: {out}\n"
            "'marked as read only' means the deploy key has no write access."
        )
    _, head = await _run("git", "rev-parse", "--short", "HEAD", cwd=str(tree), env=env)
    return f"pushed {head.strip()} to {branch}. {seconds_left():.0f}s remain."


async def time_remaining() -> str:
    """Report how many seconds are left before this run is cut off.

    Returns:
        The seconds remaining, and what to do when they are nearly gone.
    """
    left = seconds_left()
    if left <= 0:
        return "0s -- the deadline has passed. Push now and say where you got to."
    if left < 90:
        return f"{left:.0f}s -- finish the current edit, push, and report honestly."
    return f"{left:.0f}s remain."
