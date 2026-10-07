"""Member 1: extract rows -> normalized snapshot document (plan §§1-3).

Pure `build_snapshot()` plus a CLI that reads the `analysis/customers/*.json`
extracts and writes an immutable `data/runtime/snapshots/<id>.json` document
(plus manifest summary on stdout). Never touches the SQL source.

Normalization rules:
- Monthly rows deduplicated on (customer, month) by summation; out-of-range
  months dropped. Both counted in manifest quality flags.
- Months from a customer's first observed month through the complete month
  are zero-filled; earlier uncovered history stays absent (not zero).
- Missing company names become identifier-based display names.
- Industry `Unknown` maps to null IDs; labels keep deterministic slugs.
- Nominal intervals convert via a documented unit table; unknown units and
  non-positive values become null with a per-instrument quality flag.
- Stop flag tri-state: 1 -> True, 0 -> False, anything else -> None (unknown).
- Instrument UUIDs are hashed in the builder so snapshots stay pseudonymous.
"""

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

from ...contracts import sales_v2 as v2
from .requirements import infer_requirements

ROOT = Path(__file__).resolve().parents[4]
EXTRACT_DIR = ROOT / "analysis" / "customers"
SNAPSHOT_DIR = ROOT / "data" / "runtime" / "snapshots"

MONTH_UNITS = {"M", "MO", "MON", "MONAT", "MONATE", "MM", "MONTH", "MONTHS"}
YEAR_UNITS = {"J", "JR", "JAHR", "JAHRE", "Y", "YR", "YEAR", "YEARS", "A"}
DAY_UNITS = {"T", "TAG", "TAGE", "D", "DAY", "DAYS"}
WEEK_UNITS = {"W", "WOCHE", "WOCHEN", "W", "WEEK", "WEEKS"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _month_to_index(month: str) -> int:
    year, mon = month.split("-")
    return int(year) * 12 + int(mon)


def _index_to_month(index: int) -> str:
    year, mon = divmod(index, 12)
    if mon == 0:
        year, mon = year - 1, 12
    return f"{year}-{mon:02d}"


def _month_range(start: str, end: str) -> list[str]:
    return [_index_to_month(i) for i in range(_month_to_index(start), _month_to_index(end) + 1)]


def convert_interval(value, unit):
    """Return (nominal_interval_months | None, quality_flag | None)."""
    if value is None or value <= 0:
        return None, "no_positive_interval"
    code = (str(unit) if unit is not None else "").strip().upper()
    if code in MONTH_UNITS:
        return int(value), None
    if code in YEAR_UNITS:
        return int(value) * 12, None
    if code in DAY_UNITS:
        return max(1, round(value / 30.44)), "day_unit_converted_to_months"
    if code in WEEK_UNITS:
        return max(1, round(value * 7 / 30.44)), "week_unit_converted_to_months"
    return None, f"unknown_interval_unit:{unit}"


def _industry_ids(label: str | None) -> tuple[str | None, str | None]:
    if label is None or label.strip().lower() == "unknown" or not label.strip():
        return None, None
    slug = re.sub(r"[^A-Z0-9]+", "_", label.strip().upper()).strip("_")
    return f"IND-{slug}", label.strip()


def build_snapshot(
    monthly_rows: list[dict],
    industry_rows: list[dict],
    groups_rows: list[dict],
    instrument_rows: list[dict] | None = None,
    event_rows: list[dict] | None = None,
    *,
    snapshot_id: str,
    extracted_at: str,
    reference_date: str,
    complete_through_month: str,
    history_start: str,
) -> dict:
    quality_flags: list[str] = []
    complete_idx = _month_to_index(complete_through_month)

    # --- monthly history: dedupe, drop out-of-range, zero-fill ---
    deduped: dict[tuple[str, str], dict] = {}
    duplicates = 0
    out_of_range = 0
    for row in monthly_rows:
        month = row["month"]
        if not re.fullmatch(r"\d{4}-\d{2}", month) or not (
            _month_to_index(history_start) <= _month_to_index(month) <= complete_idx
        ):
            out_of_range += 1
            continue
        key = (row["customer"], month)
        if key in deduped:
            duplicates += 1
            for extract_field, stored_field in (
                ("calibrations", "calibration_events"),
                ("instruments", "distinct_instruments"),
                ("equipment_groups", "equipment_group_count"),
                ("labs", "lab_count"),
            ):
                deduped[key][stored_field] += row.get(extract_field) or 0
        else:
            deduped[key] = {
                "customer_id": row["customer"],
                "month": month,
                "calibration_events": row.get("calibrations") or 0,
                "distinct_instruments": row.get("instruments") or 0,
                "equipment_group_count": row.get("equipment_groups") or 0,
                "lab_count": row.get("labs") or 0,
            }
    if duplicates:
        quality_flags.append(f"duplicate_month_rows_summed:{duplicates}")
    if out_of_range:
        quality_flags.append(f"out_of_range_month_rows_dropped:{out_of_range}")

    first_seen: dict[str, str] = {}
    for customer, month in deduped:
        if customer not in first_seen or month < first_seen[customer]:
            first_seen[customer] = month
    history = list(deduped.values())
    zero_filled = 0
    for customer, start in first_seen.items():
        for month in _month_range(start, complete_through_month):
            if (customer, month) not in deduped:
                history.append(
                    {
                        "customer_id": customer,
                        "month": month,
                        "calibration_events": 0,
                        "distinct_instruments": 0,
                        "equipment_group_count": 0,
                        "lab_count": 0,
                    }
                )
                zero_filled += 1
    if zero_filled:
        quality_flags.append(f"zero_filled_months:{zero_filled}")
    history.sort(key=lambda r: (r["customer_id"], r["month"]))

    # --- profiles ---
    industry_map = {r["customer"]: r.get("industry") for r in industry_rows}
    customers = set(first_seen) | set(industry_map) | {r["customer"] for r in groups_rows}
    profiles = []
    for customer in sorted(customers):
        industry_id, industry_label = _industry_ids(industry_map.get(customer))
        profiles.append(
            {
                "customer_id": customer,
                "display_name": f"Account {customer[:8]}",
                "name_source": "identifier",
                "industry_id": industry_id,
                "industry_label": industry_label,
            }
        )

    # --- portfolio (trailing-12m group calibration counts; the export has
    # no group-level distinct-instrument counts, so those stay null) ---
    window_start = date.fromisoformat(_index_to_month(complete_idx - 11) + "-01")
    import calendar as _calendar

    last_day = _calendar.monthrange(int(complete_through_month[:4]), int(complete_through_month[5:7]))[1]
    window_end = date(int(complete_through_month[:4]), int(complete_through_month[5:7]), last_day)
    portfolio = [
        {
            "customer_id": r["customer"],
            "group_id": f"GRP-{re.sub(r'[^A-Z0-9]+', '_', str(r['equipment_group']).strip().upper()).strip('_')}",
            "group_label": r["equipment_group"],
            "distinct_instruments": None,
            "calibration_events": r.get("calibrations") or 0,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        }
        for r in groups_rows
    ]
    quality_flags.append("group_distinct_instrument_counts_not_exported")

    # --- instruments + events (optional until the instrument extract lands) ---
    instruments = []
    for row in instrument_rows or []:
        months, flag = convert_interval(row.get("nominal_interval"), row.get("interval_unit"))
        flags = [flag] if flag else []
        raw_stop = row.get("stopped")
        stopped = True if raw_stop == 1 else (False if raw_stop == 0 else None)
        instruments.append(
            {
                "instrument_id": _hash(str(row["instrument"])),
                "current_customer_id": row.get("customer"),
                "group_id": (
                    f"GRP-{re.sub(r'[^A-Z0-9]+', '_', str(row.get('equipment_group') or '').strip().upper()).strip('_')}"
                    if row.get("equipment_group")
                    else None
                ),
                "last_calibration_date": row.get("last_calibration"),
                "recorded_due_date": row.get("recorded_due"),
                "nominal_interval_months": months,
                "stopped": stopped,
                "quality_flags": flags,
            }
        )
    raw_to_hashed = {
        str(row["instrument"]): _hash(str(row["instrument"]))
        for row in instrument_rows or []
    }
    events = [
        {
            "event_id": row["event"],
            "instrument_id": raw_to_hashed.get(
                str(row["instrument"]), _hash(str(row["instrument"]))
            ),
            "historical_customer_id": row.get("customer"),
            "calibration_date": row["calibration_date"],
            "group_id": None,
        }
        for row in event_rows or []
    ]
    if not instrument_rows:
        quality_flags.append("instrument_level_not_exported")

    instrument_models = [v2.InstrumentRecord.model_validate(i) for i in instruments]
    event_models = [v2.InstrumentEvent.model_validate(e) for e in events]
    requirement_models = infer_requirements(instrument_models, event_models, reference_date)

    profile_models = [v2.CustomerProfile.model_validate(p) for p in profiles]
    history_models = [v2.MonthlyHistoryRow.model_validate(h) for h in history]
    portfolio_models = [v2.PortfolioRow.model_validate(p) for p in portfolio]

    n_profiles = len(profile_models)
    coverage = {
        "industry_label": sum(1 for p in profile_models if p.industry_label) / max(n_profiles, 1),
        "recorded_due_date": sum(1 for i in instrument_models if i.recorded_due_date)
        / max(len(instrument_models), 1),
        "nominal_interval": sum(1 for i in instrument_models if i.nominal_interval_months)
        / max(len(instrument_models), 1),
        "stop_known": sum(1 for i in instrument_models if i.stopped is not None)
        / max(len(instrument_models), 1),
    }
    manifest = v2.SnapshotManifest(
        snapshot_id=snapshot_id,
        extracted_at=extracted_at,
        reference_date=reference_date,
        complete_through_month=complete_through_month,
        history_start=history_start,
        source_tables=["profiles", "history", "portfolio", "instruments", "events", "requirements"],
        row_counts={
            "profiles": n_profiles,
            "history": len(history_models),
            "portfolio": len(portfolio_models),
            "instruments": len(instrument_models),
            "events": len(event_models),
            "requirements": len(requirement_models),
        },
        field_coverage=coverage,
        quality_flags=quality_flags,
    )
    group_labels = sorted({(p.group_id, p.group_label) for p in portfolio_models})
    industry_options = sorted(
        {(p.industry_id, p.industry_label) for p in profile_models if p.industry_id}
    )
    return {
        "manifest": manifest.model_dump(),
        "month_grid": _month_range(history_start, complete_through_month),
        "industry_labels": [
            {"industry_id": i, "industry_label": label} for i, label in industry_options
        ],
        "equipment_group_labels": [
            {"group_id": group_id, "group_label": group_label}
            for group_id, group_label in group_labels
        ],
        "profiles": [p.model_dump() for p in profile_models],
        "history": [h.model_dump() for h in history_models],
        "portfolio": [p.model_dump() for p in portfolio_models],
        "instruments": [i.model_dump() for i in instrument_models],
        "events": [e.model_dump() for e in event_models],
        "requirements": [r.model_dump() for r in requirement_models],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build a normalized v2 snapshot document.")
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--extracted-at", required=True, help="ISO UTC timestamp")
    parser.add_argument("--reference-date", default="2026-08-31")
    parser.add_argument("--complete-through", default="2026-08")
    parser.add_argument("--history-start", default="2024-01")
    args = parser.parse_args()

    def load(name: str, required: bool = True) -> list[dict]:
        path = EXTRACT_DIR / f"{name}.json"
        if not path.exists():
            if required:
                raise SystemExit(f"missing extract: {path}")
            print(f"optional extract missing, continuing without: {name}")
            return []
        return json.loads(path.read_text())

    document = build_snapshot(
        load("monthly_history"),
        load("industry"),
        load("groups"),
        load("instruments", required=False),
        load("instrument_events", required=False),
        snapshot_id=args.snapshot_id,
        extracted_at=args.extracted_at,
        reference_date=args.reference_date,
        complete_through_month=args.complete_through,
        history_start=args.history_start,
    )
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOT_DIR / f"{args.snapshot_id}.json"
    with out.open("x") as output:
        output.write(json.dumps(document, ensure_ascii=False))
    print(f"wrote {out}")
    print(json.dumps(document["manifest"], indent=1))


if __name__ == "__main__":
    main()
