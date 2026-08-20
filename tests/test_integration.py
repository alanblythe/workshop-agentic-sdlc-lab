"""Both halves, after they are merged. Neither party can run this alone."""

from main import load_export
from usage import parse_usage, score

EXPECTED = {
    "acme": (10, "HEALTHY", []),
    "globex": (6, "MEDIUM", ["seats down sharply"]),
    "hooli": (10, "HEALTHY", []),
    "initech": (5, "MEDIUM", ["low engagement", "unresolved support load"]),
    "umbrella": (10, "HEALTHY", []),
    "vandelay": (6, "MEDIUM", ["seats down sharply"]),
}


def test_the_two_halves_compose():
    scored = {
        account: (r.score, r.tier, r.reasons)
        for account, months in parse_usage(load_export()).items()
        for r in [score(months)]
    }
    assert scored == EXPECTED
