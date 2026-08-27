#!/usr/bin/env node
//
// Turn marked `###` headings in an exported codelab into collapsed sections.
//
//   node scripts/collapse-sections.mjs docs/*/index.html
//
// claat drops <details> and <summary> from the markdown and keeps only the
// text inside, so a collapsible cannot be written in the source. This wraps
// them after export, the same way the copy buttons are added, and for the same
// reason: claat's templates are explicitly not stable, so forking one drifts.
//
// The marker is a leading U+25B8 on a `###` heading, which the build helper
// emits for the codelab format only. Without this pass the page still reads
// correctly -- the sections are simply open, with a stray triangle.
//
// Idempotent -- re-running on an already-processed file changes nothing.

import { readFileSync, writeFileSync } from "node:fs";

const MARKER = "<!-- collapse-sections -->";
const STYLE = `${MARKER}
<style>
  details.clab-fold { margin: 16px 0; border-top: 1px solid #dadce0; }
  details.clab-fold > summary {
    cursor: pointer; list-style: none; padding: 12px 0;
    font: 500 16px/1.4 Roboto, sans-serif; color: #202124;
  }
  details.clab-fold > summary::-webkit-details-marker { display: none; }
  details.clab-fold > summary::before {
    content: "\\25B8"; display: inline-block; width: 1.2em;
    color: #5f6368; transition: transform .15s ease;
  }
  details.clab-fold[open] > summary::before { transform: rotate(90deg); }
  details.clab-fold > summary:hover { color: #1a73e8; }
</style>
`;

const file = process.argv[2];
if (!file) {
  console.error("usage: collapse-sections.mjs <index.html>");
  process.exit(2);
}

let html = readFileSync(file, "utf8");
if (html.includes(MARKER)) {
  console.log(`  ${file}, already collapsed`);
  process.exit(0);
}

// A marked heading owns everything up to the next heading of any level or the
// end of its step, whichever comes first.
const HEAD = /<h2 is-upgraded>▸\s*([\s\S]*?)<\/h2>/g;
let count = 0;
let out = "";
let cursor = 0;
let m;
while ((m = HEAD.exec(html)) !== null) {
  const bodyStart = m.index + m[0].length;
  const nextHead = html.indexOf("<h2", bodyStart);
  const endStep = html.indexOf("</google-codelab-step>", bodyStart);
  const end = Math.min(...[nextHead, endStep].filter((n) => n !== -1));
  const body = html.slice(bodyStart, end);
  out += html.slice(cursor, m.index);
  out += `<details class="clab-fold"><summary>${m[1]}</summary>${body}</details>`;
  cursor = end;
  count += 1;
  HEAD.lastIndex = end;
}
out += html.slice(cursor);

if (!count) {
  console.log(`  ${file}, no marked sections`);
  process.exit(0);
}

out = out.replace("</head>", `${STYLE}</head>`);
writeFileSync(file, out);
console.log(`  ${file}, ${count} section(s) collapsed`);
