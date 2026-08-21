#!/usr/bin/env bash
#
# Render the lab guide and publish it to the gh-pages branch.
#
#   bash scripts/publish.sh
#
# gh-pages rather than /docs: attendees fork main, and a built site in every
# fork is noise. The copy-button pass must follow every export -- `claat export`
# rewrites index.html wholesale.

set -euo pipefail
CLAAT="${CLAAT:-$HOME/go/bin/claat}"
OUT="${TMPDIR:-/tmp}/agentic-sdlc-pages"

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
echo "built into $OUT — publish with: git subtree/worktree push to gh-pages"
