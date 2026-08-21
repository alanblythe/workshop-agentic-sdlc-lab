#!/usr/bin/env bash
#
# Agentic SDLC workshop, teardown.
#
# Removes everything the workshop created in your project and your fork, and
# nothing else. Run it at the end of the session.
#
#   bash scripts/teardown.sh          # show what would go, then ask
#   bash scripts/teardown.sh --yes    # no prompt
#   bash scripts/teardown.sh --dry-run
#
# Safe to run twice: anything already gone is reported and skipped.
#
# Deliberately not `terraform destroy`. The state file is local and gitignored,
# and you are plausibly in a fresh clone that has none, destroy would find an
# empty state, report no changes, delete nothing, and exit 0. Deleting by name
# works from anywhere.
#
# APIs are left enabled. Your project may well have been using them before the
# workshop, and turning them off is not ours to do.

set -uo pipefail

SECRET_ID="agentic-sdlc-deploy-key"
KEY_TITLE="agentic-sdlc coder agent"
ENGINE_NAME="coder-agent"
ASSUME_YES=0
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y)  ASSUME_YES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)         echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then B=$(printf '\033[1m'); R=$(printf '\033[0m'); RED=$(printf '\033[31m'); GRN=$(printf '\033[32m'); YEL=$(printf '\033[33m')
else B=""; R=""; RED=""; GRN=""; YEL=""; fi
step() { printf '\n%s== %s ==%s\n' "$B" "$1" "$R"; }
ok()   { printf '  %sremoved%s  %s\n' "$GRN" "$R" "$1"; }
skip() { printf '  --       %s\n' "$1"; }
warn() { printf '  %swarn%s     %s\n' "$YEL" "$R" "$1"; }
FAILED=0
fail() { printf '  %sFAIL%s     %s\n' "$RED" "$R" "$1"; }
would() { printf '  %swould%s    %s\n' "$YEL" "$R" "$1"; }

PROJECT=$(gcloud config get-value project 2>/dev/null)
[ -n "$PROJECT" ] && [ "$PROJECT" != "(unset)" ] || { echo "no active gcloud project" >&2; exit 1; }
# Never defaulted. Teardown querying the wrong region finds nothing and reports
# a clean project while the engine keeps running, which is the one thing this
# script exists to prevent.
LOCATION="${AGENT_ENGINE_LOCATION:-}"
[ -n "$LOCATION" ] || LOCATION=$(gcloud secrets describe agentic-sdlc-deploy-key \
  --format='value(replication.userManaged.replicas[0].location)' 2>/dev/null)
[ -n "$LOCATION" ] || die "AGENT_ENGINE_LOCATION is not set and could not be read back from the deploy-key secret" \
  'export AGENT_ENGINE_LOCATION=<the region you deployed to>' 
TOKEN=$(gcloud auth print-access-token 2>/dev/null)
[ -n "$TOKEN" ] || { echo "not authenticated, run: gcloud auth login" >&2; exit 1; }
API="https://${LOCATION}-aiplatform.googleapis.com/v1"
BASE="${API}/projects/${PROJECT}/locations/${LOCATION}/reasoningEngines"

# --- what is actually there ------------------------------------------------
# Matched by name, never by wildcard: a project may hold agents that are not
# ours, and this must not be the script that removed one of them.
ENGINES=$(curl -sS -H "Authorization: Bearer $TOKEN" "$BASE" 2>/dev/null | python3 -c "
import json,sys
try: data = json.load(sys.stdin)
except Exception: data = {}
for e in data.get('reasoningEngines', []):
    if e.get('displayName') == '$ENGINE_NAME':
        print(e['name'])
" 2>/dev/null)

SECRET_EXISTS=0
gcloud secrets describe "$SECRET_ID" --project="$PROJECT" >/dev/null 2>&1 && SECRET_EXISTS=1

REPO=""
KEY_IDS=""
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  ORIGIN=$(git remote get-url origin 2>/dev/null)
  REPO=$(printf '%s' "$ORIGIN" | sed -E 's#^git@github\.com:##; s#^ssh://git@github\.com/##; s#^https://[^/]*github\.com/##; s#\.git$##')
  case "$REPO" in
    */*) KEY_IDS=$(gh repo deploy-key list --repo "$REPO" --json id,title \
                     -q ".[] | select(.title == \"$KEY_TITLE\") | .id" 2>/dev/null) ;;
    *)   REPO="" ;;
  esac
fi

step "what will be removed"
[ -n "$ENGINES" ] && for e in $ENGINES; do echo "  agent      ${e##*/} ($ENGINE_NAME, in $PROJECT)"; done || skip "no deployed $ENGINE_NAME agent"
[ "$SECRET_EXISTS" -eq 1 ] && echo "  secret     $SECRET_ID (in $PROJECT)" || skip "no $SECRET_ID secret"
[ -n "$KEY_IDS" ] && for k in $KEY_IDS; do echo "  deploy key $k on $REPO"; done || skip "no deploy key titled '$KEY_TITLE'"
echo
echo "  APIs stay enabled, and your branches and commits are untouched."

if [ -z "$ENGINES" ] && [ "$SECRET_EXISTS" -eq 0 ] && [ -z "$KEY_IDS" ]; then
  step "nothing to do"
  echo "  Already torn down."
  exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
  step "dry run"
  [ -n "$ENGINES" ] && for e in $ENGINES; do would "delete agent ${e##*/}"; done
  [ "$SECRET_EXISTS" -eq 1 ] && would "delete secret $SECRET_ID"
  [ -n "$KEY_IDS" ] && for k in $KEY_IDS; do would "delete deploy key $k"; done
  echo; echo "  Nothing was changed."
  exit 0
fi

if [ "$ASSUME_YES" -eq 0 ]; then
  printf '\n  Type %syes%s to remove these: ' "$B" "$R"
  read -r answer
  [ "$answer" = "yes" ] || { echo "  Nothing was changed."; exit 1; }
fi

# --- remove ----------------------------------------------------------------
# The deploy key first. It is the only item here that grants anyone anything,
# so if the run is interrupted it should be the part already gone.
step "removing"

if [ -n "$KEY_IDS" ]; then
  for k in $KEY_IDS; do
    if gh repo deploy-key delete "$k" --repo "$REPO" >/dev/null 2>&1; then
      ok "deploy key $k from $REPO"
    else
      FAILED=$((FAILED + 1))
      fail "could not delete deploy key $k, do it at https://github.com/$REPO/settings/keys"
    fi
  done
fi

# force=true is required, not optional. An engine that has ever been invoked
# holds sessions, and deleting one with children is refused:
#   FAILED_PRECONDITION: contains child resources: sessions
# Every run of this lab produces sessions, so without force this fails for
# everyone. The recorded trajectory goes with the engine, which is the point.
# Deleting the engine also takes its Agent Identity; no principal is left over.
for e in $ENGINES; do
  BODY=$(curl -sS -w '\n%{http_code}' -X DELETE \
    -H "Authorization: Bearer $TOKEN" "${API}/${e}?force=true" 2>/dev/null)
  CODE=$(printf '%s' "$BODY" | tail -1)
  case "$CODE" in
    200|202) ok "agent ${e##*/} and its sessions (deletion started)" ;;
    404)     skip "agent ${e##*/} was already gone" ;;
    *)       FAILED=$((FAILED + 1))
             fail "agent ${e##*/} returned HTTP $CODE: $(printf '%s' "$BODY" | sed -n 's/.*"message": *"\([^"]*\)".*/\1/p' | head -1)" ;;
  esac
done

if [ "$SECRET_EXISTS" -eq 1 ]; then
  if gcloud secrets delete "$SECRET_ID" --project="$PROJECT" --quiet >/dev/null 2>&1; then
    ok "secret $SECRET_ID and every version of it"
  else
    FAILED=$((FAILED + 1))
    fail "could not delete $SECRET_ID, try: gcloud secrets delete $SECRET_ID --project=$PROJECT"
  fi
fi

if [ "$FAILED" -gt 0 ]; then
  step "$FAILED item(s) could not be removed"
  echo "  Something above is still there, and may still be billing or still"
  echo "  grant access. Fix the failures and run this again, it is safe to."
  exit 1
fi

step "done"
echo "  Nothing from the workshop is running or billing."
echo
echo "  Left alone on purpose:"
echo "    - the APIs, which your project may have been using already"
echo "    - your fork, your branches, and the agent's commits"
echo
echo "  Preflight recreates the secret if you run the lab again."
