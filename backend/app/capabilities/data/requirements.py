"""Member 1: upcoming-requirement inference (plan §4C, Member 1 §§4/70).

Evidence tiers, in priority order:
  1. recorded         — a valid recorded due date (point window).
  2. nominal_interval — usable nominal interval + last calibration
                        (window = due ± 1 month). Rule version requirements-v1.
  3. repeat_history   — ≥3 positive gaps between an instrument's own events;
                        window = last + median gap ± max(30d, spread/2).
  4. unknown          — no usable evidence; null window, unknowns listed.

Eligibility: stopped instruments are always excluded; a null stop flag
stays review_required (unknown, not "active confirmed"). Implausible
recorded dates (due on/before last calibration, or >10 years after the
reference date) are invalidated and fall through to the next tier.
One requirement per instrument; IDs are deterministic.
"""

import calendar
from datetime import date

from ...contracts import sales_v2 as v2

RULE_VERSION = "requirements-v1"
MIN_POSITIVE_GAPS = 3
NOMINAL_WINDOW_MONTHS = 1
REPEAT_MIN_HALF_WIDTH_DAYS = 30
MAX_DUE_HORIZON_YEARS = 10


def _parse(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _add_months(day: date, months: int) -> date:
    total = day.month - 1 + months
    year, month = day.year + total // 12, total % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _eligibility(stopped: bool | None) -> str:
    if stopped is True:
        return "excluded"
    if stopped is None:
        return "review_required"
    return "eligible"


def infer_requirements(
    instruments: list[v2.InstrumentRecord],
    events: list[v2.InstrumentEvent],
    reference_date: str,
) -> list[v2.Requirement]:
    reference = date.fromisoformat(reference_date)
    by_instrument: dict[str, list[date]] = {}
    for event in events:
        day = _parse(event.calibration_date)
        if day is not None:
            by_instrument.setdefault(event.instrument_id, []).append(day)

    requirements = []
    for inst in instruments:
        requirements.append(
            _infer_one(inst, sorted(by_instrument.get(inst.instrument_id, [])), reference)
        )
    return requirements


def _infer_one(
    inst: v2.InstrumentRecord, event_dates: list[date], reference: date
) -> v2.Requirement:
    last = _parse(inst.last_calibration_date)
    recorded = _parse(inst.recorded_due_date)
    base = {
        "id": "",
        "customer_id": inst.current_customer_id or "unknown",
        "instrument_id": inst.instrument_id,
        "group_id": inst.group_id,
        "stopped": inst.stopped,
        "eligibility": _eligibility(inst.stopped),
    }

    # Tier 1: recorded due date, validated before use.
    if recorded is not None:
        plausible = True
        if last is not None and recorded <= last:
            plausible = False
        try:
            horizon = date(
                reference.year + MAX_DUE_HORIZON_YEARS,
                reference.month,
                min(reference.day, 28),
            )
            if recorded > horizon:
                plausible = False
        except ValueError:
            plausible = False
        if plausible:
            evidence = [d.isoformat() for d in ([last] if last else []) + [recorded]]
            return v2.Requirement.model_validate(
                {
                    **base,
                    "id": f"REQ-{inst.instrument_id}-recorded",
                    "kind": "recorded",
                    "window_start": recorded.isoformat(),
                    "window_end": recorded.isoformat(),
                    "method": "recorded_due_date",
                    "evidence_dates": evidence,
                    "positive_gap_count": 0,
                    "unknowns": [],
                }
            )

    # Tier 2: nominal interval from last calibration.
    if inst.nominal_interval_months and last is not None:
        due = _add_months(last, inst.nominal_interval_months)
        return v2.Requirement.model_validate(
            {
                **base,
                "id": f"REQ-{inst.instrument_id}-nominal_interval",
                "kind": "nominal_interval",
                "window_start": _add_months(due, -NOMINAL_WINDOW_MONTHS).isoformat(),
                "window_end": _add_months(due, NOMINAL_WINDOW_MONTHS).isoformat(),
                "method": (
                    f"nominal_interval_{inst.nominal_interval_months}m_from_last_calibration"
                ),
                "evidence_dates": [last.isoformat()],
                "positive_gap_count": 0,
                "unknowns": [],
            }
        )

    # Tier 3: repeated own-history intervals.
    gaps = [
        (later - earlier).days
        for earlier, later in zip(event_dates, event_dates[1:])
        if (later - earlier).days > 0
    ]
    if len(gaps) >= MIN_POSITIVE_GAPS and event_dates:
        median_gap = _median(gaps)
        spread = max(gaps) - min(gaps)
        half_width = max(REPEAT_MIN_HALF_WIDTH_DAYS, spread / 2)
        projected = event_dates[-1].toordinal() + int(round(median_gap))
        start = date.fromordinal(projected - int(round(half_width)))
        end = date.fromordinal(projected + int(round(half_width)))
        return v2.Requirement.model_validate(
            {
                **base,
                "id": f"REQ-{inst.instrument_id}-repeat_history",
                "kind": "repeat_history",
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "method": (
                    f"repeat_history_median_gap_{median_gap / 30.44:.0f}m"
                    f"_over_{len(gaps)}_positive_gaps"
                ),
                "evidence_dates": [d.isoformat() for d in event_dates],
                "positive_gap_count": len(gaps),
                "unknowns": [],
            }
        )

    # Tier 4: unknown — never a fabricated exact date.
    unknowns = []
    if recorded is None:
        unknowns.append("no recorded due date")
    if not inst.nominal_interval_months or last is None:
        unknowns.append("no nominal interval")
    if not event_dates:
        unknowns.append("no calibration history")
    return v2.Requirement.model_validate(
        {
            **base,
            "id": f"REQ-{inst.instrument_id}-unknown",
            "kind": "unknown",
            "eligibility": "excluded" if inst.stopped is True else "review_required",
            "window_start": None,
            "window_end": None,
            "method": "no_usable_date_evidence",
            "evidence_dates": [],
            "positive_gap_count": 0,
            "unknowns": unknowns,
        }
    )
