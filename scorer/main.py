"""Entry point for the account health scorer.

This module owns the file read. The scorer is a pure function over the export's
text, so both halves of it stay testable without touching the filesystem.
"""

from __future__ import annotations

from pathlib import Path

FIXTURE = Path(__file__).parent.parent / "fixtures" / "usage.csv"


def load_export(path: Path | str = FIXTURE) -> str:
    """Return the usage export as text."""
    return Path(path).read_text(encoding="utf-8")


def main() -> None:
    text = load_export()
    rows = [line for line in text.splitlines()[1:] if line.strip()]
    accounts = sorted({line.split(",", 1)[0] for line in rows})

    try:
        from usage import parse_usage, score
    except ImportError:
        print(f"{len(rows)} rows, {len(accounts)} accounts: {', '.join(accounts)}")
        print("No scorer yet. Implement parse_usage and score in scorer/usage.py.")
        return

    for account, months in sorted(parse_usage(text).items()):
        result = score(months)
        reasons = ", ".join(result.reasons) or "-"
        print(f"{account:<10} {result.score:>2}  {result.tier:<8} {reasons}")


if __name__ == "__main__":
    main()
