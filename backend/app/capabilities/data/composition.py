"""Member 1: account composition + refresh-after-correction seam (plan §5).

`refresh_after_correction` re-derives an account's actionable state after a
workflow write: stored requirements minus signal-scoped suppressions, plus
the persisted workflow. Ranking/peer/preparation math is Member 3's pure
insight layer, composed here — never reimplemented. Member 2's published
predictions are read for this snapshot; unavailable outputs stay null.
"""

import calendar
import os
from collections.abc import Callable

from ..analytics.context import for_snapshot as _analytics_for_snapshot
from ..insights import compat as _compat
from ..insights import service as _insights
from ..insights.peers import owns_category as _owns_category
from .service import get_customer_detail, list_customers, load_snapshot
from .workflow import get_workflow, _db_path
from ...contracts import sales_v2 as v2

WORKFLOW_TODAY = os.getenv("PECAL_TODAY", "2026-10-07")


def _max_expected_value(snapshot_id: str, snapshot: dict) -> float | None:
    """Snapshot maximum of P(activity) × expected volume × unit value.

    None when analytics predictions are unavailable: the expected-value
    ranking component then stays null instead of scoring blind.
    """
    from ..insights.value_weights import load_weights, unit_value

    try:
        analytics = _analytics_for_snapshot(snapshot)
        weights = load_weights()
        best = 0.0
        groups: dict[str, set[str]] = {}
        for req in snapshot["requirements"]:
            if req.group_id and req.stopped is not True and req.eligibility != "excluded":
                groups.setdefault(req.customer_id, set()).add(req.group_id)
        for profile in snapshot["profiles"]:
            prediction = analytics.prediction(profile.customer_id)
            if prediction is None:
                continue
            prob = prediction.activity.probability
            expected = prediction.calibration_volume.expected_total
            if (
                prob is None
                or expected is None
                or prediction.activity.support.status != "supported"
                or prediction.calibration_volume.support.status != "supported"
            ):
                continue
            owned = groups.get(profile.customer_id, set())
            unit = sum(unit_value(g, weights) for g in owned) / len(owned) if owned else 1.0
            best = max(best, prob * expected * unit)
        return best if best > 0 else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _suppressed_ids(state: v2.AccountWorkflow, today: str) -> set[str]:
    suppressed = set()
    for record in state.suppressions:
        if record.status == "resolved":
            suppressed.add(record.reason_id)
        elif record.status == "snoozed" and record.until is not None and record.until >= today:
            suppressed.add(record.reason_id)
    return suppressed


def snapshot_stats(snapshot_id: str) -> _insights.SnapshotStats:
    """Frozen normalization anchors: every account ranks against the same ones."""
    snapshot = load_snapshot(snapshot_id)
    if "_ranking_stats" in snapshot:
        return snapshot["_ranking_stats"]
    instruments_per_account: dict[str, int] = dict(snapshot.get("ranking_instrument_counts", {}))
    for inst in snapshot["instruments"]:
        if inst.current_customer_id:
            instruments_per_account[inst.current_customer_id] = (
                instruments_per_account.get(inst.current_customer_id, 0) + 1
            )
    if not instruments_per_account:
        for row in snapshot["history"]:
            instruments_per_account[row.customer_id] = max(instruments_per_account.get(row.customer_id, 0), row.distinct_instruments)
    complete = snapshot["manifest"].complete_through_month
    recent = sorted({h.month for h in snapshot["history"] if h.month <= complete})[-3:]
    volume_3m: dict[str, float] = {}
    for row in snapshot["history"]:
        if row.month in recent:
            volume_3m[row.customer_id] = volume_3m.get(row.customer_id, 0) + row.calibration_events
    counts = sorted(instruments_per_account.values())
    p90 = counts[max(0, min(len(counts) - 1, int(len(counts) * 0.9)))] if counts else 1
    snapshot["_ranking_stats"] = _insights.SnapshotStats(
        snapshot_id=snapshot_id,
        reference_date=snapshot["manifest"].reference_date,
        max_instruments_per_account=max(counts + [1]),
        max_calibration_events_3m=max(list(volume_3m.values()) + [1.0]),
        p90_instruments_per_account=float(p90 or 1),
        max_expected_value=_max_expected_value(snapshot_id, snapshot),
    )
    return snapshot["_ranking_stats"]


def _peer_inputs(snapshot_id: str) -> dict:
    snapshot = load_snapshot(snapshot_id)
    if "_peer_inputs" in snapshot:
        return snapshot["_peer_inputs"]
    industry_by_customer = {
        p.customer_id: p.industry_id
        for p in snapshot["profiles"]
        if p.industry_id is not None
    }
    snapshot["_peer_inputs"] = {
        "portfolios": [_compat.portfolio_from_shared(p) for p in snapshot["portfolio"]],
        "industry_by_customer": industry_by_customer,
        "group_labels": {
            g["group_id"]: g["group_label"]
            for g in snapshot.get("equipment_group_labels", [])
        },
        "industry_customer_count": {
            industry: sum(1 for p in snapshot["profiles"] if p.industry_id == industry)
            for industry in set(industry_by_customer.values())
        },
    }
    peer = snapshot["_peer_inputs"]
    peer["index"] = _insights.build_peer_index(peer["portfolios"], industry_by_customer)
    return peer


def peers_for_customer(snapshot_id: str, customer_id: str) -> list[v2.PeerOpportunity]:
    """Peer-supported discovery for one account (target excluded by construction)."""
    detail = get_customer_detail(snapshot_id, customer_id)
    peer = _peer_inputs(snapshot_id)
    owned = {
        p.group_id
        for p in detail["portfolio"]
        if _owns_category(_compat.portfolio_from_shared(p))
        and p.group_id is not None
    }
    windows = [(p.window_start, p.window_end) for p in detail["portfolio"]]
    if windows:
        window_start = min(s for s, _ in windows)[:10]
        window_end = max(e for _, e in windows)[:10]
    else:
        manifest = load_snapshot(snapshot_id)["manifest"]
        year, month = map(int, manifest.complete_through_month.split("-"))
        start_month = month - 11
        start_year = year
        while start_month <= 0:
            start_month += 12
            start_year -= 1
        window_start = f"{start_year}-{start_month:02d}-01"
        last_day = calendar.monthrange(year, month)[1]
        window_end = f"{year}-{month:02d}-{last_day}"
    opportunities = _insights.get_peer_opportunities(
        target_customer_id=customer_id,
        target_industry_id=detail["profile"].industry_id,
        owned_group_ids=owned,
        peer_index=peer["index"],
        group_labels=peer["group_labels"],
        industry_customer_count=peer["industry_customer_count"],
        window_start=window_start,
        window_end=window_end,
    )
    return [v2.PeerOpportunity.model_validate(o.model_dump()) for o in opportunities]


def _local_inputs(snapshot_id: str, customer_id: str, today: str) -> dict:
    detail = get_customer_detail(snapshot_id, customer_id)
    state = get_workflow(customer_id)
    suppressed = _suppressed_ids(state, today)
    prediction = _analytics_for_snapshot(load_snapshot(snapshot_id)).prediction(customer_id)
    return {
        "profile": _compat.profile_from_shared(detail["profile"]),
        "requirements": [
            _compat.requirement_from_shared(r)
            for r in detail["requirements"]
            if r.id not in suppressed
        ],
        "prediction": _compat.prediction_from_shared(prediction) if prediction is not None else None,
        "peers": _compat.peers_from_shared(peers_for_customer(snapshot_id, customer_id)),
        "workflow": _compat.workflow_from_shared(state),
        "suppressed": suppressed,
        "workflow_shared": state,
    }


def action_for_customer(
    snapshot_id: str, customer_id: str, today: str = WORKFLOW_TODAY
) -> v2.AccountAction | None:
    """One account's ranked action in shared shape, or None without reasons."""
    stats = snapshot_stats(snapshot_id)
    local = _local_inputs(snapshot_id, customer_id, today)
    action = _insights.build_account_action(
        snapshot_id=snapshot_id,
        customer_id=customer_id,
        requirements=local["requirements"],
        prediction=local["prediction"],
        peer_opportunities=local["peers"],
        workflow=local["workflow"],
        stats=stats,
        today=today,
    )
    if action is None:
        return None
    return v2.AccountAction.model_validate(_compat.action_to_shared_payload(action))


def preparation_for_customer(
    snapshot_id: str, customer_id: str, today: str = WORKFLOW_TODAY
) -> v2.PreparationCard:
    """Grounded preparation brief: structured facts, never LLM-invented inputs."""
    stats = snapshot_stats(snapshot_id)
    local = _local_inputs(snapshot_id, customer_id, today)
    action = _insights.build_account_action(
        snapshot_id=snapshot_id,
        customer_id=customer_id,
        requirements=local["requirements"],
        prediction=local["prediction"],
        peer_opportunities=local["peers"],
        workflow=local["workflow"],
        stats=stats,
        today=today,
    )
    card = _insights.build_preparation(
        profile=local["profile"],
        action=action,
        peer_opportunities=local["peers"],
        prediction=local["prediction"],
        requirements=local["requirements"],
        workflow=local["workflow"],
        reference_date=stats.reference_date,
    )
    return v2.PreparationCard.model_validate(card.model_dump())


def ranked_queue(snapshot_id: str, today: str = WORKFLOW_TODAY) -> list[v2.AccountAction]:
    """Cache deterministic queues until local workflow or analytics changes."""
    snapshot = load_snapshot(snapshot_id)
    path = _db_path()
    analytics = _analytics_for_snapshot(snapshot)
    key = (today, str(path), path.stat().st_mtime_ns if path.exists() else None,
           os.getenv("PECAL_ANALYTICS_ROOT"), analytics.available, analytics.predictions_ready)
    cached = snapshot.get("_queue")
    if cached and cached["key"] == key:
        return cached["actions"]
    stats = snapshot_stats(snapshot_id)
    actions, workflows = [], {}
    for profile in list_customers(snapshot_id):
        local = _local_inputs(snapshot_id, profile.customer_id, today)
        workflows[profile.customer_id] = local["workflow"]
        action = _insights.build_account_action(snapshot_id=snapshot_id, customer_id=profile.customer_id,
            requirements=local["requirements"], prediction=local["prediction"],
            peer_opportunities=local["peers"], workflow=local["workflow"], stats=stats, today=today)
        if action is not None:
            actions.append(v2.AccountAction.model_validate(_compat.action_to_shared_payload(action)))
    actions.sort(key=lambda a: (-a.priority_score, a.customer_id))
    # The first read may initialize the workflow DB; capture its final revision.
    key = (*key[:2], path.stat().st_mtime_ns, *key[3:])
    snapshot["_queue"] = {"key": key, "actions": actions, "workflows": workflows}
    return actions


def split_queue(snapshot_id: str, today: str = WORKFLOW_TODAY) -> tuple[list[v2.AccountAction], list[v2.AccountAction]]:
    actions = ranked_queue(snapshot_id, today)
    workflows = load_snapshot(snapshot_id)["_queue"]["workflows"]
    return _insights.split_followups_first(actions, workflows, today)


def refresh_after_correction(
    snapshot_id: str,
    customer_id: str,
    ranking_fn: Callable | None = None,
    today: str = WORKFLOW_TODAY,
) -> dict:
    """Recompute one account's requirements/workflow/action after a correction."""
    detail = get_customer_detail(snapshot_id, customer_id)
    state = get_workflow(customer_id)
    suppressed = _suppressed_ids(state, today)
    active = [r for r in detail["requirements"] if r.id not in suppressed]
    if ranking_fn is None:
        ranking_fn = _compat.ranking_fn_for_composition(
            snapshot_stats(snapshot_id), today=today
        )
    local = _local_inputs(snapshot_id, customer_id, today)
    local_action = ranking_fn(detail["profile"], active, local["prediction"], local["peers"], state)
    action = (
        v2.AccountAction.model_validate(_compat.action_to_shared_payload(local_action))
        if local_action is not None
        else None
    )
    snapshot = load_snapshot(snapshot_id)
    cache = snapshot.get("_queue")
    if cache and cache["key"][0] == today:
        cache["actions"] = sorted([a for a in cache["actions"] if a.customer_id != customer_id] + ([action] if action else []), key=lambda a: (-a.priority_score, a.customer_id))
        cache["workflows"][customer_id] = _compat.workflow_from_shared(state)
        key = cache["key"]
        cache["key"] = (*key[:2], _db_path().stat().st_mtime_ns, *key[3:])
    return {
        "customer_id": customer_id,
        "requirements": detail["requirements"],
        "active_requirement_ids": [r.id for r in active],
        "suppressed_requirement_ids": sorted(suppressed),
        "workflow": state,
        "action": action,
    }
