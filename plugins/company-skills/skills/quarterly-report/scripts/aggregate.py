#!/usr/bin/env python3
"""
aggregate.py — collapses a GL CSV into quarterly line items.

Deterministic. Same input, same output, every time. Skills should push
this kind of logic into scripts rather than describing it in prose:
Claude can read the prose and approximate, but accounting math should
not be approximated.

Usage:
    python aggregate.py path/to/gl.csv --quarter 3 --fy 2026
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date

# Account-range → category mapping. Mirror of references/gl-schema.md.
CATEGORY_RANGES = [
    (4000, 4999, "revenue"),
    (5000, 5999, "cost_of_revenue"),
    (6000, 7999, "operating_expenses"),
    (8000, 8999, "other"),
    (9000, 9999, "tax"),
]


def category_for(account_code: str) -> str | None:
    try:
        code = int(account_code)
    except ValueError:
        return None
    for low, high, cat in CATEGORY_RANGES:
        if low <= code <= high:
            return cat
    return None


def quarter_bounds(quarter: int, fy: int) -> tuple[date, date]:
    """Calendar-year fiscal calendar. Override for non-calendar fiscals."""
    starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    return date(fy, *starts[quarter]), date(fy, *ends[quarter])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--quarter", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--fy", type=int, required=True)
    args = parser.parse_args()

    start, end = quarter_bounds(args.quarter, args.fy)
    totals: dict[str, float] = defaultdict(float)

    with open(args.csv_path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                period = date.fromisoformat(row["period"])
            except (KeyError, ValueError):
                continue
            if not (start <= period <= end):
                continue
            cat = category_for(row.get("account_code", ""))
            if not cat:
                continue
            debit = float(row.get("debit") or 0)
            credit = float(row.get("credit") or 0)
            # Revenue accounts have natural credit balance; flip the sign.
            sign = -1 if cat == "revenue" else 1
            totals[cat] += sign * (debit - credit)

    gross_profit = totals["revenue"] - totals["cost_of_revenue"]
    operating_income = gross_profit - totals["operating_expenses"]
    net_income = operating_income + totals["other"] - totals["tax"]

    json.dump({
        "quarter": f"Q{args.quarter} FY{args.fy}",
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "totals": dict(totals),
        "derived": {
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "net_income": net_income,
        },
    }, sys.stdout, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
