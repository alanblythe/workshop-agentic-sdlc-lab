# Spec template

What a spec has to contain before anyone writes code. Every section is
required. A section with nothing under it is not a spec that is small, it is a
question nobody has asked yet.

**Status:** `Draft` while the spec is being argued over, `Approved` once it is
buildable. Nothing is dispatched against a Draft.

## What this does

The problem, and why it matters now. Two or three sentences.

## Input

What arrives, in what shape, and what is guaranteed about it. Everything a
builder would otherwise have to assume.

## The two halves

The interface. The types and signatures each side is written against, so two people
can build from this independently and their code will fit.

## Rules

The behaviour, stated as rules a builder follows rather than as intentions.

## Out of scope

What this deliberately does not do. A boundary to point at when somebody asks
for one more thing.

## Decisions

One row per ambiguity resolved. The id is what a contract test cites, so an
assertion citing nothing is a guess rather than a requirement.

| ID | Rule a builder follows | Passage it resolves | Case that would differ |
| --- | --- | --- | --- |

## Open questions

Everything still undecided, and what will collide because of it.

## The gate

Code starts when all three hold:

- **Status** is `Approved`
- **Open questions** is empty
- Every rule, in Rules and in Decisions, is one a builder could follow without
  asking anybody

A spec that has every section and fails the gate is the normal case, not a
broken one. Sections are cheap. The gate is the part that costs something.
