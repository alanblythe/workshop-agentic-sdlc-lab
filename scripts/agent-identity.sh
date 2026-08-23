#!/usr/bin/env bash
#
# Agentic SDLC workshop: which identity the deployed agent actually runs as.
#
#   bash scripts/agent-identity.sh
#
# The deploy prints a gcp-sa-aiplatform-re service account whether or not
# --agent-identity worked, so it cannot answer this. spec.effectiveIdentity on
# the reasoning engine can, and there is no gcloud surface for that field.

set -uo pipefail

ENGINE_NAME="coder-agent"

: "${AGENT_ENGINE_LOCATION:?set AGENT_ENGINE_LOCATION to the region you deployed to}"

PROJECT=$(gcloud config get-value project 2>/dev/null)
[ -n "$PROJECT" ] || { echo "no active gcloud project" >&2; exit 1; }

TOKEN=$(gcloud auth print-access-token 2>/dev/null) ||
  { echo "gcloud is not authenticated, run: gcloud auth login" >&2; exit 1; }

API="https://${AGENT_ENGINE_LOCATION}-aiplatform.googleapis.com/v1"
BASE="${API}/projects/${PROJECT}/locations/${AGENT_ENGINE_LOCATION}/reasoningEngines"

ENGINE=$(curl -sS -H "Authorization: Bearer ${TOKEN}" "$BASE" | python3 -c "
import json, sys
engines = json.load(sys.stdin).get('reasoningEngines', [])
named = [e['name'] for e in engines if e.get('displayName') == '${ENGINE_NAME}']
if not named:
    sys.exit('no engine named ${ENGINE_NAME} in ${AGENT_ENGINE_LOCATION}, so nothing is deployed there yet')
print(named[0])
") || exit 1

curl -sS -H "Authorization: Bearer ${TOKEN}" "${API}/${ENGINE}" | python3 -c "
import json, sys
identity = json.load(sys.stdin).get('spec', {}).get('effectiveIdentity')
if not identity:
    sys.exit('the engine has no spec.effectiveIdentity, so it is running as a service account rather than its own')
print(identity)
"
