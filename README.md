# Account health scorer

Reads a monthly usage export and reports, per account, a health score, a tier,
and the reasons behind it.

This is the lab repository for the Agentic SDLC workshop. **Fork it**, the
workshop guide tells you when.

- [`docs/spec.md`](docs/spec.md), the draft specification
- [`docs/adk-eval-implementation.md`](docs/adk-eval-implementation.md), guide and key file references for the ADK eval implementation
- [`scorer/main.py`](scorer/main.py), reads the export; neither half of the scorer touches the file
- [`fixtures/usage.csv`](fixtures/usage.csv), sample export
- [`scripts/setup-deploy-key.sh`](scripts/setup-deploy-key.sh), gives the coding agent write access to your
  fork. The guide says when; running it early does no harm and no good

Setup and prerequisites live in the other repository,
[workshop-agentic-sdlc](https://github.com/alanblythe/workshop-agentic-sdlc).
Run its preflight before the session.
