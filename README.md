# Account health scorer

Reads a monthly usage export and reports, per account, a health score, a tier,
and the reasons behind it.

This is the lab repository for the Agentic SDLC workshop. **Fork it**, the
workshop guide tells you when.

- `docs/spec.md`, the draft specification
- `main.py`, reads the export; neither half of the scorer touches the file
- `fixtures/usage.csv`, sample export
- `scripts/setup-deploy-key.sh`, gives the coding agent write access to your
  fork. The guide says when; running it early does no harm and no good

Setup and prerequisites live in the other repository,
[workshop-agentic-sdlc](https://github.com/alanblythe/workshop-agentic-sdlc).
Run its preflight before the session.
