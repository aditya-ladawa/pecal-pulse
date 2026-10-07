"""Compose one opportunity response; all totals use the full selected cohort."""
import hashlib
import json
import os
from datetime import date
from pathlib import Path
from . import service, composition, workflow
from ..analytics.context import for_snapshot
from ..analytics import opportunities as features
from ...contracts import sales_v2 as v2
from ...contracts.opportunities import (OpportunityFilters, OpportunityPoint, ClusterSummary,
    CohortMetric, OpportunityResponse, ScenarioAssumptions)


def _base(snapshot_id, filters, allow_fit=False):
    snapshot = service.load_snapshot(snapshot_id)
    analytics = for_snapshot(snapshot)
    key = (features.RULE_VERSION, filters.window_days, filters.include_inferred, filters.include_past_due, id(analytics))
    cache = snapshot.setdefault('_opportunity_base', {})
    if key in cache:
        return cache[key]
    reference = snapshot['manifest'].reference_date
    end_month = snapshot['manifest'].complete_through_month
    end_index = int(end_month[:4]) * 12 + int(end_month[5:])
    volumes, groups, reqs = {}, {}, {}
    for h in snapshot['history']:
        index = int(h.month[:4]) * 12 + int(h.month[5:])
        if end_index - 11 <= index <= end_index:
            volumes[h.customer_id] = volumes.get(h.customer_id, 0) + h.calibration_events
    for p in snapshot['portfolio']:
        if p.calibration_events > 0:
            groups.setdefault(p.customer_id, set()).add(p.group_id)
    for r in snapshot['requirements']:
        reqs.setdefault(r.customer_id, []).append(r)
        if r.group_id:
            groups.setdefault(r.customer_id, set()).add(r.group_id)
    segments = {s['id']: s['label'] for s in analytics.payload('segments') or []}
    rows = []
    for profile in snapshot['profiles']:
        cid = profile.customer_id
        prediction = analytics.prediction(cid)
        peers = composition.peers_for_customer(snapshot_id, cid)
        supported = features.due_requirements(reqs.get(cid, []), reference, filters.window_days,
                                             filters.include_inferred, filters.include_past_due)
        raw = features.raw_components(supported, prediction, volumes.get(cid), bool(peers), reference)
        rows.append({'profile': profile, 'prediction': prediction, 'requirements': supported,
                     'history_volume': volumes.get(cid), 'discovery': bool(peers), 'raw': raw,
                     'groups': sorted(groups.get(cid, set()) | {p.group_id for p in peers}),
                     'segment_label': segments.get(prediction.segment_id) if prediction else None})
    signature = hashlib.sha256(json.dumps([features.RULE_VERSION, snapshot_id, reference,
        snapshot['manifest'].extracted_at, snapshot['manifest'].row_counts,
        next((r['prediction'].activity.model_version for r in rows if r['prediction']), 'unavailable'),
        filters.window_days, filters.include_inferred, filters.include_past_due], sort_keys=True).encode()).hexdigest()[:16]
    root = Path(os.getenv('PECAL_OPPORTUNITY_ROOT', str(service.ROOT / 'data/runtime/opportunities')))
    path = root / snapshot_id / f'{signature}.json'
    try:
        model = json.loads(path.read_text())
        if model['rule_version'] != features.RULE_VERSION:
            raise ValueError('model version mismatch')
    except (OSError, ValueError, KeyError):
        if not allow_fit and not snapshot_id.startswith("synthetic"):
            raise ValueError("Opportunity artifacts missing. Run python -m analysis.build_opportunities --snapshot-id " + snapshot_id)
        model = features.fit_map([r['raw'] for r in rows])
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(model, allow_nan=False, indent=2))
        temp.replace(path)
    cache[key] = rows, model, signature
    return cache[key]


def compose(snapshot_id: str, metadata: v2.ResponseMetadata, filters: OpportunityFilters,
            cluster_id: str | None = None, display_limit=500, limit=10, offset=0,
            scenario: ScenarioAssumptions | None = None) -> OpportunityResponse:
    if cluster_id is not None and cluster_id not in {*features.IDS, 'needs-evidence'}:
        raise ValueError('Unknown opportunity cluster')
    snapshot = service.load_snapshot(snapshot_id)
    profiles = snapshot['profiles']
    analytics = for_snapshot(snapshot)
    options = {
        'industries': [{'value': k, 'label': label} for k, label in sorted({(p.industry_id or 'unknown', p.industry_label or 'Unknown') for p in profiles})],
        'segments': [{'value': s['id'], 'label': s['label']} for s in analytics.payload('segments') or []],
        'groups': [{'value': g['group_id'], 'label': g['group_label']} for g in snapshot.get('equipment_group_labels', [])],
    }
    # Some fixtures use portfolio labels without the auxiliary group dictionary.
    if not options['groups']:
        options['groups'] = [{'value': k, 'label': label} for k, label in sorted({(p.group_id, p.group_label) for p in snapshot['portfolio']})]
    for key, value in [('industries', filters.industry), ('segments', filters.segment), ('groups', filters.group)]:
        if value != 'all' and value not in {o['value'] for o in options[key]}:
            raise ValueError(f'Unknown {key} filter')
    rows, model, signature = _base(snapshot_id, filters)
    actions = {a.customer_id: a for a in composition.ranked_queue(snapshot_id, metadata.workflow_today)}
    # Queue reads initialize the DB; read workflow state afterwards.
    states = workflow.list_workflows()
    matched = []
    for row in rows:
        p, pred = row['profile'], row['prediction']
        cid = p.customer_id
        if filters.industry != 'all' and (p.industry_id or 'unknown') != filters.industry:
            continue
        if filters.segment != 'all' and (pred is None or pred.segment_id != filters.segment):
            continue
        if filters.group != 'all' and filters.group not in row['groups']:
            continue
        state = states.get(cid, v2.AccountWorkflow())
        suppressed = composition._suppressed_ids(state, metadata.workflow_today)
        reqs = features.due_requirements(row['requirements'], metadata.reference_date,
                    filters.window_days, filters.include_inferred, filters.include_past_due, suppressed)
        action = actions.get(cid)
        reason_types = list(dict.fromkeys(r.type for r in action.reasons)) if action else []
        prediction = pred
        if pred and f'{cid}:inactivity:review' in suppressed:
            prediction = pred.model_copy(update={'inactivity': pred.inactivity.model_copy(update={'flagged': False})})
        raw = features.raw_components(reqs, prediction, row['history_volume'], 'discovery' in reason_types, metadata.reference_date)
        if filters.purpose == 'upcoming' and not reqs:
            continue
        if filters.purpose != 'all' and filters.purpose != 'upcoming' and filters.purpose not in reason_types:
            continue
        urgency, size, basis = features.coordinates(raw, model['anchors'])
        activity = pred.activity if pred else None
        volume = pred.calibration_volume if pred else None
        matched.append(OpportunityPoint(
            customer_id=cid, display_name=p.display_name, industry_id=p.industry_id or 'unknown',
            industry_label=p.industry_label or 'Unknown', segment_id=pred.segment_id if pred else None,
            segment_label=row['segment_label'], cluster_id=features.assign(urgency, size, model),
            urgency_score=urgency, size_score=size, size_basis=basis,
            components={k: raw[k] for k in ('due_quantity', 'activity_gap', 'discovery_scale')},
            due_recorded=raw['due_recorded'], due_inferred=raw['due_inferred'],
            due_selected_category=sum(filters.group == 'all' or r.group_id == filters.group for r in reqs),
            activity_flagged=bool(prediction and prediction.inactivity.support.status == 'supported' and prediction.inactivity.flagged),
            inactivity_supported=bool(pred and pred.inactivity.support.status == 'supported'),
            activity_probability=activity.probability if activity and activity.support.status == 'supported' else None,
            expected_calibrations=volume.expected_total if volume and volume.support.status == 'supported' and volume.metric == 'calibration_events' else None,
            forecast_start=volume.window_start if volume else None, forecast_end=volume.window_end if volume else None,
            priority_score=action.priority_score if action else 0, reasons=[r.title for r in action.reasons[:3]] if action else [],
            reason_types=reason_types, next_action=action.suggested_next_step if action else 'Gather more evidence before prioritizing.',
            readiness=action.readiness if action else 'insufficient_evidence', owner=state.account_owner,
            group_ids=row['groups']))
    matched.sort(key=lambda p: (-p.priority_score, p.customer_id))
    selected = [p for p in matched if cluster_id is None or (p.cluster_id == cluster_id if cluster_id != 'needs-evidence' else p.cluster_id is None)]
    ids = {p.customer_id for p in selected}
    tasks = sorted([f for cid, state in states.items() if cid in ids for f in state.followups if f.status == 'open'], key=lambda f: (f.due_date, f.id))
    overdue = sum(f.due_date < metadata.workflow_today for f in tasks)
    recorded, inferred = sum(p.due_recorded for p in selected), sum(p.due_inferred for p in selected)
    forecast = [p for p in selected if p.expected_calibrations is not None]
    expected = sum(p.expected_calibrations for p in forecast) if forecast else None
    inactivity_supported = sum(p.inactivity_supported for p in selected)
    flagged = sum(p.activity_flagged for p in selected)
    dates = next(((p.forecast_start, p.forecast_end) for p in selected if p.forecast_start), (None, None))
    scope = f'{len(selected)} selected accounts; full filtered cohort'
    metrics = [
        CohortMetric(label='Upcoming due instruments', value=recorded + inferred, unit='instruments', scope=scope,
            definition='Deduplicated supported, unsuppressed requirements; explicitly stopped and excluded instruments omitted. Not orders.',
            caption=f'{recorded:,} recorded · {inferred:,} inferred · next {filters.window_days} days' + (' + past-due review' if filters.include_past_due else '')),
        CohortMetric(label='Expected calibrations · next 3 months', value=expected, unit='calibration events', scope=scope + '; all services',
            definition='Sum of supported unconditional quarter-total calibration forecasts. Category filters select accounts, not product-specific forecasts.',
            caption=f'{len(forecast):,}/{len(selected):,} accounts supported · {dates[0] or "—"}–{dates[1] or "—"} · directional'),
        CohortMetric(label='Accounts needing activity review', value=flagged if inactivity_supported else None, unit='accounts', scope=scope,
            definition='Supported, unsuppressed cadence/volume-review flags; not confirmed churn.',
            caption=f'{inactivity_supported:,}/{len(selected):,} accounts with evidence'),
        CohortMetric(label='Open follow-ups', value=len(tasks), unit='tasks', scope=scope + '; local workflow',
            definition=f'Open local follow-ups; overdue uses workflow date {metadata.workflow_today}, separately from historical evidence.',
            caption=f'{overdue:,} overdue · agreed next steps')]
    # Round-robin stable sample across matching groups: selection must not hide other groups.
    buckets = [[p for p in matched if p.cluster_id == cid] for cid in features.IDS]
    sampled, index = [], 0
    target = len(matched) if display_limit == 0 else display_limit
    while len(sampled) < target and any(index < len(b) for b in buckets):
        for bucket in buckets:
            if index < len(bucket) and len(sampled) < target:
                sampled.append(bucket[index])
        index += 1
    summaries = [ClusterSummary(id=cid, label=features.LABELS[i], color=features.COLORS[i], urgency=model['centers'][i][0],
                size=model['centers'][i][1], matching_count=sum(p.cluster_id == cid for p in matched)) for i, cid in enumerate(features.IDS)]
    scenario_result = None
    if scenario:
        scenario_result = {'currency': scenario.currency, 'quantity_unit': 'calibration_event', 'scope': 'all-services forecast for selected accounts',
            'target_start': dates[0], 'target_end': dates[1], 'assumptions': scenario.model_dump(),
            'expected_quantity': expected, 'supported_account_count': len(forecast), 'excluded_account_count': len(selected) - len(forecast),
            'estimated_contribution': round(expected * scenario.unit_contribution, 2) if expected is not None else None,
            'interpretation': 'scenario_not_outreach_uplift'}
    revision = hashlib.sha256(json.dumps([signature, filters.model_dump(), cluster_id,
        [(p.customer_id, p.owner, p.due_recorded, p.due_inferred, p.activity_flagged) for p in selected],
        [f.model_dump() for f in tasks], scenario.model_dump() if scenario else None], sort_keys=True).encode()).hexdigest()[:16]
    return OpportunityResponse(metadata=metadata, rule_version=features.RULE_VERSION, model_version=signature,
        selection_revision=revision, filters=filters, selected_cluster=cluster_id, filter_options=options,
        matching_count=len(matched), selected_count=len(selected), unassigned_count=sum(p.cluster_id is None for p in matched),
        displayed_count=len(sampled), points=sampled, clusters=summaries, quality=model['quality'], metrics=metrics,
        recorded_total=recorded, inferred_total=inferred, forecast_supported=len(forecast), inactivity_supported=inactivity_supported,
        overdue_count=overdue, unassigned_owner_count=sum(p.owner is None and p.cluster_id is not None for p in selected),
        due_followups=[f for f in tasks if f.due_date <= metadata.workflow_today][:5],
        items=selected[offset:offset + limit], limit=limit, offset=offset, scenario=scenario_result)
