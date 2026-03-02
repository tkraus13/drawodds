#!/usr/bin/env python3
"""
NM Big Game Draw Odds Analyzer
Parses NMDGF drawing odds reports (2022-2025) to rank hunts by draw odds.

Usage:
  python draw_odds.py --species elk
  python draw_odds.py --species elk,deer --hunter-type nonresident
  python draw_odds.py --unit 34
  python draw_odds.py --unit 34,16 --species elk
  python draw_odds.py --species elk --top 20 --sort avg_odds
  python draw_odds.py --list-species
  python draw_odds.py --species deer --csv > deer_odds.csv

Notes:
  - Draw odds are shown per choice tier: 1st, 2nd, and 3rd choice
  - Each tier: (drawn via Nth choice) / (applicants who listed as Nth choice)
  - "Avg 1st" = average 1st-choice odds across loaded years (default: 2025 only; use --year all for multi-year)
  - Hunt success rates are not included in NMDGF draw odds reports; odds here are
    draw odds only. Layer in harvest success data manually if needed.
  - 2021 report excluded (different schema).
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import openpyxl

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

DATA_DIR = Path(__file__).parent


# ─── Column layout configs ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ColConfig:
    """Zero-based column indices for one report-year layout."""
    hunt_code: int
    unit_desc: int
    bag: int
    licenses: int
    # Pre-draw: applicant counts per hunter category, by choice tier
    total_1st: int
    total_2nd: int
    total_3rd: int
    res_1st: int
    res_2nd: int
    res_3rd: int
    nr_1st: int
    nr_2nd: int
    nr_3rd: int
    out_1st: int
    out_2nd: int
    out_3rd: int
    # Post-draw: drawn via each choice path.
    # drawn/applied using same choice tier gives true per-tier odds.
    drawn_res: int      # residents drawn via 1st choice
    drawn_res_2nd: int  # residents drawn via 2nd choice
    drawn_res_3rd: int  # residents drawn via 3rd choice
    drawn_nr: int
    drawn_nr_2nd: int
    drawn_nr_3rd: int
    drawn_out: int
    drawn_out_2nd: int
    drawn_out_3rd: int
    # Actual distribution percentages from the report
    r_pct: int
    nr_pct: int
    o_pct: int


# Column layout notes:
#
# Each choice tier (1st/2nd/3rd) has its own applicant count AND its own drawn count.
# Per-tier odds = drawn_via_Nth / applied_as_Nth — apples-to-apples comparison.
#
# 2022 pre-draw (no "T" subtotal per group):
#   Hunt-Total: 4=1st, 5=2nd, 6=3rd
#   Resident:   7=1st, 8=2nd, 9=3rd
#   NR:        10=1st,11=2nd,12=3rd
#   Outfitter: 13=1st,14=2nd,15=3rd
#   spacer at 16
# 2022 post-draw:
#   Hunt-Total drawn: 19=1st,20=2nd,21=3rd,22=4th,23=T
#   Resident drawn:   24=1st,25=2nd,26=3rd,27=4th,28=T
#   NR drawn:         29=1st,30=2nd,31=3rd,32=4th,33=T
#   Outfitter drawn:  34=1st,35=2nd,36=3rd,37=4th,38=T
#   Distribution:     39=R%,40=NR%,41=O%,42=T%
_COL_2022 = ColConfig(
    hunt_code=0, unit_desc=1, bag=2, licenses=3,
    total_1st=4,  total_2nd=5,  total_3rd=6,
    res_1st=7,    res_2nd=8,    res_3rd=9,
    nr_1st=10,    nr_2nd=11,    nr_3rd=12,
    out_1st=13,   out_2nd=14,   out_3rd=15,
    drawn_res=24, drawn_res_2nd=25, drawn_res_3rd=26,
    drawn_nr=29,  drawn_nr_2nd=30,  drawn_nr_3rd=31,
    drawn_out=34, drawn_out_2nd=35, drawn_out_3rd=36,
    r_pct=39, nr_pct=40, o_pct=41,
)

# 2023-2025 pre-draw (adds "T" subtotal after each group, shifts res/NR/out right by 1):
#   Hunt-Total: 4=1st, 5=2nd, 6=3rd, 7=T
#   Resident:   8=1st, 9=2nd,10=3rd,11=T
#   NR:        12=1st,13=2nd,14=3rd,15=T
#   Outfitter: 16=1st,17=2nd,18=3rd,19=T
#   spacer at 20
# 2023-2025 post-draw:
#   Category totals: 24=Res,25=NR,26=Out,27=T
#   Resident drawn:  28=1st,29=2nd,30=3rd,31=4th,32=T
#   NR drawn:        33=1st,34=2nd,35=3rd,36=4th,37=T
#   Outfitter drawn: 38=1st,39=2nd,40=3rd,41=4th,42=T
#   Distribution:    43=R%,44=NR%,45=O%,46=T%
_COL_2023_PLUS = ColConfig(
    hunt_code=0, unit_desc=1, bag=2, licenses=3,
    total_1st=4,  total_2nd=5,  total_3rd=6,
    res_1st=8,    res_2nd=9,    res_3rd=10,
    nr_1st=12,    nr_2nd=13,    nr_3rd=14,
    out_1st=16,   out_2nd=17,   out_3rd=18,
    drawn_res=28, drawn_res_2nd=29, drawn_res_3rd=30,
    drawn_nr=33,  drawn_nr_2nd=34,  drawn_nr_3rd=35,
    drawn_out=38, drawn_out_2nd=39, drawn_out_3rd=40,
    r_pct=43, nr_pct=44, o_pct=45,
)

YEAR_CONFIGS: Dict[int, ColConfig] = {
    2022: _COL_2022,
    2023: _COL_2023_PLUS,
    2024: _COL_2023_PLUS,
    2025: _COL_2023_PLUS,
}

# NMDGF renamed "ANTELOPE" to "PRONGHORN" starting in 2023.
SPECIES_NORMALIZE = {
    "ANTELOPE": "PRONGHORN",
}

_HUNT_CODE_RE = re.compile(r'^[A-Z]{2,6}-\d+-\d+$')

# ─── Hunt type mapping (user-friendly name → species + bag codes) ─────────────
# Used by --strategy to let users say "bull elk" instead of --species elk + manual
# bag filtering.  Keys are lowercase.  Values are (SPECIES, [bag_codes]).
HUNT_TYPES = {
    # Elk
    "bull elk":             ("ELK", ["MB"]),
    "mature bull elk":      ("ELK", ["MB"]),
    "any elk":              ("ELK", ["A"]),
    "either sex elk":       ("ELK", ["ES"]),
    "cow elk":              ("ELK", ["ES"]),
    "antlerless elk":       ("ELK", ["APRE/6", "APRE/6/A"]),
    # Deer
    "fork antlered deer":           ("DEER", ["FAD"]),
    "fork antlered mule deer":      ("DEER", ["FAMD"]),
    "fork antlered whitetail deer": ("DEER", ["FAWTD"]),
    "either sex whitetail deer":    ("DEER", ["ESWTD"]),
    "any deer":                     ("DEER", ["A"]),
    "mule deer":                    ("DEER", ["FAD", "FAMD"]),
    "whitetail deer":               ("DEER", ["FAWTD", "ESWTD"]),
    # Pronghorn
    "buck pronghorn":           ("PRONGHORN", ["MB"]),
    "mature buck pronghorn":    ("PRONGHORN", ["MB"]),
    "either sex pronghorn":     ("PRONGHORN", ["ES"]),
    "doe pronghorn":            ("PRONGHORN", ["F-IM"]),
    # Barbary sheep
    "barbary sheep":            ("BARBARY SHEEP", ["ES", "F-IM"]),
    "barbary ram":              ("BARBARY SHEEP", ["ES"]),
    "barbary ewe":              ("BARBARY SHEEP", ["F-IM"]),
    # Bighorn sheep
    "bighorn ram":              ("BIGHORN SHEEP", ["RAM"]),
    "bighorn ewe":              ("BIGHORN SHEEP", ["EWE"]),
    "bighorn sheep":            ("BIGHORN SHEEP", ["RAM", "EWE"]),
    # Ibex
    "ibex":                     ("IBEX", ["ES", "F-IM"]),
    # Javelina
    "javelina":                 ("JAVELINA", ["ES"]),
    # Oryx
    "oryx":                     ("ORYX", ["ES", "BHO"]),
}
_SKIP_LABELS = frozenset({
    "Hunt", "Hunt Code", "SPECIES HUNT INFORMATION", "SPECIES",
    "Pre-Draw Applicants", "Post-Draw Successful Applicants",
    "Pre-Draw Applicant Information", "Post-Draw Successful Applicant Information",
})


# ─── Data model ────────────────────────────────────────────────────────────────

@dataclass
class HuntRecord:
    year: int
    hunt_code: str
    species: str
    unit_desc: str
    units: List[str]    # parsed GMU numbers as strings
    bag: str
    licenses: int
    # Pre-draw applicant counts by choice tier
    total_1st: int
    total_2nd: int
    total_3rd: int
    res_1st: int
    res_2nd: int
    res_3rd: int
    nr_1st: int
    nr_2nd: int
    nr_3rd: int
    out_1st: int
    out_2nd: int
    out_3rd: int
    # Post-draw successful draws by choice tier
    drawn_res: int
    drawn_res_2nd: int
    drawn_res_3rd: int
    drawn_nr: int
    drawn_nr_2nd: int
    drawn_nr_3rd: int
    drawn_out: int
    drawn_out_2nd: int
    drawn_out_3rd: int
    r_pct: float
    nr_pct: float
    o_pct: float

    def draw_odds(self, hunter_type: str, choice: int = 1) -> Optional[float]:
        """
        Draw odds as a percentage for this hunter type and choice tier.
        Formula: (hunters who drew via Nth choice) / (hunters who applied as Nth choice)
        Returns None if no applicants in that category/choice.
        """
        if choice == 1:
            if hunter_type == "resident":
                apps, drawn = self.res_1st, self.drawn_res
            elif hunter_type == "nonresident":
                apps, drawn = self.nr_1st, self.drawn_nr
            elif hunter_type == "outfitter":
                apps, drawn = self.out_1st, self.drawn_out
            else:
                apps  = self.total_1st
                drawn = self.drawn_res + self.drawn_nr + self.drawn_out
        elif choice == 2:
            if hunter_type == "resident":
                apps, drawn = self.res_2nd, self.drawn_res_2nd
            elif hunter_type == "nonresident":
                apps, drawn = self.nr_2nd, self.drawn_nr_2nd
            elif hunter_type == "outfitter":
                apps, drawn = self.out_2nd, self.drawn_out_2nd
            else:
                apps  = self.total_2nd
                drawn = self.drawn_res_2nd + self.drawn_nr_2nd + self.drawn_out_2nd
        elif choice == 3:
            if hunter_type == "resident":
                apps, drawn = self.res_3rd, self.drawn_res_3rd
            elif hunter_type == "nonresident":
                apps, drawn = self.nr_3rd, self.drawn_nr_3rd
            elif hunter_type == "outfitter":
                apps, drawn = self.out_3rd, self.drawn_out_3rd
            else:
                apps  = self.total_3rd
                drawn = self.drawn_res_3rd + self.drawn_nr_3rd + self.drawn_out_3rd
        else:
            return None

        if apps <= 0:
            return None
        return min(round(drawn / apps * 100, 1), 100.0)


@dataclass
class AggregatedHunt:
    hunt_code: str
    species: str
    unit_desc: str
    units: List[str]
    bag: str
    latest_year: int
    licenses: int
    type_licenses: int           # licenses allocated to the active hunter type
    latest_applicants: int       # 1st-choice apps in latest year (hunter-type-specific)
    latest_applicants_2nd: int   # 2nd-choice apps in latest year
    latest_applicants_3rd: int   # 3rd-choice apps in latest year
    latest_odds: Optional[float]
    latest_odds_2nd: Optional[float]
    latest_odds_3rd: Optional[float]
    avg_odds: Optional[float]    # average 1st-choice odds across all loaded years
    year_count: int


# ─── XLSX parsing ──────────────────────────────────────────────────────────────

def _clean(val) -> str:
    """Strip whitespace and non-breaking spaces."""
    if isinstance(val, str):
        return val.replace('\xa0', '').strip()
    return str(val).strip() if val is not None else ''


def _int(row: list, col: int) -> int:
    if col >= len(row) or row[col] is None:
        return 0
    try:
        return int(row[col])
    except (ValueError, TypeError):
        return 0


def _float(row: list, col: int) -> float:
    if col >= len(row) or row[col] is None:
        return 0.0
    try:
        return float(row[col])
    except (ValueError, TypeError):
        return 0.0


def _species_from_row(row: list) -> Optional[str]:
    """
    If row[0] is a species section header, return the normalized species name.
    Species headers are fully uppercase, not a hunt code, and not a known label.
    """
    val = _clean(row[0]) if row[0] is not None else ''
    if not val or val in _SKIP_LABELS:
        return None
    if _HUNT_CODE_RE.match(val):
        return None
    # Species headers are ALL CAPS with at least one letter
    if val == val.upper() and re.search(r'[A-Z]', val):
        return SPECIES_NORMALIZE.get(val, val)
    return None


def _parse_units(unit_desc: str) -> List[str]:
    """Extract GMU numbers from descriptions like 'Units 2, 7, 9, 10 youth only'."""
    return re.findall(r'\d+', unit_desc)


def parse_xlsx(filepath: Path, year: int) -> List[HuntRecord]:
    """Parse one NMDGF drawing odds report and return HuntRecord objects."""
    cfg = YEAR_CONFIGS.get(year)
    if cfg is None:
        return []

    records: List[HuntRecord] = []
    current_species = "UNKNOWN"

    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active

    for row_vals in ws.iter_rows(values_only=True):
        row = list(row_vals)

        # Detect species section headers (e.g. "ELK", "PRONGHORN")
        species = _species_from_row(row)
        if species is not None:
            current_species = species
            continue

        # Skip blank rows and non-data rows
        if not row or row[0] is None:
            continue
        val0 = _clean(row[0])
        if not _HUNT_CODE_RE.match(val0):
            continue

        unit_desc = ''
        if cfg.unit_desc < len(row) and row[cfg.unit_desc] is not None:
            unit_desc = _clean(row[cfg.unit_desc])

        bag = ''
        if cfg.bag < len(row) and row[cfg.bag] is not None:
            bag = _clean(row[cfg.bag])

        records.append(HuntRecord(
            year=year,
            hunt_code=val0,
            species=current_species,
            unit_desc=unit_desc,
            units=_parse_units(unit_desc),
            bag=bag,
            licenses=_int(row, cfg.licenses),
            total_1st=_int(row, cfg.total_1st),
            total_2nd=_int(row, cfg.total_2nd),
            total_3rd=_int(row, cfg.total_3rd),
            res_1st=_int(row, cfg.res_1st),
            res_2nd=_int(row, cfg.res_2nd),
            res_3rd=_int(row, cfg.res_3rd),
            nr_1st=_int(row, cfg.nr_1st),
            nr_2nd=_int(row, cfg.nr_2nd),
            nr_3rd=_int(row, cfg.nr_3rd),
            out_1st=_int(row, cfg.out_1st),
            out_2nd=_int(row, cfg.out_2nd),
            out_3rd=_int(row, cfg.out_3rd),
            drawn_res=_int(row, cfg.drawn_res),
            drawn_res_2nd=_int(row, cfg.drawn_res_2nd),
            drawn_res_3rd=_int(row, cfg.drawn_res_3rd),
            drawn_nr=_int(row, cfg.drawn_nr),
            drawn_nr_2nd=_int(row, cfg.drawn_nr_2nd),
            drawn_nr_3rd=_int(row, cfg.drawn_nr_3rd),
            drawn_out=_int(row, cfg.drawn_out),
            drawn_out_2nd=_int(row, cfg.drawn_out_2nd),
            drawn_out_3rd=_int(row, cfg.drawn_out_3rd),
            r_pct=_float(row, cfg.r_pct),
            nr_pct=_float(row, cfg.nr_pct),
            o_pct=_float(row, cfg.o_pct),
        ))

    wb.close()
    return records


def load_reports(
    data_dir: Path,
    year_filter: Optional[List[int]] = None,
    verbose: bool = True,
) -> List[HuntRecord]:
    """Load all valid XLSX reports. Silently skips 2021 (incompatible schema)."""
    all_records: List[HuntRecord] = []
    for xlsx in sorted(data_dir.glob("*.xlsx")):
        m = re.search(r'(20\d\d)', xlsx.name)
        if not m:
            continue
        year = int(m.group(1))
        if year == 2021 or year not in YEAR_CONFIGS:
            continue
        if year_filter and year not in year_filter:
            continue
        recs = parse_xlsx(xlsx, year)
        all_records.extend(recs)
        if verbose:
            print(f"  [{year}] {len(recs):>4} hunt codes  ← {xlsx.name}", file=sys.stderr)
    return all_records


# ─── Filtering ─────────────────────────────────────────────────────────────────

def filter_species(records: List[HuntRecord], species_list: List[str]) -> List[HuntRecord]:
    """Case-insensitive substring match. 'elk' matches 'ELK', 'ROCKY MTN ELK', etc."""
    out = []
    for r in records:
        for s in species_list:
            if s.upper() in r.species.upper():
                out.append(r)
                break
    return out


def filter_units(records: List[HuntRecord], units: List[str]) -> List[HuntRecord]:
    """Keep records whose unit description contains at least one requested GMU number."""
    return [r for r in records if any(u in r.units for u in units)]


# ─── Aggregation ───────────────────────────────────────────────────────────────

def aggregate(records: List[HuntRecord], hunter_type: str) -> List[AggregatedHunt]:
    """
    Group by hunt code. For each hunt code, compute:
    - latest_odds: draw odds from the most recent report year
    - avg_odds:    average draw odds across all available years
    """
    groups: Dict[str, List[HuntRecord]] = defaultdict(list)
    for r in records:
        groups[r.hunt_code].append(r)

    results: List[AggregatedHunt] = []
    for hunt_code, recs in groups.items():
        recs.sort(key=lambda r: r.year)
        latest = recs[-1]

        all_odds = [r.draw_odds(hunter_type) for r in recs]
        valid_odds = [o for o in all_odds if o is not None]
        avg_odds = round(sum(valid_odds) / len(valid_odds), 1) if valid_odds else None

        if hunter_type == "resident":
            latest_apps     = latest.res_1st
            latest_apps_2nd = latest.res_2nd
            latest_apps_3rd = latest.res_3rd
            type_licenses   = round(latest.licenses * latest.r_pct / 100)
        elif hunter_type == "nonresident":
            latest_apps     = latest.nr_1st
            latest_apps_2nd = latest.nr_2nd
            latest_apps_3rd = latest.nr_3rd
            type_licenses   = round(latest.licenses * latest.nr_pct / 100)
        elif hunter_type == "outfitter":
            latest_apps     = latest.out_1st
            latest_apps_2nd = latest.out_2nd
            latest_apps_3rd = latest.out_3rd
            type_licenses   = round(latest.licenses * latest.o_pct / 100)
        else:
            latest_apps     = latest.total_1st
            latest_apps_2nd = latest.total_2nd
            latest_apps_3rd = latest.total_3rd
            type_licenses   = latest.licenses

        results.append(AggregatedHunt(
            hunt_code=hunt_code,
            species=latest.species,
            unit_desc=latest.unit_desc,
            units=latest.units,
            bag=latest.bag,
            latest_year=latest.year,
            licenses=latest.licenses,
            type_licenses=type_licenses,
            latest_applicants=latest_apps,
            latest_applicants_2nd=latest_apps_2nd,
            latest_applicants_3rd=latest_apps_3rd,
            latest_odds=latest.draw_odds(hunter_type, choice=1),
            latest_odds_2nd=latest.draw_odds(hunter_type, choice=2),
            latest_odds_3rd=latest.draw_odds(hunter_type, choice=3),
            avg_odds=avg_odds,
            year_count=len(recs),
        ))

    return results


# ─── Display ───────────────────────────────────────────────────────────────────

def _fmt_odds(val: Optional[float]) -> str:
    return f"{val:.1f}%" if val is not None else "N/A"


def _sort_hunts(hunts: List[AggregatedHunt], sort_by: str) -> List[AggregatedHunt]:
    if sort_by == "avg_odds":
        return sorted(hunts, key=lambda h: h.avg_odds if h.avg_odds is not None else -1, reverse=True)
    if sort_by == "licenses":
        return sorted(hunts, key=lambda h: h.licenses, reverse=True)
    if sort_by == "unit":
        return sorted(hunts, key=lambda h: h.unit_desc)
    # default: latest_odds
    return sorted(hunts, key=lambda h: h.latest_odds if h.latest_odds is not None else -1, reverse=True)


def display_table(
    hunts: List[AggregatedHunt],
    hunter_type: str,
    sort_by: str,
    top: int,
    num_years: int,
) -> None:
    if not hunts:
        print("No matching hunts found.")
        return

    hunts = _sort_hunts(hunts, sort_by)
    if top > 0:
        hunts = hunts[:top]

    type_abbr = {"resident": "Res", "nonresident": "NR", "outfitter": "Out", "total": "Tot"}
    lic_label = f"{type_abbr.get(hunter_type, hunter_type.title())} Lic"

    headers = [
        "#", "Hunt Code", "Species", "Unit / Description",
        "Bag", lic_label,
        "1st Choice", "1st Odds",
        "2nd Choice", "2nd Odds",
        "3rd Choice", "3rd Odds",
        "Yr",
        f"Avg 1st ({num_years}yr)",
    ]

    rows = []
    for i, h in enumerate(hunts, 1):
        rows.append([
            i,
            h.hunt_code,
            h.species.title(),
            h.unit_desc[:40],
            h.bag,
            h.type_licenses if h.type_licenses > 0 else "—",
            h.latest_applicants     if h.latest_applicants     > 0 else "—",
            _fmt_odds(h.latest_odds),
            h.latest_applicants_2nd if h.latest_applicants_2nd > 0 else "—",
            _fmt_odds(h.latest_odds_2nd),
            h.latest_applicants_3rd if h.latest_applicants_3rd > 0 else "—",
            _fmt_odds(h.latest_odds_3rd),
            h.latest_year,
            _fmt_odds(h.avg_odds),
        ])

    if HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))
    else:
        # Simple fallback formatter
        col_w = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
        fmt = "  ".join(f"{{:<{w}}}" for w in col_w)
        print(fmt.format(*headers))
        print("─" * (sum(col_w) + 2 * (len(headers) - 1)))
        for row in rows:
            print(fmt.format(*[str(x) for x in row]))

    print(f"\n  {len(hunts)} hunt(s) | hunter-type: {hunter_type} | sorted by: {sort_by}")
    if not HAS_TABULATE:
        print("  Tip: pip install tabulate for better table formatting")


def output_csv(hunts: List[AggregatedHunt], hunter_type: str) -> None:
    """Write results as CSV to stdout (redirect with > to save to file)."""
    writer = csv.writer(sys.stdout)
    writer.writerow([
        "hunt_code", "species", "unit_desc", "bag",
        "total_licenses", f"{hunter_type}_licenses",
        f"{hunter_type}_1st_apps",
        f"{hunter_type}_2nd_apps",
        f"{hunter_type}_3rd_apps",
        "1st_odds_pct", "2nd_odds_pct", "3rd_odds_pct",
        "avg_1st_odds_pct", "years_of_data",
    ])
    for h in hunts:
        writer.writerow([
            h.hunt_code, h.species, h.unit_desc, h.bag,
            h.licenses, h.type_licenses,
            h.latest_applicants,
            h.latest_applicants_2nd,
            h.latest_applicants_3rd,
            f"{h.latest_odds:.1f}"     if h.latest_odds     is not None else "",
            f"{h.latest_odds_2nd:.1f}" if h.latest_odds_2nd is not None else "",
            f"{h.latest_odds_3rd:.1f}" if h.latest_odds_3rd is not None else "",
            f"{h.avg_odds:.1f}"        if h.avg_odds        is not None else "",
            h.year_count,
        ])


def list_species(records: List[HuntRecord]) -> None:
    """Print all unique species found in the loaded reports."""
    species_years: Dict[str, set] = defaultdict(set)
    for r in records:
        species_years[r.species].add(r.year)
    print("\nSpecies available in loaded reports:")
    for sp in sorted(species_years):
        yrs = sorted(species_years[sp])
        print(f"  {sp.title():<30} (years: {', '.join(str(y) for y in yrs)})")


def list_hunt_types() -> None:
    """Print all valid --strategy hunt type names."""
    print("\nAvailable hunt types for --strategy:")
    by_species: Dict[str, List[str]] = defaultdict(list)
    for name, (species, bags) in HUNT_TYPES.items():
        by_species[species].append(f"  {name:<35} (bag: {', '.join(bags)})")
    for species in sorted(by_species):
        print(f"\n  {species}")
        print(f"  {'─' * 50}")
        for line in sorted(by_species[species]):
            print(line)
    print("\nUsage: python draw_odds.py --strategy \"bull elk\"")
    print("       python draw_odds.py --strategy \"fork antlered deer\" --unit 34")


def filter_bag(records: List[HuntRecord], bags: List[str]) -> List[HuntRecord]:
    """Keep records whose bag code matches any of the given bags.

    Matches via exact equality OR component overlap when splitting on '/'.
    This handles: exact 'APRE/6' match, plus combo codes like MB/A matching
    either 'MB' or 'A' as individual components.
    """
    bag_set = set(bags)
    return [r for r in records
            if r.bag in bag_set or bag_set & set(r.bag.split("/"))]


def filter_youth(records: List[HuntRecord], include: bool) -> List[HuntRecord]:
    """Exclude youth-only hunts unless include is True."""
    if include:
        return records
    return [r for r in records if "youth" not in r.unit_desc.lower()]


def display_strategy(
    records: List[HuntRecord],
    hunt_type_name: str,
    species: str,
    bags: List[str],
    hunter_type: str,
    top: int,
) -> None:
    """Show the top N hunts per choice tier to maximize draw odds."""
    # Get the latest year for each hunt code
    latest: Dict[str, HuntRecord] = {}
    for r in records:
        if r.hunt_code not in latest or r.year > latest[r.hunt_code].year:
            latest[r.hunt_code] = r

    recs = list(latest.values())
    if not recs:
        print("No matching hunts found for that strategy.")
        return

    year = max(r.year for r in recs)
    bag_label = ", ".join(bags)
    type_label = hunter_type.title()

    print(f"\n{'═' * 70}")
    print(f"  DRAW STRATEGY: {hunt_type_name.title()}")
    print(f"  {species.title()} (bag: {bag_label}) | {type_label} | {year}")
    print(f"{'═' * 70}")

    for choice, choice_label in [(1, "1st"), (2, "2nd"), (3, "3rd")]:
        # Build (hunt_code, odds, record) tuples
        ranked = []
        for r in recs:
            odds = r.draw_odds(hunter_type, choice)
            if odds is not None and odds > 0:
                if hunter_type == "resident":
                    apps = [r.res_1st, r.res_2nd, r.res_3rd][choice - 1]
                elif hunter_type == "nonresident":
                    apps = [r.nr_1st, r.nr_2nd, r.nr_3rd][choice - 1]
                elif hunter_type == "outfitter":
                    apps = [r.out_1st, r.out_2nd, r.out_3rd][choice - 1]
                else:
                    apps = [r.total_1st, r.total_2nd, r.total_3rd][choice - 1]
                ranked.append((odds, apps, r))

        ranked.sort(key=lambda x: x[0], reverse=True)
        shown = ranked[:top]

        print(f"\n  ── Best {choice_label} Choice Options ──")

        if not shown:
            print("  No hunts with draws in this tier.")
            continue

        headers = ["#", "Hunt Code", "Unit / Description", "Bag", "Licenses", "Apps", "Draw %"]
        rows = []
        for i, (odds, apps, r) in enumerate(shown, 1):
            rows.append([
                i,
                r.hunt_code,
                r.unit_desc[:38],
                r.bag,
                r.licenses,
                apps,
                f"{odds:.1f}%",
            ])

        if HAS_TABULATE:
            print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))
        else:
            col_w = [max(len(str(r[j])) for r in [headers] + rows) for j in range(len(headers))]
            fmt = "  ".join(f"{{:<{w}}}" for w in col_w)
            print(f"  {fmt.format(*headers)}")
            print(f"  {'─' * (sum(col_w) + 2 * (len(headers) - 1))}")
            for row in rows:
                print(f"  {fmt.format(*[str(x) for x in row])}")

    print(f"\n  Tip: Combine with --unit to narrow by GMU (e.g. --unit 34)")
    print(f"       Use --year all to see multi-year trends")
    print()


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="NM Big Game Draw Odds Analyzer (2022-2025 reports)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--species", "-s",
        help="Species to filter by (comma-separated). E.g.: elk  deer  pronghorn  bear",
    )
    parser.add_argument(
        "--unit", "-u",
        help="GMU number(s) to filter by (comma-separated). E.g.: 34  or  16,17,34",
    )
    parser.add_argument(
        "--hunter-type", "-t",
        choices=["resident", "nonresident", "outfitter", "total"],
        default="resident",
        help="Hunter category for odds calculation (default: resident)",
    )
    parser.add_argument(
        "--year", "-y",
        default="2025",
        help="Report year(s) to include: 2022-2025, comma-separated, or 'all' (default: 2025)",
    )
    parser.add_argument(
        "--sort",
        choices=["latest_odds", "avg_odds", "licenses", "unit"],
        default="latest_odds",
        help="Column to sort by (default: latest_odds)",
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=25,
        help="Show top N results; 0 = all (default: 25)",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output CSV to stdout instead of a table",
    )
    parser.add_argument(
        "--strategy",
        help='Hunt type to optimize draws for. E.g.: "bull elk", "fork antlered deer"',
    )
    parser.add_argument(
        "--include-youth",
        action="store_true",
        help="Include youth-only hunts (excluded by default)",
    )
    parser.add_argument(
        "--list-species",
        action="store_true",
        help="List all species found in the reports and exit",
    )
    parser.add_argument(
        "--list-types",
        action="store_true",
        help="List all valid --strategy hunt type names and exit",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help=f"Directory containing XLSX files (default: script directory)",
    )

    args = parser.parse_args()

    # --list-types needs no data
    if args.list_types:
        list_hunt_types()
        return

    if not args.list_species and not args.species and not args.unit and not args.strategy:
        parser.error("Provide --species, --unit, --strategy, or --list-species / --list-types")

    # Parse year filter
    year_filter: Optional[List[int]] = None
    if args.year != "all":
        try:
            year_filter = [int(y.strip()) for y in args.year.split(",")]
        except ValueError:
            parser.error(f"Invalid --year value: {args.year!r}. Use e.g. 2025 or 2023,2024")

    # Load reports
    print(f"\nLoading reports from {args.data_dir} ...", file=sys.stderr)
    records = load_reports(args.data_dir, year_filter)
    if not records:
        print("ERROR: No records loaded. Check --data-dir or year filter.", file=sys.stderr)
        sys.exit(1)

    available_years = sorted({r.year for r in records})
    print(f"  Years: {available_years} | Total hunt records: {len(records)}", file=sys.stderr)

    # Youth filter (applied before all other filters)
    records = filter_youth(records, args.include_youth)
    if not args.include_youth:
        print(f"  Excluding youth-only hunts: {len(records)} remaining", file=sys.stderr)

    # --list-species shortcut
    if args.list_species:
        list_species(records)
        return

    # --strategy mode
    if args.strategy:
        key = args.strategy.strip().lower()
        if key not in HUNT_TYPES:
            print(f"ERROR: Unknown hunt type: {args.strategy!r}", file=sys.stderr)
            print("  Use --list-types to see valid options.", file=sys.stderr)
            sys.exit(1)
        strategy_species, strategy_bags = HUNT_TYPES[key]
        records = filter_species(records, [strategy_species])
        records = filter_bag(records, strategy_bags)
        print(f"  Strategy: {args.strategy} → {strategy_species}, bag={strategy_bags}", file=sys.stderr)
        if args.unit:
            unit_list = [u.strip() for u in args.unit.split(",") if u.strip()]
            records = filter_units(records, unit_list)
            print(f"  After --unit ({', '.join(unit_list)}): {len(records)} records", file=sys.stderr)
        if not records:
            print("\nNo hunts match that strategy + filters.", file=sys.stderr)
            sys.exit(0)
        print(f"  Matching hunt records: {len(records)}\n", file=sys.stderr)
        strategy_top = args.top if args.top != 25 else 3
        display_strategy(records, args.strategy, strategy_species, strategy_bags,
                         args.hunter_type, strategy_top)
        return

    # Apply filters
    if args.species:
        sp_list = [s.strip() for s in args.species.split(",") if s.strip()]
        records = filter_species(records, sp_list)
        print(f"  After --species ({', '.join(sp_list)}): {len(records)} records", file=sys.stderr)

    if args.unit:
        unit_list = [u.strip() for u in args.unit.split(",") if u.strip()]
        records = filter_units(records, unit_list)
        print(f"  After --unit ({', '.join(unit_list)}): {len(records)} records", file=sys.stderr)

    if not records:
        print("\nNo hunts match your filters.", file=sys.stderr)
        sys.exit(0)

    # Aggregate and display
    hunts = aggregate(records, args.hunter_type)
    print(f"  Unique hunt codes: {len(hunts)}\n", file=sys.stderr)

    if args.csv:
        output_csv(hunts, args.hunter_type)
    else:
        display_table(hunts, args.hunter_type, args.sort, args.top, len(available_years))


if __name__ == "__main__":
    main()
