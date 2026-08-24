<!-- Generated from guides/lab.md.hbs by the presenter repo. Do not edit. -->
# The agentic SDLC lab

<walkthrough-tutorial-duration duration="60"></walkthrough-tutorial-duration>

## Before you begin

<walkthrough-tutorial-duration duration="2"></walkthrough-tutorial-duration>

This lab simulates the common scenario for feature requests that provide 
detailed information, though lack to cover edge and boundary conditions.

In this lab you'll:
- Use Antigravity CLI with skills, subagents, and a MCP server
- Deploy an agent to Gemini Enterprise Agent Platform
- Use an adversarial skill to refine a spec
- Interfact with a code-agent deployed to Agent Platform. You'll instruct this
agent to write the implementation code starting from your GitHub commit hash

This lab is built on two practices. **Spec-driven development** builds a
specification for review and agreement before any code is written.
**Test-driven development, TDD** writes the tests before the implementation they
check. Spec clarity is of utmost importance. This lab uses an adversarial skill
to ensure a clear spec is authored and approved before coding starts.

The **Agent Platform** agent is deployed using Agent Identity.

The lab is deliberately simplified: one request, one spec, one agent, one
repository, and no CI.

### What you'll learn

- How to interrogate a specification until the ambiguity is gone, using an
  agent skill that refuses to decide anything for you
- How to turn resolved decisions into acceptance tests, which are what make an
  agent's work checkable
- How to deploy an agent to Agent Runtime under its own identity, and dispatch
  work to it at a pinned commit
- How to author and use Antigravity CLI skills, subagents, and MCP servers

### What you'll need

- The [preflight from the setup guide](https://alanblythe.github.io/workshop-agentic-sdlc/agentic-sdlc-setup/), finished and reporting **ready**
- A GitHub account with `gh` logged in, forking to **your own account**

> **Careful:**
>
> Fork to your own account, not to an organization. The agent pushes with a
> deploy key, and organizations default to off.

## Fork the lab repository

<walkthrough-tutorial-duration duration="3"></walkthrough-tutorial-duration>

The application lives in its own repository. You fork it, because the agent will
push to your copy and you will merge its work.

You are already in a clone of it, the one Cloud Shell made when you opened this
guide. Fork in place, and set the fork up in the same breath:

```bash
gh repo fork --remote
gh repo set-default "$(git remote get-url origin)"
gh repo edit --enable-issues
git push -u origin main
```

`origin` now points at your fork and `upstream` at the original. The rest is
not housekeeping:

- `gh repo set-default` — forking points `gh` at **upstream**, so without it
  the issue you file lands on the workshop's copy rather than yours, and
  nothing tells you
- `gh repo edit --enable-issues` — GitHub disables issues on every new fork,
  which you would otherwise discover two steps from here, when you try to file
  one
- `git push -u origin main` — forking in place renamed your `origin` to
  `upstream` and took the branch's tracking with it, so a bare `git push` later
  today would aim at the workshop's copy and be rejected

> **Tip:**
>
> A fork does not copy the issues from the repository it came from either. That
> is deliberate. You are about to file one, and it should be yours.

### Verify your work

```bash
gh repo view --json nameWithOwner,isFork,hasIssuesEnabled \
  --jq '.nameWithOwner + " fork=" + (.isFork|tostring) + " issues=" + (.hasIssuesEnabled|tostring)'
```

The owner should be **you**, with `fork=true` and `issues=true`.

## Restore your Cloud Shell

<walkthrough-tutorial-duration duration="2"></walkthrough-tutorial-duration>

Cloud Shell keeps your `$HOME` and forgets the rest, so a session opened today
has none of setup's environment. Five things have to be true before anything
below will work:

- `agy` is current, and still logged in
- `gcloud` is logged in, **and so is ADC**
- `gcloud` is pointed at your project
- `MODEL_LOCATION` and `AGENT_ENGINE_LOCATION` are set
- `gh` is still authenticated

Update `agy` first. It lives on the VM rather than in `$HOME`, so a new session
may have an older one. No harm if you are already current.

```bash
sudo agy update && agy --version
```

Check your `agy` login:

```bash
agy -p "Reply with exactly: authenticated"
```

If it asks you to open a URL instead of answering, the grant has lapsed. Log in
again with [Authenticate agy](https://alanblythe.github.io/workshop-agentic-sdlc/agentic-sdlc-setup/#7)
from the setup guide, then come back.

Now your two Google grants, before anything that calls `gcloud`. The `gcloud`
login and Application Default Credentials are separate, and `--update-adc` does
both in one command:

```bash
gcloud auth login --update-adc
```

> **Careful:**
>
> **ADC is the one that goes missing.** It is a different file from your `gcloud`
> login, and it is what `agents-cli` and the `geap` tools read. Without it the
> deploy fails on credentials rather than on anything it was asked to do.

Select the project you ran preflight against. **Ignore the offer to create a
new one** — that link belongs to the picker, and a fresh project has none of
the APIs, the service account or the secret this lab needs.

<walkthrough-project-setup></walkthrough-project-setup>

Point `gcloud` at it. A new session has no project set, and every `gcloud`
command below needs one:

```bash
gcloud config set project <walkthrough-project-id/>
gcloud config get-value project
```

Set your two locations. A new shell has neither. `MODEL_LOCATION` is fixed by
the model: the Gemini 3 family answers only from `global`. Your engine region
is whatever you chose during setup, and the project remembers it, because
Terraform replicated the secret into that region:

```bash
export MODEL_LOCATION=global
export AGENT_ENGINE_LOCATION=$(gcloud secrets describe agentic-sdlc-deploy-key \
  --format='value(replication.userManaged.replicas[0].location)')
echo "$MODEL_LOCATION / $AGENT_ENGINE_LOCATION"
```

> **Careful:**
>
> Setting those two to the same value produces a 404 that names the model and
> reads like a typo in the model name rather than a wrong location.

Then your GitHub login, which should have survived:

```bash
gh auth status
```

### Verify your work

```bash
gcloud auth application-default print-access-token >/dev/null && echo "ADC ok"
gcloud secrets describe agentic-sdlc-deploy-key --format='value(name)'
```

The first prints `ADC ok` — minting a token is what proves the credential is
live rather than merely present on disk. The second prints the secret's
resource name. That secret is empty: preflight created the container, and you
put a key in it later today.

## Deploy the coder-agent

<walkthrough-tutorial-duration duration="4"></walkthrough-tutorial-duration>

The agent takes up to 10 minutes to build and deploy. Continue without
the next steps while it deploys.

```bash
(cd coder-agent && agents-cli deploy \
  --project "$(gcloud config get-value project)" \
  --region "$AGENT_ENGINE_LOCATION" \
  --agent-identity \
  --update-env-vars GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true,MODEL_LOCATION=global \
  --no-wait)
```

`--no-wait` returns as soon as the build is submitted. `--agent-identity`
enables Agent Identity: it gives the agent a SPIFFE identity rather than a
service account. This identity is granted access to Secret Manager by an IAM
binding that preflight's Terraform put on the secret. That binding names every
Agent Runtime agent in the project rather than one engine, so it was in place
before this agent existed.

### Verify your work

```bash
(cd coder-agent && agents-cli deploy --status)
```

It reports the deployment as in progress. You are not waiting for it. The next
four steps happen while it builds.

## Read the request, then the spec

<walkthrough-tutorial-duration duration="6"></walkthrough-tutorial-duration>

<walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/docs/request.md">docs/request.md</walkthrough-editor-open-file> is the request as it arrived. It is short, and
it is the only statement of what anyone actually wants.

```bash
cat docs/request.md
```

Create the GitHub issue, the agent's commits will reference it and
merging its branch will close it:

```bash
gh issue create --title "Account health scoring" --body-file docs/request.md
```

Read <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/docs/spec.md">docs/spec.md</walkthrough-editor-open-file>. We'll use an adversarial refinement skill to
ensure the spec is clear and can be used for creating acceptance tests and
writing code.

```bash
cat docs/spec.md
```

> **Tip:**
>
> **This spec was written to be flawed.** It reads well, but it has subtle
> gaps that would often survive review. After going through the Human in the loop (HITL)
> adversarial review the gaps will become clear.

It already conforms to <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/docs/spec-template.md">docs/spec-template.md</walkthrough-editor-open-file>, a representative template
that may be used as part of a broader SDLC.

> **Tip:**
>
> **A typical production spec carries more than this one.** The template folds 
> design into *The two halves* and decision records into *Decisions*, and leaves out
> what a 60-minute lab has no room for:
>
> - Non-functional requirements — limits, latency, error handling
> - Architecture beyond a single interface: components, dependencies, data flow
> - Data model, persistence and retention
> - Architectural Design Records: Decision records with the alternatives that were rejected
> - Security, privacy and data classification
> - Rollout, migration and backwards compatibility
> - Observability — what it logs, and what you can alert on
> - Risks, considered or mitigated

> **Tip:**
>
> LLMs are inherently non-deterministic. Trajectories and Evals were used in the
> construction of this lab. The spec was purposely simplified to reduce the effort
> the lab taker must undergo to arrive at a valid spec.

As you read the spec you may ask these questions:

> Could acceptance tests and code be implemented
> independently from each other?
> Are there subtle gaps in the understanding of the data?

The data the spec is written against is <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/fixtures/usage.csv">fixtures/usage.csv</walkthrough-editor-open-file>.

## Interrogate the spec

<walkthrough-tutorial-duration duration="12"></walkthrough-tutorial-duration>

The interrogator is a skill called **spec-adversary**, and it ships in this
repository at <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/.agents/skills/spec-adversary/SKILL.md">.agents/skills/spec-adversary/SKILL.md</walkthrough-editor-open-file>, Antigravity CLI
will automatically load it. A workspace skill is found
relative to where `agy` starts, so start it from the lab repo, workshop-agentic-sdlc-lab:

```bash
cd ~/cloudshell_open/workshop-agentic-sdlc-lab
agy --mode accept-edits
```

> **Tip:**
>
> `--mode accept-edits` allows auto-editing of files, otherwise you would need 
> to approve every file create/edit, including the ones the subagent writes.  
> `shift` + `tab` cycles the mode if you would rather approve each one.

### Use the skill to clarify the spec

Open <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/.agents/skills/spec-adversary/SKILL.md">.agents/skills/spec-adversary/SKILL.md</walkthrough-editor-open-file> and read it. 
The skill instructs: 
- sweep the spec before asking anything
- one question at a time
- never recommend a reading. 
- to give choices allowing simple selection
- writes decisions into <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/docs/spec.md">docs/spec.md</walkthrough-editor-open-file>

Ask Antigravity CLI to use the skill:

```text
Use the spec-adversary skill on docs/spec.md. The sample data is
fixtures/usage.csv. One ambiguity at a time.
```

The sample data it asks about is <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/fixtures/usage.csv">fixtures/usage.csv</walkthrough-editor-open-file>.

> **Tip:**
>
> Answer as the person who owns the product, not as the person who has to build
> it. "Whichever is easier" is not a decision. It hands the choice back to
> whoever writes the code, which is exactly the situation you are removing.

Keep going until it stops finding anything consequential. That usually takes
longer than people expect, and the questions get better as they get smaller.

### Verify your work

Open the **Source Control** view in the editor and click `spec.md` to see what
changed.

![The Source Control view, with spec.md listed as changed](https://raw.githubusercontent.com/alanblythe/workshop-agentic-sdlc-lab/main/docs/images/source-control-spec-diff.png)

The gate, and you can check it yourself:

- `Status` is **Approved**
- `Open questions` is empty
- `Decisions` has a row per question you answered, each naming the case that
  would have differed

Every hunk in that diff should be one of those three. A hunk that is a
rewording is the adversary editing your spec, which it is not allowed to do.

## Emit the contract

<walkthrough-tutorial-duration duration="8"></walkthrough-tutorial-duration>

Now codify the spec and decisions into acceptance tests using the contract-writer agent.

Still in `agy`:

```text
Use the contract-writer agent to write acceptance tests into scorer/tests/ from
the resolved docs/spec.md, and the interface they call into scorer/usage.py. Cover
the parsing rules and the scoring rules separately. Every function body in
scorer/usage.py raises NotImplementedError and nothing else. Cite the decision
id on every assertion that came from one.
```

> **Tip:**
>
> The agent name "contract-writer" is specifically used to ensure Antigravity CLI
> chooses the configured subagent in <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/.agents/agents/contract-writer/agent.md">.agents/agents/contract-writer/agent.md</walkthrough-editor-open-file>.

The adversary skill helps you the product manager clarify requirements.
The **contract-writer** subagent writes the stubbed tests.
You'll see the agent spawn: turning resolved decisions into assertions, 
and which is not allowed to decide anything. If it reports an assertion 
it could not derive, that is an ambiguity the interrogation missed, 
and the adversary reopens it rather than letting a guess into a test.

![The contract-writer subagent launching](https://raw.githubusercontent.com/alanblythe/workshop-agentic-sdlc-lab/main/docs/images/contract-writer-spawn.png)

These tests are the contract. They are what "done" means.
They provide codified assertions to ensure the written code 
fulfills the spec requirement.

### Verify your work

Leave `agy` first, so these run in the shell:

```text
/exit
```

First, check what files the subagent created:

```bash
git status --short scorer/
```
You should see the three test files authored by the subagent.

Run the tests:

```bash
uv run pytest -q
```

![pytest reporting the acceptance tests failed and the starter tests passed](https://raw.githubusercontent.com/alanblythe/workshop-agentic-sdlc-lab/main/docs/images/contract-tests-failing.png)

**Failures, not errors.** The acceptance tests fail, because the implementation
hasn't been coded yet.

## Check the deploy landed

<walkthrough-tutorial-duration duration="3"></walkthrough-tutorial-duration>

Your agent should be up by now, and you are back in the shell.

```bash
(cd coder-agent && agents-cli deploy --status)
```

![agents-cli reporting the deployment succeeded, with the agent card URL and runtime id](https://raw.githubusercontent.com/alanblythe/workshop-agentic-sdlc-lab/main/docs/images/deploy-status.png)

If there is no pending deploy operation, list the deployed agents:

```bash
(cd coder-agent && agents-cli deploy --list)
```

Confirm it is running under its own identity rather than a service account.
`gcloud` has no surface for that field, so <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/scripts/agent-identity.sh">scripts/agent-identity.sh</walkthrough-editor-open-file>
asks the REST API.

**It only reads:**

- Finds your `coder-agent` engine
- Reads `spec.effectiveIdentity` over REST
- Prints what it found, changes nothing

```bash
bash scripts/agent-identity.sh
```

### Verify your work

Agent Identity:

- `principal://iam.googleapis.com/`...`system.id.goog/subject/`*ENGINE_ID*

Service accounts:

- `service-`*PROJECT_NUMBER*`@gcp-sa-aiplatform-re.iam.gserviceaccount.com`

The first is what the next step grants access to.

## Ensure git config is correct

<walkthrough-tutorial-duration duration="1"></walkthrough-tutorial-duration>

The commit in two steps needs a git identity, and Cloud Shell often has none.
Look first:

```bash
git config --global --get-regexp '^user\.'
```

- **Two lines back** — you already have one, move on
- **Nothing back** — it is unset, so set it:

```bash
git config --global user.name "Your Name" && git config --global user.email "you@example.com"
```

Use the address on your GitHub account, which is what the commits are
attributed to. `--global` writes to `$HOME`, which Cloud Shell keeps, so this is
once per machine rather than once per session.

### Verify your work

The first command again, with both lines back.

## Give the agent a GitHub deploy key to your fork

<walkthrough-tutorial-duration duration="4"></walkthrough-tutorial-duration>

The agent is written to push its commit to GitHub, so it needs a key of its
own. <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/scripts/setup-deploy-key.sh">scripts/setup-deploy-key.sh</walkthrough-editor-open-file> is what does it.

**What it checks, changing nothing:**

- `gh`, `gcloud`, `git`, `ssh-keygen` present
- You have admin on the fork
- Preflight's secret exists

**What it changes:**

- Revokes any previous deploy key
- Generates an ed25519 key pair
- Adds it, write access, this repository
- Proves a push works, `--dry-run`
- Private half into Secret Manager
- Disables older secret versions

```bash
bash scripts/setup-deploy-key.sh
```

![the script reporting a clone over SSH, a push accepted, and the key written to Secret Manager](https://raw.githubusercontent.com/alanblythe/workshop-agentic-sdlc-lab/main/docs/images/deploy-key-verified.png)

The push it makes to prove the key works is a `--dry-run`, so it is a real
authorization check that leaves no ref behind. Nothing is left on your machine.

> **Tip:**
>
> A deploy key is for one repository, by construction. Revoking deploy keys is
> removing it from the repo.

### Verify your work

The script ends by printing the secret the agent reads and the repository it can
push to. It also refuses to finish unless a real clone and a real push
succeeded, so reaching the end *is* the verification.

## Dispatch coder-agent

<walkthrough-tutorial-duration duration="5"></walkthrough-tutorial-duration>

Commit the contract and send the work.

```bash
git add -A && git commit -m "The contract: the resolved spec and the tests it implies" && git push
```

> **Careful:**
>
> **Push before you dispatch.** The agent clones your fork from GitHub, so a
> commit you have not pushed does not exist as far as it is concerned, and it
> will work from the commit before yours without saying so.

The agent runs on Agent Platform, not on this machine. You reach it through
`geap`, the MCP server registered during setup, from inside `agy`.

Start it **from your fork's clone**, not from the setup repository — the prompt
below reads the repository out of the working directory:

```bash
cd ~/cloudshell_open/workshop-agentic-sdlc-lab && agy
```

Paste this:

```text
Use the geap tools. Run list_agents to find coder-agent in this project, then
start_query on it. The message is a JSON string:

  {"repo": "<owner>/<fork>", "sha": "<HEAD>", "branch": "agent/parse", "issue": "1"}

Get repo and sha by running git here: the fork's owner/name from the origin
remote, and the sha that origin/main points at. The repository name must end
in -lab; if it does not, stop and tell me, because I am in the wrong clone.

Then follow the run: call read_query in a loop, passing the next_cursor it
returns, until state is no longer "running". Print any new lines after each
call, before you wait.
```

> **Tip:**
>
> **Approve the tool calls.** MCP calls ask every time, whatever permission mode
> you started in. A run that looks stuck is usually a prompt waiting behind the
> narration.

The lines you see are the agent narrating itself: every file it reads, every
command it runs, and each commit it pushes.

Watch which files it edits. Only `scorer/usage.py` means it is working inside
the contract; an edit naming a test is the agent changing what "done" means.

Leaving `agy` does not stop the agent. It runs on Agent Platform and keeps
going; `read_query` picks the trajectory back up from any cursor.

### Verify your work

The agent's branch appears on your fork and at least one commit lands on it.
When the run reports it is done, leave `agy` and ask for the compare page:

```text
/exit
```

```bash
echo "https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/compare/main...agent/parse"
```

Narration going quiet is not the agent stopping. `read_query` returning no new
lines with a state of "running" means it is working, which is why the branch,
not the narration, is what tells you it landed.

## Read what it did

<walkthrough-tutorial-duration duration="6"></walkthrough-tutorial-duration>

Don't merge yet, review the file diff to see what changes the coder-agent made.

- Open the compare page you printed above, the branch's diff on GitHub
- Click **Create pull request**
- Leave the title and the description alone: GitHub fills both from the
  agent's commit, `Closes #1` and all

Read the diff under **Files changed**. Then run the tests yourself. To keep
things simple, no CI is part of this lab.

```bash
git fetch origin && git checkout -b review origin/agent/parse && uv run pytest -q
```

![pytest reporting every test passed on the agent's branch](https://raw.githubusercontent.com/alanblythe/workshop-agentic-sdlc-lab/main/docs/images/contract-tests-passing.png)

### Verify your work

The tests pass, and the diff touches the implementation only. If the agent
edited a test to make it pass, you have learned something about how contracts
need to be written.

Merge the pull request. Your issue closes as it lands.

Ask `agy` where to watch that happen, rather than hunting for the tab:

```text
Get the gh issue link for me
```

> **Tip:**
>
> The agent wrote `Closes #1` and pushed the commit. **You** opening 
> the pull request is the event GitHub acts on. When you merge the pull
> request Issue 1 will be closed.

## Tear it down

<walkthrough-tutorial-duration duration="4"></walkthrough-tutorial-duration>

One command removes everything the day created:
<walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/scripts/teardown.sh">scripts/teardown.sh</walkthrough-editor-open-file>.

**What it removes:**

- The deployed `coder-agent` and sessions
- The `agentic-sdlc-deploy-key` secret
- The deploy key on your fork

**What it leaves:**

- Your branches and the agent's commits
- The APIs, still enabled

```bash
bash scripts/teardown.sh
```

It prints that list for your project, then asks before doing any of it. Use
`--dry-run` first if you would rather look than trust. The APIs stay on because
your project may have been using them before today, and turning them off is not
this script's call.

### What you did

- Improved a spec using an adversarial review skill, which lives in your fork
  at <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/.agents/skills/spec-adversary/SKILL.md">.agents/skills/spec-adversary/SKILL.md</walkthrough-editor-open-file>
- Used [Antigravity CLI](https://antigravity.google/docs/cli/overview) to turn
  the resolved decisions into acceptance tests
- Deployed a coding agent to Agent Runtime on
  [Gemini Enterprise Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform),
  under an identity of its own
- Dispatched work to it at a pinned commit, and merged what it pushed

Completed a simplified scenario using TDD and Spec-driven development.
The next evolution to this scenario could be agent teams that act as your teammates
within a chat group. You could chat with them as their respective roles e.g. 
product owner, software engineer, peer reviewer, etc.

### What's next

Two things to try with what is already in your fork:

- Run it again with a spec you actually own, and see how far the interrogation
  gets before you have to make a decision you were avoiding
- Change what the adversary refuses to decide for you. It is a skill in your
  fork, and [skills and plugins](https://antigravity.google/docs/cli/plugins/)
  is how they are written

**Codelabs that pick up where this one stops**

- [Stateful Data Science Agent on Agent Engine](https://codelabs.developers.google.com/next26/adk-deploy-scale)
  — Sessions and Memory Bank, the state this lab never keeps
- [Personalized agents with ADK, MCP and Memory Bank](https://codelabs.developers.google.com/codelabs/christmas-card/instructions)
  — memory and tools together
- [Multi-agent systems with ADK, Agent Runtime and A2A](https://codelabs.developers.google.com/codelabs/create-multi-agents-adk-a2a)
  — agents calling agents, rather than one agent doing a job
- [Spec-driven development with Antigravity CLI](https://codelabs.developers.google.com/sdd-agy-cli)
  — the same practice against live data, without the contract or a remote agent
- [Automated UI testing with Antigravity CLI and BrowserMCP](https://codelabs.developers.google.com/agentic-ui-automation-with-antigravity)
  — skills and a multimodal MCP server
- [Deploy to Cloud Run from Antigravity using an MCP server](https://codelabs.developers.google.com/deploy-to-cloud-run-using-oss-mcp-server)
- [Developer Knowledge MCP](https://codelabs.developers.google.com/developer-knowledge-mcp-antigravity)
  and [Workspace MCP](https://codelabs.developers.google.com/google-workspace-mcp-antigravity)
  in Antigravity

**Documentation**

- [Gemini Enterprise Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform)
  — and [Agent Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/overview),
  for what else it hosts
- [ADK on Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk),
  [ADK documentation](https://google.github.io/adk-docs/) and
  [google/adk-python](https://github.com/google/adk-python)
- [agents-cli](https://google.github.io/agents-cli/) and
  [google/agents-cli](https://github.com/google/agents-cli) — what deployed the
  agent here, and what installed the ADK skills during setup
- [Antigravity CLI](https://antigravity.google/docs/cli/overview)
- [geap-mcp](https://github.com/alanblythe/geap-mcp) — the MCP server you
  dispatched through, and its four tools

**Keeping up**

- [The Antigravity blog](https://antigravity.google/blog) and
  [@antigravity](https://x.com/antigravity)
- [Google Developers Blog](https://developers.googleblog.com/) and the
  [Google Cloud AI blog](https://cloud.google.com/blog/products/ai-machine-learning)

