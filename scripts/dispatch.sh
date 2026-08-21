#!/usr/bin/env bash
#
# Agentic SDLC workshop — dispatch a coding run.
#
# Sends your fork, one exact commit, and a branch name to the deployed agent,
# then follows the branch while it works.
#
#   bash scripts/dispatch.sh                    # dispatch and follow
#   bash scripts/dispatch.sh --no-follow        # dispatch and return
#   bash scripts/dispatch.sh --follow-only      # follow a run already going
#
#   --branch NAME   where the agent pushes (default: agent/parse)
#   --engine ID     override engine discovery
#   --help          this text
#
# The commit is pinned at dispatch. The agent physically cannot see anything
# you commit afterwards, which is the point of the exercise rather than an
# agreement to be careful.

set -uo pipefail

BRANCH="agent/parse"
ENGINE=""
FOLLOW=1
DISPATCH=1

while [ $# -gt 0 ]; do
  case "$1" in
    --branch)      BRANCH="${2:-}"; shift 2 ;;
    --engine)      ENGINE="${2:-}"; shift 2 ;;
    --no-follow)   FOLLOW=0; shift ;;
    --follow-only) DISPATCH=0; shift ;;
    --help|-h)     sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)             echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then B=$(printf '\033[1m'); R=$(printf '\033[0m'); RED=$(printf '\033[31m'); GRN=$(printf '\033[32m')
else B=""; R=""; RED=""; GRN=""; fi
step() { printf '\n%s== %s ==%s\n' "$B" "$1" "$R"; }
ok()   { printf '  %sok%s    %s\n' "$GRN" "$R" "$1"; }
info() { printf '  --    %s\n' "$1"; }
die()  { printf '\n  %sFAIL%s  %s\n\n    %s\n\n' "$RED" "$R" "$1" "$2" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# --- 1. where the agent lives ----------------------------------------------
# The host is built from AGENT_ENGINE_LOCATION and never from MODEL_LOCATION.
# MODEL_LOCATION is "global", and "global-aiplatform.googleapis.com" does not
# resolve -- the failure looks like DNS rather than like a config mistake.
step "target"

[ -n "${AGENT_ENGINE_LOCATION:-}" ] || die "AGENT_ENGINE_LOCATION is not set" 'export AGENT_ENGINE_LOCATION=us-central1'
case "$AGENT_ENGINE_LOCATION" in
  global) die "AGENT_ENGINE_LOCATION is 'global'. That is a model endpoint, not a region; interpolated into a host it gives global-aiplatform.googleapis.com, which does not resolve." \
            'export AGENT_ENGINE_LOCATION=us-central1' ;;
esac
HOST="https://${AGENT_ENGINE_LOCATION}-aiplatform.googleapis.com"

have gcloud || die "gcloud is not installed" 'https://cloud.google.com/sdk/docs/install'
have git    || die "git is not installed" 'xcode-select --install'
PROJECT=$(gcloud config get-value project 2>/dev/null)
[ -n "$PROJECT" ] && [ "$PROJECT" != "(unset)" ] || die "no active gcloud project" 'gcloud config set project YOUR_PROJECT_ID'

# ADC, which in Cloud Shell is the attendee's own identity. Nothing inbound
# needs provisioning: they are already allowed to invoke their own engine.
TOKEN=$(gcloud auth print-access-token 2>/dev/null)
[ -n "$TOKEN" ] || die "could not mint an access token" 'gcloud auth login'

BASE="$HOST/v1/projects/$PROJECT/locations/$AGENT_ENGINE_LOCATION/reasoningEngines"
# The agent is a container, so it is dispatched through its own HTTP route and
# not through the platform's :streamQuery -- that returns 404 for a
# sourceCodeSpec engine, and a 404 on a URL built from the right project and
# region reads like the agent is missing rather than like the wrong endpoint.
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)' 2>/dev/null)

if [ -z "$ENGINE" ]; then
  ENGINE=$(curl -sS -H "Authorization: Bearer $TOKEN" "$BASE" 2>/dev/null | python3 -c "
import json,sys
try: engines = json.load(sys.stdin).get('reasoningEngines', [])
except Exception: engines = []
# Only a deployed engine can be dispatched to; a sourceless one has no code.
deployed = [e for e in engines if e.get('spec', {}).get('deploymentSpec')]
print(deployed[-1]['name'].split('/')[-1] if deployed else '')
" 2>/dev/null)
fi
[ -n "$ENGINE" ] || die "no deployed agent found in $PROJECT/$AGENT_ENGINE_LOCATION. A sourceless engine does not count -- it holds sessions but runs no code." \
  "cd coder-agent && agents-cli deploy --project $PROJECT --region $AGENT_ENGINE_LOCATION --agent-identity"
ok "engine $ENGINE in $AGENT_ENGINE_LOCATION"

# --- 2. what to send -------------------------------------------------------
step "the commit"

ORIGIN=$(git remote get-url origin 2>/dev/null)
[ -n "$ORIGIN" ] || die "no 'origin' remote here" 'run this from your clone of your fork'
REPO=$(printf '%s' "$ORIGIN" | sed -E 's#^git@github\.com:##; s#^ssh://git@github\.com/##; s#^https://[^/]*github\.com/##; s#\.git$##')

SHA=$(git rev-parse HEAD 2>/dev/null)
LOCAL_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

if [ "$DISPATCH" -eq 1 ]; then
  # There is no SHA to dispatch until the contract is committed, and no commit
  # the agent can fetch until it is pushed. Both are checked here rather than
  # discovered as a fetch failure inside the container.
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    die "you have uncommitted changes. The agent works from a commit, so anything not committed is invisible to it." \
      'git add -A && git commit -m "the contract" && git push'
  fi
  git fetch -q origin "$LOCAL_BRANCH" 2>/dev/null
  REMOTE_SHA=$(git rev-parse "origin/$LOCAL_BRANCH" 2>/dev/null)
  [ "$SHA" = "$REMOTE_SHA" ] || die "HEAD ($(echo "$SHA" | cut -c1-12)) is not what origin/$LOCAL_BRANCH points at. The agent clones from GitHub, so an unpushed commit does not exist as far as it is concerned." \
    "git push origin $LOCAL_BRANCH"
  ok "$REPO at $(echo "$SHA" | cut -c1-12), pushed"
  ok "the agent will push to $BRANCH"
fi

# --- 3. dispatch -----------------------------------------------------------
LOG="${TMPDIR:-/tmp}/agentic-sdlc-dispatch-$(echo "$BRANCH" | tr '/' '-').log"

if [ "$DISPATCH" -eq 1 ]; then
  step "dispatch"
  PAYLOAD=$(python3 -c "
import json,sys
print(json.dumps({'repo': sys.argv[1], 'sha': sys.argv[2], 'branch': sys.argv[3]}))
" "$REPO" "$SHA" "$BRANCH")

  BODY=$(python3 -c "
import json,sys
print(json.dumps({
  'class_method': 'async_stream_query',
  'input': {'user_id': sys.argv[1], 'message': sys.argv[2]},
}))
" "${USER:-attendee}" "$PAYLOAD")

  APP="$HOST/reasoningEngines/v1/projects/$PROJECT_NUMBER/locations/$AGENT_ENGINE_LOCATION/reasoningEngines/$ENGINE/api"

  # Submit and return. The invocation is capped at ~600s and the cap is hard,
  # so the terminal is not held against it: the branch is what is followed.
  # Closing this connection does not stop the agent -- server-side work carries
  # on regardless, which is why the branch and not the stream is the display.
  curl -sS -N -X POST "$APP/api/stream_reasoning_engine" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "$BODY" > "$LOG" 2>&1 &
  DISPATCH_PID=$!
  ok "submitted (pid $DISPATCH_PID)"
  info "trajectory: $LOG"
  info "sessions:   https://console.cloud.google.com/vertex-ai/agents/agent-engines?project=$PROJECT"
  [ "$FOLLOW" -eq 1 ] || { info "not following; run --follow-only to watch the branch"; exit 0; }
fi

# --- 4. follow the branch --------------------------------------------------
# The branch, not the stream. The agent pushes every iteration, so this shows
# real progress and survives losing the connection -- which the stream does not.
step "following $BRANCH"
info "polling every 10s; ctrl-c stops watching, not the agent"

LAST=""
IDLE=0
while :; do
  REMOTE=$(git ls-remote origin "refs/heads/$BRANCH" 2>/dev/null | cut -f1)
  if [ -n "$REMOTE" ] && [ "$REMOTE" != "$LAST" ]; then
    git fetch -q origin "$BRANCH" 2>/dev/null
    if [ -n "$LAST" ]; then
      git log --oneline "$LAST..$REMOTE" 2>/dev/null | sed 's/^/  + /'
    else
      info "branch appeared at $(echo "$REMOTE" | cut -c1-12)"
      git log --oneline -1 "$REMOTE" 2>/dev/null | sed 's/^/  + /'
    fi
    LAST="$REMOTE"
    IDLE=0
  else
    IDLE=$((IDLE + 1))
  fi

  if [ "${DISPATCH_PID:-}" != "" ] && ! kill -0 "$DISPATCH_PID" 2>/dev/null; then
    step "the run has ended"
    if grep -q '"error"' "$LOG" 2>/dev/null; then
      printf '  %sthe invocation reported an error%s\n' "$RED" "$R"
      head -c 600 "$LOG" | sed 's/^/      /'
      info "whatever was pushed before it stopped is on $BRANCH -- that is why the agent pushes every iteration"
    fi
    [ -n "$LAST" ] && ok "$BRANCH is at $(echo "$LAST" | cut -c1-12)" || info "$BRANCH was never created"
    echo
    echo "  Review it, then merge when you are satisfied:"
    echo "      git fetch origin $BRANCH && git log origin/$BRANCH"
    echo "      git merge origin/$BRANCH"
    exit 0
  fi
  sleep 10
done
