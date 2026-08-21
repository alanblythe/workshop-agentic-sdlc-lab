#!/usr/bin/env bash
#
# Render the lab guide and publish it to the gh-pages branch.
#
#   bash scripts/publish.sh            # build, commit and push
#   bash scripts/publish.sh --build    # build only, change no branch
#
# gh-pages rather than /docs: attendees fork main, and a built site in every
# fork is noise. The copy-button pass must follow every export -- `claat export`
# rewrites index.html wholesale.

set -euo pipefail
CLAAT="${CLAAT:-$HOME/go/bin/claat}"
command -v "$CLAAT" >/dev/null 2>&1 || { echo "claat not found at $CLAAT — set CLAAT=/path/to/claat" >&2; exit 1; }
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT="${TMPDIR:-/tmp}/agentic-sdlc-pages"

BUILD_ONLY=0
case "${1:-}" in
  --build) BUILD_ONLY=1 ;;
  "")      ;;
  *)       echo "unknown argument: $1" >&2; exit 2 ;;
esac

cd "$REPO_ROOT"
npm run build --silent
rm -rf "$OUT" && mkdir -p "$OUT"
"$CLAAT" export -o "$OUT" lab.lab.md
node scripts/add-copy-buttons.mjs "$OUT"/agentic-sdlc-lab/index.html
touch "$OUT/.nojekyll"
cat > "$OUT/index.html" <<'HTML'
<!doctype html>
<meta charset="utf-8">
<title>The agentic SDLC lab</title>
<meta http-equiv="refresh" content="0; url=./agentic-sdlc-lab/">
<link rel="canonical" href="./agentic-sdlc-lab/">
<p>Redirecting to <a href="./agentic-sdlc-lab/">the lab</a>.</p>
HTML

if [ "$BUILD_ONLY" -eq 1 ]; then
  echo "built into $OUT — nothing published"
  exit 0
fi

# A worktree created and destroyed per run. A long-lived one accumulates ways
# to be wrong: its .git pointer breaks when the repo moves, and a checkout left
# behind blocks the next `worktree add` for the same branch.
WT=$(mktemp -d "${TMPDIR:-/tmp}/ghpages.XXXXXX")
cleanup() { git worktree remove --force "$WT" 2>/dev/null || rm -rf "$WT"; }
trap cleanup EXIT

git fetch -q origin gh-pages
# -B off origin: the branch is a publishing target, so what is live is the only
# sensible base. Anything local and divergent is not worth preserving.
git worktree add -q -B gh-pages "$WT" origin/gh-pages
rsync -a --delete --exclude '.git' "$OUT"/ "$WT"/

if git -C "$WT" diff --quiet && git -C "$WT" diff --cached --quiet && [ -z "$(git -C "$WT" ls-files --others --exclude-standard)" ]; then
  echo "gh-pages already matches this build — nothing to publish"
  exit 0
fi

git -C "$WT" add -A
git -C "$WT" commit -q -m "Publish $(git rev-parse --short HEAD)"
git -C "$WT" push -q origin gh-pages
echo "published https://alanblythe.github.io/workshop-agentic-sdlc-lab/agentic-sdlc-lab/ from $(git rev-parse --short HEAD)"
