# Account health scoring

**Status:** Draft

## What this does

Customer Success needs to know an account is in trouble before the cancellation
email arrives. This reads the monthly usage export, gives each account a health
score, puts it in a tier, and names the reasons, so CS can work a list rather
than a hunch.

## Input

The usage export is a CSV with one row per account per month:

```
account_id,month,seats_active,logins,tickets_open
```

| Column | Meaning |
| --- | --- |
| `account_id` | Stable identifier for the account |
| `month` | The month the row covers, as `YYYY-MM` |
| `seats_active` | The number of seats used that month |
| `logins` | Total logins across the account that month |
| `tickets_open` | Support tickets still open at the end of the month |

The first line is the header shown above. `account_id`, `month`, `logins` and
`tickets_open` are always present and never blank. Rows may appear in any order, and each account has at most one row per
month.

## The two halves

The work splits at a single data structure. One half turns the export into
snapshots; the other half scores them and never sees the CSV.

```python
@dataclass(frozen=True)
class MonthSnapshot:
    account_id: str
    month: str          # "YYYY-MM"
    seats_active: int
    logins: int
    tickets_open: int
```

```python
def parse_usage(csv_text: str) -> dict[str, list[MonthSnapshot]]:
    """Group the export text by account, each list in ascending month order.

    An account with no months to score is omitted, so score() is never
    called with an empty list.
    """

def score(months: list[MonthSnapshot]) -> Result:
    """Score one account's months. Never reads the CSV."""
```

```python
@dataclass(frozen=True)
class Result:
    score: int
    tier: str           # "HEALTHY" | "MEDIUM" | "AT RISK"
    reasons: list[str]
```

`main.py` opens the file and hands its contents to `parse_usage`. Neither half
touches the filesystem, so both stay pure functions over their inputs.

## Scoring

Every account starts at **10**. Each rule below deducts once, at most. The score
is floored at 0. It never goes negative.

| Rule | Deduction | Reason string |
| --- | --- | --- |
| The latest month's seat count has fallen by 40% or more | −4 | `seats down sharply` |
| Fewer than 3 logins in the latest month | −3 | `low engagement` |
| 2 or more tickets open in the latest month | −2 | `unresolved support load` |

**The latest month** is the most recent month present for that account.

`reasons` lists the reason strings for the rules that fired, in the order the
rules appear in the table above. An account with no rules fired has an empty
`reasons` list.

The seat-decline rule needs at least two months to compare. An account with only
one month in the export does not fire it, and cannot lose those 4 points.

## Tiers

| Tier | Score |
| --- | --- |
| `HEALTHY` | 8–10 |
| `MEDIUM` | 5–7 |
| `AT RISK` | 0–4 |

Any account scoring 5 or below should be surfaced to CS as at risk, so the
weekly digest is built from that set.

## Out of scope

Alerting, the digest itself, and anything that writes back to the CRM. This
produces the score and nothing else.

## Decisions

| ID | Rule a builder follows | Passage it resolves | Case that would differ |
| --- | --- | --- | --- |

## Open questions

None.
