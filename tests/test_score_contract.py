"""The scoring half, alone. Does not import parse_usage() and never reads a file.

The MonthSnapshot lists below are written out longhand on purpose: that longhand
list is the seam, and writing it here is what lets this half be built and tested
before the other one exists.

Every expectation traces to a rule in docs/spec.md:
  - 10 points, minus 4 seats / 3 logins / 2 tickets, floored at 0
  - the seat rule compares the latest month against the highest month present
  - it needs at least two months, so a single-month account cannot fire it
  - reasons appear in the order the rules are listed
  - HEALTHY 8-10, MEDIUM 5-7, AT RISK 0-4
"""

from usage import MonthSnapshot, score


def test_steady_account_scores_full_marks():
    months = [
        MonthSnapshot("hooli", "2026-01", 12, 40, 0),
        MonthSnapshot("hooli", "2026-02", 12, 45, 1),
    ]
    result = score(months)
    assert (result.score, result.tier, result.reasons) == (10, "HEALTHY", [])


def test_seats_down_against_the_highest_month_fires():
    # Highest is 10 in 2026-02, latest is 6. (10-6)/10 = 40%, which is "or more".
    months = [
        MonthSnapshot("globex", "2026-01", 4, 5, 0),
        MonthSnapshot("globex", "2026-02", 10, 5, 0),
        MonthSnapshot("globex", "2026-03", 6, 5, 0),
    ]
    result = score(months)
    assert (result.score, result.tier, result.reasons) == (
        6, "MEDIUM", ["seats down sharply"],
    )


def test_seats_down_is_not_measured_against_the_previous_month():
    # Previous month is 6 and latest is 5, a 17% fall. Against the highest of 10
    # it is 50%, so the rule fires.
    months = [
        MonthSnapshot("vandelay", "2026-01", 10, 5, 0),
        MonthSnapshot("vandelay", "2026-02", 6, 5, 0),
        MonthSnapshot("vandelay", "2026-03", 5, 5, 0),
    ]
    result = score(months)
    assert (result.score, result.tier, result.reasons) == (
        6, "MEDIUM", ["seats down sharply"],
    )


def test_a_mild_decline_does_not_fire():
    # Highest 10, latest 8: a 20% fall, under the 40% threshold.
    months = [
        MonthSnapshot("acme", "2026-01", 10, 5, 0),
        MonthSnapshot("acme", "2026-02", 8, 5, 0),
    ]
    result = score(months)
    assert (result.score, result.tier, result.reasons) == (10, "HEALTHY", [])


def test_a_single_month_cannot_fire_the_seat_rule():
    months = [MonthSnapshot("umbrella", "2026-02", 3, 10, 0)]
    result = score(months)
    assert (result.score, result.tier, result.reasons) == (10, "HEALTHY", [])


def test_the_tier_boundary_at_five():
    # 10 - 3 (logins) - 2 (tickets) = 5. Seats are steady, so that rule is silent.
    months = [
        MonthSnapshot("initech", "2026-01", 6, 4, 0),
        MonthSnapshot("initech", "2026-02", 6, 2, 3),
    ]
    result = score(months)
    assert result.score == 5
    assert result.tier == "MEDIUM"
    assert result.reasons == ["low engagement", "unresolved support load"]
