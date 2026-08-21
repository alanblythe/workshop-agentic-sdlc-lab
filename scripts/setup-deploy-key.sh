#!/usr/bin/env bash
#
# Agentic SDLC workshop, deploy key setup.
#
# Run this from your fork, on the day. It generates an SSH key, gives it write
# access to this one repository, and puts the private half into the Secret
# Manager secret your preflight created. The deployed agent reads it from
# there; you never handle it again.
#
#   bash scripts/setup-deploy-key.sh
#
# Safe to re-run: it revokes the previous key before adding a new one, so the
# repository never accumulates keys.
#
#   --help   this text
#
# Blast radius is one repository by construction. The key is not an account
# credential, has no scopes, and is not visible to any other repo you own.

set -uo pipefail

# The same fixed string terraform/locals.tf uses in the front-door repo. Day-of
# steps run in a different clone of a different repository and cannot read that
# state, so both ends hard-code the name.
SECRET_ID="agentic-sdlc-deploy-key"
KEY_TITLE="agentic-sdlc coder agent"
PROBE_REF="refs/heads/deploy-key-check"

case "${1:-}" in
  --help|-h) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
  "")        ;;
  *)         echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
esac

if [ -t 1 ]; then B=$(printf '\033[1m'); R=$(printf '\033[0m'); RED=$(printf '\033[31m'); GRN=$(printf '\033[32m')
else B=""; R=""; RED=""; GRN=""; fi

step() { printf '\n%s== %s ==%s\n' "$B" "$1" "$R"; }
ok()   { printf '  %sok%s    %s\n' "$GRN" "$R" "$1"; }
info() { printf '  --    %s\n' "$1"; }
die() {
  # die "<what is wrong>" "<command that fixes it>"
  printf '\n  %sFAIL%s  %s\n\n    %s\n\n' "$RED" "$R" "$1" "$2" >&2
  exit 1
}

have() { command -v "$1" >/dev/null 2>&1; }

# --- 1. tools --------------------------------------------------------------
step "tools"

have gh        || die "gh is not installed" 'brew install gh    # or https://cli.github.com'
have gcloud    || die "gcloud is not installed" 'https://cloud.google.com/sdk/docs/install'
have git       || die "git is not installed" 'xcode-select --install    # macOS'
have ssh-keygen || die "ssh-keygen is not installed" 'install openssh-client'
gh auth status >/dev/null 2>&1 || die "gh is not authenticated" 'gh auth login'
ok "gh, gcloud, git, ssh-keygen"

# --- 2. the fork -----------------------------------------------------------
# Resolved from origin rather than by letting gh pick. A clone that also has an
# upstream remote makes `gh repo view` ambiguous, and gh resolves that by
# PROMPTING, which hangs a lab step that is meant to be one command.
step "your fork"

ORIGIN=$(git remote get-url origin 2>/dev/null)
[ -n "$ORIGIN" ] || die "no 'origin' remote here, run this from your clone of your fork" \
  'gh repo fork alanblythe/workshop-agentic-sdlc-lab --clone'

REPO=$(printf '%s' "$ORIGIN" | sed -E 's#^git@github\.com:##; s#^ssh://git@github\.com/##; s#^https://[^/]*github\.com/##; s#\.git$##')
case "$REPO" in
  */*/*|*/) die "cannot read an owner/repo out of origin ($ORIGIN)" "git remote set-url origin git@github.com:YOUR_USER/workshop-agentic-sdlc-lab.git" ;;
  */*) ;;
  *)   die "cannot read an owner/repo out of origin ($ORIGIN)" "git remote set-url origin git@github.com:YOUR_USER/workshop-agentic-sdlc-lab.git" ;;
esac

PERM=$(gh repo view "$REPO" --json viewerPermission -q .viewerPermission 2>/dev/null)
[ "$PERM" = "ADMIN" ] || die "you do not have admin on $REPO (you have '${PERM:-no access}'), so you cannot add a deploy key to it. This is what a clone of the upstream looks like, fork it first, then work in the fork." \
  "gh repo fork alanblythe/workshop-agentic-sdlc-lab --clone"
ok "$REPO, you have admin"

# --- 3. the secret ---------------------------------------------------------
# The container is Terraform's, made by preflight a week ago. This script only
# adds a version to it, so a missing secret means preflight never ran.
step "secret manager"

PROJECT=$(gcloud config get-value project 2>/dev/null)
[ -n "$PROJECT" ] && [ "$PROJECT" != "(unset)" ] || die "no active gcloud project" 'gcloud config set project YOUR_PROJECT_ID'

gcloud secrets describe "$SECRET_ID" --project="$PROJECT" >/dev/null 2>&1 \
  || die "secret '$SECRET_ID' does not exist in $PROJECT. Terraform creates it, from the other repository, during preflight." \
    'cd ../workshop-agentic-sdlc && AGENT_ENGINE_LOCATION=us-central1 MODEL_LOCATION=global bash scripts/preflight.sh'
ok "$SECRET_ID exists in $PROJECT"

# --- 4. generate -----------------------------------------------------------
# In a temp directory, never ~/.ssh: this key belongs to the agent, not to you,
# and leaving a copy on the machine is one more thing to remember to delete.
step "generate"

KEYDIR=$(mktemp -d) || die "could not create a temporary directory" 'check that TMPDIR is writable'
chmod 700 "$KEYDIR"
trap 'rm -rf "$KEYDIR"' EXIT INT TERM
KEY="$KEYDIR/id_ed25519"

# No passphrase: nothing in the container can type one.
ssh-keygen -t ed25519 -N '' -C "$KEY_TITLE ($REPO)" -f "$KEY" -q \
  || die "ssh-keygen failed" "ssh-keygen -t ed25519 -N '' -f $KEY"
# GNU stat first: on Linux `-f` means *filesystem*, so it exits 0 with a garbage
# mode and the fallback never fires. BSD stat rejects `-c` outright, so this
# order is the one that works on both. ssh refuses a key looser than 0600 and
# says so in terms of file modes, naming no credential.
MODE=$(stat -c '%a' "$KEY" 2>/dev/null || stat -f '%Lp' "$KEY" 2>/dev/null)
[ "$MODE" = "600" ] || die "the generated key is mode ${MODE:-unknown}, and ssh refuses anything looser than 600" \
  "chmod 600 $KEY"
ok "ed25519 key, mode $MODE"

# --- 5. install on the fork ------------------------------------------------
# Deleting first is what makes a re-run safe. Without it a second run leaves the
# first key live, and revoking later means guessing which of two is in the
# secret.
step "install on $REPO"

OLD=$(gh repo deploy-key list --repo "$REPO" --json id,title -q ".[] | select(.title == \"$KEY_TITLE\") | .id" 2>/dev/null)
for id in $OLD; do
  gh repo deploy-key delete "$id" --repo "$REPO" >/dev/null 2>&1 && info "revoked the previous key (id $id)"
done

gh repo deploy-key add "$KEY.pub" --title "$KEY_TITLE" --allow-write --repo "$REPO" >/dev/null \
  || die "could not add the deploy key to $REPO" \
    "gh repo deploy-key add $KEY.pub --title '$KEY_TITLE' --allow-write --repo $REPO"
ok "added with write access"

# --- 6. prove it works -----------------------------------------------------
# The same mechanism the agent uses: an explicit key, strict host checking left
# ON, and a pinned known_hosts. IdentitiesOnly=yes is the load-bearing option, # without it ssh offers your own agent's keys first, and the check passes on
# your credentials rather than on the deploy key.
step "verify"

ssh-keyscan -t rsa,ecdsa,ed25519 github.com > "$KEYDIR/known_hosts" 2>/dev/null
[ -s "$KEYDIR/known_hosts" ] || die "could not fetch github.com's host keys" 'check your network, then re-run'

export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o UserKnownHostsFile=$KEYDIR/known_hosts -o StrictHostKeyChecking=yes"

git clone --depth 1 "git@github.com:$REPO.git" "$KEYDIR/clone" >/dev/null 2>&1 \
  || die "the key cannot clone $REPO over SSH. GitHub takes a few seconds to propagate a new deploy key, wait and re-run." \
    "GIT_SSH_COMMAND='$GIT_SSH_COMMAND' git clone git@github.com:$REPO.git /tmp/keycheck"
ok "clone over SSH, no StrictHostKeyChecking=no anywhere"

# A read-only key is refused here, at receive-pack, before anything is sent.
# --dry-run makes that a real authorization check that leaves no ref behind.
if ! PUSH=$(git -C "$KEYDIR/clone" push --dry-run origin "HEAD:$PROBE_REF" 2>&1); then
  case "$PUSH" in
    *"read only"*|*"read-only"*) die "the key was added without write access. GitHub answers a read-only key here and only here: it clones perfectly and is refused at receive-pack." \
      "bash scripts/setup-deploy-key.sh    # re-run; it revokes and re-adds with --allow-write" ;;
    *) die "the deploy key cannot push to $REPO:
$(printf '%s' "$PUSH" | sed 's/^/      /')" \
      "gh repo deploy-key list --repo $REPO" ;;
  esac
fi
ok "push accepted, the key has write access"

# --- 7. hand it to the agent -----------------------------------------------
step "secret manager"

gcloud secrets versions add "$SECRET_ID" --data-file="$KEY" --project="$PROJECT" >/dev/null 2>&1 \
  || die "could not add a version to $SECRET_ID" \
    "gcloud secrets versions add $SECRET_ID --data-file=<key> --project=$PROJECT"
VERSION=$(gcloud secrets versions list "$SECRET_ID" --project="$PROJECT" --limit=1 --format='value(name)' 2>/dev/null)
ok "written as version ${VERSION:-latest}"

# Every earlier version holds a key that was revoked from the repository a
# moment ago. The agent reads `latest` and would never see them, but leaving
# them enabled means teardown has to reason about which key is live.
for v in $(gcloud secrets versions list "$SECRET_ID" --project="$PROJECT" \
             --filter='state:ENABLED' --format='value(name)' 2>/dev/null); do
  [ "$v" = "$VERSION" ] && continue
  gcloud secrets versions disable "$v" --secret="$SECRET_ID" --project="$PROJECT" >/dev/null 2>&1 \
    && info "disabled version $v, its key is already revoked"
done

step "done"
echo "  The agent reads:"
echo "      projects/$PROJECT/secrets/$SECRET_ID/versions/latest"
echo "  and pushes to:"
echo "      git@github.com:$REPO.git"
echo
echo "  Nothing was left on this machine. To revoke, delete the key titled"
echo "  '$KEY_TITLE' from $REPO, that alone is enough."
