#!/usr/bin/env node
//
// Render each guide once per format.
//
//   npm install && npm run build
//
// One source, two dialects. The formats agree on Markdown and on `##` marking a
// step, and disagree about everything else -- metadata, durations, callouts,
// and, more importantly, about what the reader can be told to do. A codelab is
// read anywhere and must spell a command out; a Cloud Shell walkthrough renders
// beside the shell and can point at it. `{{#walkthrough}}` blocks are for that
// second kind of difference, which is the one no amount of markup translation
// would fix.
//
// Authoring-time only. Nothing an attendee runs depends on Node.

import Handlebars from "handlebars";
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { basename, join } from "node:path";

const SRC = "guides";
const FORMATS = {
  codelab: { ext: ".lab.md", label: "CLaaT codelab" },
  walkthrough: { ext: ".tutorial.md", label: "Cloud Shell walkthrough" },
};

// --- helpers ---------------------------------------------------------------
// Each one exists because the two formats spell the same idea differently.

// `## Title` plus the duration in the local dialect. claat reads `Duration: N`
// and drops unknown tags silently; Cloud Shell reads the tag and would render
// `Duration: N` as stray text.
Handlebars.registerHelper("step", function (title, minutes, options) {
  const fmt = options.data.root.format;
  const duration =
    fmt === "codelab"
      ? `Duration: ${minutes}`
      : `<walkthrough-tutorial-duration duration="${minutes}"></walkthrough-tutorial-duration>`;
  return new Handlebars.SafeString(`## ${title}\n\n${duration}\n`);
});

// The tutorial-level total, which Cloud Shell renders under the title. Summed
// from the step minutes so it cannot drift from them; a codelab gets its total
// from claat, which adds the per-step Durations itself.
Handlebars.registerHelper("tutorialDuration", function (options) {
  const { format, totalMinutes } = options.data.root;
  return format === "walkthrough"
    ? new Handlebars.SafeString(
        `<walkthrough-tutorial-duration duration="${totalMinutes}"></walkthrough-tutorial-duration>`,
      )
    : "";
});

// claat styles `> aside positive|negative`. Cloud Shell has no equivalent, so
// it gets a labelled blockquote -- readable, and it keeps the distinction.
Handlebars.registerHelper("aside", function (tone, options) {
  const fmt = options.data.root.format;
  const body = options.fn(this).trim();
  if (fmt === "codelab") {
    const quoted = body.split("\n").map((l) => (l ? `> ${l}` : ">")).join("\n");
    return new Handlebars.SafeString(`> aside ${tone}\n>\n${quoted}\n`);
  }
  const label = tone === "negative" ? "**Careful:**" : "**Tip:**";
  const quoted = body.split("\n").map((l) => (l ? `> ${l}` : ">")).join("\n");
  return new Handlebars.SafeString(`> ${label}\n>\n${quoted}\n`);
});

// The walkthrough can substitute the reader's real project; a codelab cannot.
// Bare, with no backticks: this is nearly always used inside a fenced block,
// where backticks would be printed rather than read as markup.
Handlebars.registerHelper("projectId", function (options) {
  return new Handlebars.SafeString(
    options.data.root.format === "walkthrough"
      ? "<walkthrough-project-id/>"
      : "YOUR_PROJECT_ID",
  );
});

Handlebars.registerHelper("codelab", function (options) {
  return this.format === "codelab" ? options.fn(this) : options.inverse(this);
});
Handlebars.registerHelper("walkthrough", function (options) {
  return this.format === "walkthrough" ? options.fn(this) : options.inverse(this);
});

// --- render ----------------------------------------------------------------
const sources = readdirSync(SRC).filter((f) => f.endsWith(".md.hbs"));
if (!sources.length) {
  console.error(`no *.md.hbs in ${SRC}/`);
  process.exit(1);
}

for (const src of sources) {
  const name = basename(src, ".md.hbs");
  const source = readFileSync(join(SRC, src), "utf8");
  const totalMinutes = [...source.matchAll(/\{\{step\s+"[^"]*"\s+(\d+)\s*\}\}/g)]
    .reduce((sum, m) => sum + Number(m[1]), 0);
  const template = Handlebars.compile(source, { noEscape: true });
  for (const [format, { ext, label }] of Object.entries(FORMATS)) {
    const out = name + ext;
    // Collapse the blank-line runs the conditionals leave behind.
    // Both outputs are committed -- claat compiles one, and Cloud Shell reads
    // the other straight out of the clone -- so each has to say where it came
    // from, or someone edits the output and loses it on the next build.
    const note = `<!-- Generated from ${SRC}/${src} by ${"npm run build"}. Do not edit. -->\n`;
    const body =
      note + template({ format, totalMinutes }).replace(/\n{3,}/g, "\n\n").replace(/^\n+/, "");
    writeFileSync(out, body);
    console.log(`  ${out.padEnd(28)} ${label}`);
  }
}
