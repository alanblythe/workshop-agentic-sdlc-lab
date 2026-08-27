#!/usr/bin/env node
//
// Add a copy button to every code block in an exported codelab.
//
//   node scripts/add-copy-buttons.mjs docs/*/index.html
//
// Done as a post-processing pass rather than a custom claat template on
// purpose: claat's own docs say the built-in templates "are not guaranteed to
// be stable", so a fork of one is a thing that silently drifts. Injecting after
// export touches only the output, and keeps working when claat changes.
//
// Idempotent -- re-running on an already-processed file changes nothing.

import { readFileSync, writeFileSync } from "node:fs";

const MARKER = "<!-- copy-buttons -->";

const SNIPPET = `${MARKER}
<style>
  .clab-copy-wrap { position: relative; }
  .clab-copy {
    position: absolute; top: 8px; right: 8px;
    font: 500 12px/1 Roboto, sans-serif; letter-spacing: .04em;
    padding: 6px 10px; border: 0; border-radius: 4px; cursor: pointer;
    color: #fff; background: rgba(255,255,255,.16);
    opacity: 0; transition: opacity .15s ease, background .15s ease;
  }
  .clab-copy-wrap:hover .clab-copy,
  .clab-copy:focus { opacity: 1; }
  .clab-copy:hover { background: rgba(255,255,255,.28); }
  .clab-copy[data-copied="1"] { background: #1e8e3e; opacity: 1; }
  @media (hover: none) { .clab-copy { opacity: 1; } }
</style>
<script>
(function () {
  function decorate(pre) {
    if (pre.parentElement && pre.parentElement.classList.contains("clab-copy-wrap")) return;
    var wrap = document.createElement("div");
    wrap.className = "clab-copy-wrap";
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);

    var button = document.createElement("button");
    button.className = "clab-copy";
    button.type = "button";
    button.textContent = "Copy";
    button.setAttribute("aria-label", "Copy code to clipboard");
    button.addEventListener("click", function () {
      var text = pre.innerText;
      var done = function () {
        button.textContent = "Copied";
        button.dataset.copied = "1";
        setTimeout(function () {
          button.textContent = "Copy";
          delete button.dataset.copied;
        }, 1600);
      };
      // A codelab is often read over http:// or from a file, where the async
      // clipboard API is unavailable; fall back rather than fail silently.
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done);
      } else {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); done(); } finally { ta.remove(); }
      }
    });
    wrap.appendChild(button);
  }

  function scan() {
    document.querySelectorAll("google-codelab-step pre").forEach(decorate);
  }

  // Steps are rendered by a custom element, so the blocks may not exist yet.
  scan();
  document.addEventListener("DOMContentLoaded", scan);
  window.addEventListener("load", scan);
  new MutationObserver(scan).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
})();
</script>
`;

let changed = 0;
for (const file of process.argv.slice(2)) {
  const html = readFileSync(file, "utf8");
  if (html.includes(MARKER)) {
    console.log(`  ${file}, already has copy buttons`);
    continue;
  }
  if (!html.includes("</body>")) {
    console.error(`  ${file}, no </body>, skipped`);
    continue;
  }
  writeFileSync(file, html.replace("</body>", `${SNIPPET}</body>`));
  console.log(`  ${file}, copy buttons added`);
  changed++;
}
console.log(`${changed} file(s) updated`);
