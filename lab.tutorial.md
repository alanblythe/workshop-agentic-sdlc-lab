<!-- Generated from guides/lab.md.hbs by the presenter repo. Do not edit. -->
# The agentic SDLC lab

<walkthrough-tutorial-duration duration="59"></walkthrough-tutorial-duration>

## Before you begin

<walkthrough-tutorial-duration duration="4"></walkthrough-tutorial-duration>

You are going to take a request written the way requests actually arrive:
prose, from a stakeholder, with the important parts unsaid, and get working
code out of the other end. A coding agent writes the code. You never do.

The interesting part is not the agent. It is what you have to make true before
an agent can be useful: a specification precise enough that two parties could
build from it independently and their code would fit.

### What you'll learn

- How to interrogate a specification until the ambiguity is gone, using an
  agent that refuses to decide anything for you
- How to turn resolved decisions into contract tests, which are what make an
  agent's work checkable
- How to deploy an agent to Agent Runtime under its own identity, and dispatch
  work to it at a pinned commit
- Why the commit is pinned, and what that buys you

### What you'll need

- The [preflight from the setup guide](https://alanblythe.github.io/workshop-agentic-sdlc/agentic-sdlc-setup/), finished and reporting **ready**
- A GitHub account with `gh` logged in

### Restore your Cloud Shell

Update `agy`. It lives on the VM rather than in `$HOME`, so a new session may
have an older one. No harm if you are already current.

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

Pick the project you set up with:

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

Then check your GitHub login survived, which it should have:

```bash
gh auth status
```

> **Careful:**
>
> Setting those two to the same value produces a 404 that names the model and
> reads like a typo in the model name rather than a wrong location.

### Verify your work

```bash
gcloud secrets describe agentic-sdlc-deploy-key --format='value(name)'
```

It should print the secret's resource name. That secret is empty. Preflight
created the container, and you will put a key in it later today.

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
```

`origin` now points at your fork and `upstream` at the original.

The second line is not housekeeping. Forking sets `gh`'s default repository to
**upstream**, so without it the issue you file lands on the workshop's copy
rather than yours, and nothing tells you. The third turns issues on, which
GitHub disables on every new fork, and which you find out about two steps from
here when you try to file one.

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

## Start the agent deploying, then walk away

<walkthrough-tutorial-duration duration="4"></walkthrough-tutorial-duration>

The agent takes several minutes to build and deploy. Start it now and do the
thinking while it works. Waiting at a progress bar teaches nothing.

```bash
(cd coder-agent && agents-cli deploy \
  --project "$(gcloud config get-value project)" \
  --region "$AGENT_ENGINE_LOCATION" \
  --agent-identity \
  --update-env-vars GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true,MODEL_LOCATION=global \
  --no-wait)
```

`--no-wait` returns as soon as the build is submitted. `--agent-identity` is the
part that matters most: it gives the deployment a federated identity of its own
rather than borrowing a service account, which is how it will read a secret you
have not given it yet.

> **Tip:**
>
> The deploy takes about seven minutes, and it runs while you work through the
> next four steps. The minutes on this step are the ones you spend starting it.
> A first deploy in a cold project is slower than every later one, because
> nothing is cached yet.

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

File it, so the work has a number. The agent's commits will reference it and
merging its branch will close it, which is what the number is for:

```bash
gh issue create --title "Account health scoring" --body-file docs/request.md
```

> **Careful:**
>
> Use `--body-file`, not `-F`. With `-F` the command stops and asks for a title
> interactively, which is easy to miss and looks like a hang.

Someone else has already turned it into a spec. Read <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/docs/spec.md">docs/spec.md</walkthrough-editor-open-file>
as though you had to implement it this afternoon.

```bash
cat docs/spec.md
```

> **Careful:**
>
> **This spec was written to be flawed, and you should know that up front.** It
> reads well, which is the point. The gaps in it are the kind that survive review
> because nothing about them looks wrong. Finding them is the exercise.

It already conforms to <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/docs/spec-template.md">docs/spec-template.md</walkthrough-editor-open-file>, the shape a spec
has to have here before anyone writes code. Every required section is present,
`Open questions` says none, and it is nowhere near buildable. Sections are
cheap. The gate at the end of that template is the part that costs something.

As you read, keep one question in mind, and only this one:

> Could two people build from this independently, without talking, and would
> their code fit together?

Anything that passes is precise enough. Anything that does not is a decision
nobody has made yet.

### Verify your work

Think about two things in the spec you could implement in more than one way,
and that a reviewer would probably wave through. You will find out shortly
whether they are the ones that matter.

## Interrogate the spec

<walkthrough-tutorial-duration duration="12"></walkthrough-tutorial-duration>

The interrogator is a skill called **spec-adversary**, and it ships in this
repository, which means it is now in your fork. Install it, then start `agy`:

```bash
agy plugin install .
agy
```

> **Careful:**
>
> Install before you start `agy`, not after. Skills are discovered when it
> starts, so one added to a running session is not there.

Then ask it to go to work:

```text
Use the spec-adversary skill on docs/spec.md. One ambiguity at a time.
```

### Read what you just pointed at

Before you answer its first question, open
<walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/skills/spec-adversary/SKILL.md">skills/spec-adversary/SKILL.md</walkthrough-editor-open-file> and read it. It is 150 lines and
it is the whole method: sweep the spec before asking anything, one question at
a time, and never recommend a reading. Every refusal you are about to meet is
written down in there, which is the difference between an agent behaving oddly
and an agent behaving as specified.

It is in your fork, so it is yours to change. That is the last step of the
workshop, and the reason the file is here rather than somewhere central.

It puts one ambiguity in front of you at a time: the passage, the two readings,
and the case where they disagree. Arrow keys move, enter chooses. There is a
write-in option for when neither reading is what you meant. It writes your
decision into <walkthrough-editor-open-file filePath="cloudshell_open/workshop-agentic-sdlc-lab/docs/spec.md">docs/spec.md</walkthrough-editor-open-file> and moves to the next one.

> **Tip:**
>
> Answer as the person who owns the product, not as the person who has to build
> it. "Whichever is easier" is not a decision. It hands the choice back to
> whoever writes the code, which is exactly the situation you are removing.

Keep going until it stops finding anything consequential. That usually takes
longer than people expect, and the questions get better as they get smaller.

> **Careful:**
>
> Resist the urge to fix the spec yourself while you are in there. The value is in
> the decisions being explicit and attributed, not in the prose being tidy.

### Verify your work

```bash
git diff docs/spec.md
```

The gate, and you can check it yourself:

- `Status` is **Approved**
- `Open questions` is empty
- `Decisions` has a row per question you answered, each naming the case that
  would have differed

Every hunk in that diff should be one of those three. A hunk that is a
rewording is the adversary editing your spec, which it is not allowed to do.

## Emit the contract

<walkthrough-tutorial-duration duration="8"></walkthrough-tutorial-duration>

Decisions in prose are still prose. Now turn them into tests, which is the form
an agent can be held to.

Still in `agy`:

```text
From the resolved docs/spec.md, write contract tests into tests/. Cover the
parsing rules and the scoring rules separately. Do not write an implementation.
Cite the decision id on every assertion that came from one.
```

The adversary does not write them. It hands the job to a subagent called
**contract-writer**, which you will see spawn: a second persona whose only work
is turning resolved decisions into assertions, and which is not allowed to
decide anything. If it reports an assertion it could not derive, that is an
ambiguity the interrogation missed, and the adversary reopens it rather than
letting a guess into a test.

These tests are the contract. They are what "done" means, and they are the only
thing standing between you and an agent that writes plausible code which does
the wrong thing.

### Verify your work

First, that the files exist:

```bash
git status --short tests/
```

Three new files. If the subagent reported writing them and this prints nothing,
it did not write them: what an agent says it did and what is on disk are two
different claims, and only one of them is checkable.

```bash
uv run pytest -q
```

You get errors, not failures: `ModuleNotFoundError: No module named 'usage'`.
That is the right result. The contract names a module nobody has written yet,
so the tests cannot be imported, let alone pass, and collection stops before
the starter tests run. A test that passes now is testing nothing.

## Check the deploy landed

<walkthrough-tutorial-duration duration="3"></walkthrough-tutorial-duration>

Your agent should be up by now.

```bash
(cd coder-agent && agents-cli deploy --status)
```

```bash
(cd coder-agent && agents-cli deploy --list)
```

Confirm it is running under its own identity rather than a borrowed service
account. There is no `gcloud` surface for this, so ask the API directly:

```bash
export API="https://${AGENT_ENGINE_LOCATION}-aiplatform.googleapis.com/v1"
export BASE="${API}/projects/$(gcloud config get-value project)/locations/${AGENT_ENGINE_LOCATION}/reasoningEngines"
export ENGINE=$(curl -sS -H "Authorization: Bearer $(gcloud auth print-access-token)" "$BASE" \
  | python3 -c "import json,sys; print(next(e['name'] for e in json.load(sys.stdin)['reasoningEngines'] if e.get('displayName')=='coder-agent'))")

curl -sS -H "Authorization: Bearer $(gcloud auth print-access-token)" "${API}/${ENGINE}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['spec']['effectiveIdentity'])"
```

> **Careful:**
>
> The deploy output prints a `gcp-sa-aiplatform-re` service account even when
> `--agent-identity` worked. It is not the identity your agent runs as.
> `spec.effectiveIdentity` is the only field that tells the truth.

### Verify your work

`effectiveIdentity` is a long federated principal containing
`system.id.goog`, ending in your engine's id. That principal, and not any
service account, is what the next step grants access to.

## Give the agent a key to your fork

<walkthrough-tutorial-duration duration="4"></walkthrough-tutorial-duration>

The agent has to push. It needs a credential, and it needs one that cannot do
anything else.

```bash
bash scripts/setup-deploy-key.sh
```

That generates an SSH key, gives it write access to **this repository only**,
proves it works, and puts the private half in the Secret Manager secret preflight
made. Nothing is left on your machine.

> **Tip:**
>
> A deploy key's blast radius is one repository, by construction. There is no
> scope matrix to get wrong, and revoking it is deleting one key from one repo.

### Verify your work

The script ends by printing the secret the agent reads and the repository it can
push to. It also refuses to finish unless a real clone and a real push
succeeded, so reaching the end *is* the verification.

## Dispatch

<walkthrough-tutorial-duration duration="5"></walkthrough-tutorial-duration>

Commit the contract and send the work.

```bash
git add -A
git commit -m "The contract: resolved spec and the tests it implies"
git push
bash scripts/dispatch.sh --issue 1
```

The dispatch pins the exact commit you just pushed. The agent fetches that
commit and nothing else.

`--issue` is the number you filed earlier, which is **1** on a fork whose
issues you had just turned on. Run `gh issue list` if yours is not. The agent
writes it into every commit it pushes, and dispatch refuses a number that is
not an open issue rather than let a wrong one reach the commits.

> **Tip:**
>
> That pin is why you cannot rescue a bad contract once the agent is working.
> Anything you commit after this moment is invisible to it, not by agreement but
> because it never fetches anything else. If the contract was wrong, you find out
> the way you would with a colleague who took the brief and went quiet.

The script follows your branch and prints each commit as it lands. Closing it
does not stop the agent.

### Verify your work

You should see the agent's branch appear and at least one commit arrive on it.
The run ends with the branch name and how to merge it.

## Read what it did

<walkthrough-tutorial-duration duration="6"></walkthrough-tutorial-duration>

Do not merge yet. Read.

```bash
git fetch origin
git log --oneline origin/agent/parse
git diff main...origin/agent/parse
```

Then check it against the contract rather than against your impression of it:

```bash
git checkout -b review origin/agent/parse
uv run pytest -q
```

You can also watch the whole trajectory, every file it read and every command it
ran, in the console, because each step was recorded as an event in the agent's
session.

> **Careful:**
>
> Green tests mean it satisfied the contract. They do not mean the contract was
> right. If the code passes and still does the wrong thing, that is a finding
> about your spec, and it is the most valuable thing this lab can hand you.

### Verify your work

The tests pass, and the diff touches the implementation only. If the agent
edited a test to make it pass, you have learned something about how contracts
need to be written.

Merge when you are satisfied, and push:

```bash
git checkout main
git merge origin/agent/parse
git push
```

The push is what closes your issue. The agent wrote `Closes #1` into its commit
messages, and GitHub acts on that when those commits land on your default
branch, not when they land on a branch.

## Tear it down

<walkthrough-tutorial-duration duration="4"></walkthrough-tutorial-duration>

The agent costs money while it is deployed. Remove it, and the credential with
it.

One command removes everything the day created:

```bash
bash scripts/teardown.sh
```

It shows you what it is about to remove and asks before doing it. Use
`--dry-run` first if you would rather look than trust.

It deletes three things: the deployed agent, the Secret Manager secret, and the
deploy key on your fork. Your branches and the agent's commits are left alone,
and so are the APIs. Your project may well have been using them before today.

> **Tip:**
>
> Deleting the deploy key is the part that matters most. The agent is only
> costing you money; the key is granting write access to your repository until it
> is gone. The script removes it first for that reason.

> **Careful:**
>
> Do this even if you plan to come back. A deployed agent holds a warm instance
> and bills for it, and the deploy key stays valid until you delete it.

### What you did

You took prose from a stakeholder and produced merged, tested code without
writing any of it. The agent was the least interesting part: it did what the
contract said, because by then the contract said something.

The work that mattered was refusing to let the ambiguity through, and the
reason the agent could be trusted with the rest is that you had made "done"
checkable before you asked anyone, human or otherwise, to do it.

### What's next

- Run it again with a spec you actually own, and see how far the interrogation
  gets before you have to make a decision you were avoiding
- Read the trajectory in the console. The tool calls are a record of how it
  reasoned, and they show where the contract was doing the work

### Verify your work

```bash
bash scripts/teardown.sh
```

Run a second time it reports **Already torn down** and changes nothing. That is
the check: it is safe to re-run, so there is no doubt about whether it finished.
