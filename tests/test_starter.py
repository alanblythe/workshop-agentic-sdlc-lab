"""Tests for the starter itself.

The contract tests for the scorer are written during the lab and land beside
these.
"""

import csv
import io

from main import load_export

COLUMNS = ["account_id", "month", "seats_active", "logins", "tickets_open"]
ALWAYS_POPULATED = ["account_id", "month", "logins", "tickets_open"]


def rows() -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(load_export())))


def test_the_export_loads():
    assert load_export().startswith("account_id,")


def test_the_header_is_the_documented_one():
    assert next(csv.reader(io.StringIO(load_export()))) == COLUMNS


def test_required_columns_are_populated():
    for row in rows():
        for column in ALWAYS_POPULATED:
            assert row[column].strip(), f"{column} is blank in {row}"


def test_each_account_has_at_most_one_row_per_month():
    keys = [(r["account_id"], r["month"]) for r in rows()]
    assert len(keys) == len(set(keys))


def test_the_export_covers_a_month_with_no_seat_count():
    assert any(r["seats_active"].strip() == "" for r in rows())


def test_the_export_covers_an_account_with_a_single_month():
    counts: dict[str, int] = {}
    for r in rows():
        counts[r["account_id"]] = counts.get(r["account_id"], 0) + 1
    assert 1 in counts.values()
