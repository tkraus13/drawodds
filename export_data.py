#!/usr/bin/env python3
"""Export all parsed HuntRecord data as compact JSON for the web app.

Usage: python export_data.py
Output: docs/data.json (array-of-arrays format)
"""

import json
import sys
from pathlib import Path

from draw_odds import load_reports

COLUMNS = [
    ("year", "y"),
    ("hunt_code", "hc"),
    ("species", "sp"),
    ("unit_desc", "ud"),
    ("units", "u"),
    ("bag", "b"),
    ("licenses", "l"),
    ("total_1st", "t1"),
    ("total_2nd", "t2"),
    ("total_3rd", "t3"),
    ("res_1st", "r1"),
    ("res_2nd", "r2"),
    ("res_3rd", "r3"),
    ("nr_1st", "n1"),
    ("nr_2nd", "n2"),
    ("nr_3rd", "n3"),
    ("out_1st", "o1"),
    ("out_2nd", "o2"),
    ("out_3rd", "o3"),
    ("drawn_res", "dr1"),
    ("drawn_res_2nd", "dr2"),
    ("drawn_res_3rd", "dr3"),
    ("drawn_nr", "dn1"),
    ("drawn_nr_2nd", "dn2"),
    ("drawn_nr_3rd", "dn3"),
    ("drawn_out", "do1"),
    ("drawn_out_2nd", "do2"),
    ("drawn_out_3rd", "do3"),
    ("r_pct", "rp"),
    ("nr_pct", "np"),
    ("o_pct", "op"),
]


def main():
    data_dir = Path(__file__).parent
    out_path = data_dir / "docs" / "data.json"
    out_path.parent.mkdir(exist_ok=True)

    print("Loading all reports...", file=sys.stderr)
    records = load_reports(data_dir, year_filter=None, verbose=True)
    if not records:
        print("ERROR: No records loaded.", file=sys.stderr)
        sys.exit(1)

    header = [short for _, short in COLUMNS]
    rows = []
    for r in records:
        row = [getattr(r, long) for long, _ in COLUMNS]
        rows.append(row)

    data = [header] + rows
    with open(out_path, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    species = sorted({r.species for r in records})
    years = sorted({r.year for r in records})
    size_kb = out_path.stat().st_size / 1024

    print(f"\nExported {len(records)} records to {out_path}", file=sys.stderr)
    print(f"  Years: {years}", file=sys.stderr)
    print(f"  Species: {species}", file=sys.stderr)
    print(f"  File size: {size_kb:.0f} KB", file=sys.stderr)


if __name__ == "__main__":
    main()
