"""The parsing half, alone. Does not import score().

Every expectation here traces to a rule in docs/spec.md:
  - an empty seats_active means the month was not measured, so it produces no
    MonthSnapshot
  - each account's months are in ascending order
  - an account with no months to score is omitted
"""

from main import load_export
from usage import MonthSnapshot, parse_usage

EXPECTED = {
    "acme": [
        MonthSnapshot("acme", "2026-01", 10, 5, 0),
        MonthSnapshot("acme", "2026-02", 8, 5, 0),
        # 2026-03 has no seat count recorded, so it is not a snapshot.
    ],
    "globex": [
        MonthSnapshot("globex", "2026-01", 4, 5, 0),
        MonthSnapshot("globex", "2026-02", 10, 5, 0),
        MonthSnapshot("globex", "2026-03", 6, 5, 0),
    ],
    "hooli": [
        MonthSnapshot("hooli", "2026-01", 12, 40, 0),
        MonthSnapshot("hooli", "2026-02", 12, 45, 1),
    ],
    "initech": [
        MonthSnapshot("initech", "2026-01", 6, 4, 0),
        MonthSnapshot("initech", "2026-02", 6, 2, 3),
    ],
    "umbrella": [
        MonthSnapshot("umbrella", "2026-02", 3, 10, 0),
    ],
    "vandelay": [
        MonthSnapshot("vandelay", "2026-01", 10, 5, 0),
        MonthSnapshot("vandelay", "2026-02", 6, 5, 0),
        MonthSnapshot("vandelay", "2026-03", 5, 5, 0),
    ],
}


def test_parse_produces_exactly_these_snapshots():
    assert parse_usage(load_export()) == EXPECTED


def test_months_are_in_ascending_order():
    for months in parse_usage(load_export()).values():
        assert [m.month for m in months] == sorted(m.month for m in months)


def test_an_unmeasured_month_produces_no_snapshot():
    acme = parse_usage(load_export())["acme"]
    assert [m.month for m in acme] == ["2026-01", "2026-02"]
