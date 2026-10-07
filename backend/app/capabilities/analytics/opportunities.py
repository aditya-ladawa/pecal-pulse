"""Frozen opportunity features and four-cluster assessment on the visible axes.

Not a revenue, churn or treatment-effect model. Fit on source evidence, then
apply workflow suppressions through the composition service without refitting.
"""
from datetime import date, timedelta
from itertools import permutations
import math
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from threadpoolctl import threadpool_limits

RULE_VERSION = 'opportunity-v1'
COLORS = ['#638768', '#a092c1', '#db9c65', '#88a8bd']
LABELS = ['Act now', 'Plan larger opportunities', 'Focused follow-up', 'Nurture and monitor']


def due_requirements(requirements, reference, days, inferred=True, past_due=False, suppressed=frozenset()):
    """Recorded dominates inferred for the same instrument, even outside the window."""
    ref = date.fromisoformat(reference)
    first = ref - timedelta(days=90) if past_due else ref + timedelta(days=1)
    last = ref + timedelta(days=days)
    best, stopped = {}, set()
    rank = {'recorded': 3, 'nominal_interval': 2, 'repeat_history': 1, 'unknown': 0}
    for r in requirements:
        if r.stopped is True:
            stopped.add(r.instrument_id)
        previous = best.get(r.instrument_id)
        if previous is None or (rank[r.kind], r.id) > (rank[previous.kind], previous.id):
            best[r.instrument_id] = r
    result = []
    for r in best.values():
        if r.instrument_id in stopped or r.eligibility == 'excluded' or r.kind == 'unknown':
            continue
        if r.kind != 'recorded' and not inferred:
            continue
        # Match both individual evidence and the existing bundled action reason.
        reason_id = f'{r.customer_id}:upcoming:{r.group_id or "__ungrouped__"}:{r.window_start}:{r.window_end}'
        if r.id in suppressed or reason_id in suppressed or not r.window_start or not r.window_end:
            continue
        try:
            start, end = date.fromisoformat(r.window_start), date.fromisoformat(r.window_end)
        except ValueError:
            continue
        if end >= start and end >= first and start <= last:
            result.append(r)
    return result


def raw_components(reqs, prediction, history_volume, discovery, reference):
    recorded = sum(r.kind == 'recorded' for r in reqs)
    inferred = len(reqs) - recorded
    due = recorded + inferred
    urgency = None
    if reqs:
        nearest = min((date.fromisoformat(r.window_start) - date.fromisoformat(reference)).days for r in reqs)
        urgency = 100 * max(.25, min(1., 1 - max(0, nearest) / 120))
    inactive = bool(prediction and prediction.inactivity.support.status == 'supported' and prediction.inactivity.flagged)
    gap = None
    if inactive:
        sig = prediction.inactivity
        if sig.baseline_volume is not None:
            gap = max(0., sig.baseline_volume - sig.recent_volume)
        measures = [max(0., min(1., sig.deficit_fraction))] if sig.deficit_fraction is not None else []
        if sig.recency_to_cadence is not None:
            measures.append(max(0., min(1., (sig.recency_to_cadence - 1) / 2)))
        if measures:
            urgency = max(urgency or 0., 100 * max(measures))
    discovery_scale = float(history_volume) if discovery and history_volume is not None else None
    if discovery_scale is not None and discovery_scale > 0:
        urgency = max(urgency or 0., 25.)
    return dict(due_recorded=recorded, due_inferred=inferred, due_quantity=due if due else None,
                activity_gap=gap, discovery_scale=discovery_scale, urgency=urgency)


def normalization(rows):
    result = {}
    for key in ('due_quantity', 'activity_gap', 'discovery_scale'):
        values = [r[key] for r in rows if r[key] is not None and r[key] > 0]
        result[key] = float(np.percentile(np.log1p(values), 95)) if values else 1.
    return result


def coordinates(row, anchors):
    channels = []
    for key, weight in [('due_quantity', 1.), ('activity_gap', 1.), ('discovery_scale', .5)]:
        value = row[key]
        if value is not None:
            score = min(100., 100 * math.log1p(value) / max(anchors[key], .001)) * weight
            channels.append((score, key))
    if row['urgency'] is None or not channels:
        return None, None, None
    size, basis = max(channels)
    return round(row['urgency'], 3), round(size, 3), basis


def fit_map(rows):
    anchors = normalization(rows)
    xy = np.array([c[:2] for row in rows if (c := coordinates(row, anchors))[0] is not None])
    # Priority-zone fallback remains useful for sparse or unstable populations.
    quality = {'sample_count': len(xy), 'silhouette': None, 'seed_agreement': None, 'outlier_agreement': None}
    model = None
    with threadpool_limits(limits=1):
        if len(xy) >= 20 and len(np.unique(xy, axis=0)) >= 4:
            model = KMeans(n_clusters=4, n_init=20, random_state=42).fit(xy)
            other = KMeans(n_clusters=4, n_init=20, random_state=7).fit(xy)
            quality['silhouette'] = float(silhouette_score(xy, model.labels_, sample_size=min(1500, len(xy)), random_state=42))
            quality['seed_agreement'] = float(adjusted_rand_score(model.labels_, other.labels_))
            # Refit without top 1% size scores; compare assignments on the full cohort.
            trimmed = xy[xy[:, 1] <= np.percentile(xy[:, 1], 99)]
            if len(np.unique(trimmed, axis=0)) >= 4:
                trimmed_model = KMeans(n_clusters=4, n_init=20, random_state=42).fit(trimmed)
                quality['outlier_agreement'] = float(adjusted_rand_score(model.labels_, trimmed_model.predict(xy)))
            counts = np.bincount(model.labels_, minlength=4).tolist()
            quality['cluster_sizes'] = counts
            valid = (quality['silhouette'] >= .25 and quality['seed_agreement'] >= .8
                     and (quality['outlier_agreement'] or 0) >= .8 and min(counts) >= max(3, .01 * len(xy)))
            if not valid:
                model = None
    if model is None:
        centers = [[75., 75.], [25., 75.], [75., 25.], [25., 25.]]
        quality['method'] = 'priority_zones'
        quality['note'] = 'Four explicit urgency/size zones; stable natural clusters were not established.'
    else:
        # Match actual centers to intuitive profiles rather than arbitrary label numbers.
        target = np.array([[100, 100], [0, 100], [100, 0], [0, 0]])
        order = min(permutations(range(4)), key=lambda p: sum(np.sum((model.cluster_centers_[p[i]] - target[i]) ** 2) for i in range(4)))
        centers = model.cluster_centers_[list(order)].tolist()
        quality['method'] = 'kmeans'
        quality['note'] = 'KMeans on urgency/size; labels describe relative center profiles, not measured sales outcomes.'
    return {'rule_version': RULE_VERSION, 'anchors': anchors, 'centers': centers, 'quality': quality}


def assign(urgency, size, model):
    if urgency is None or size is None:
        return None
    if model['quality']['method'] == 'priority_zones':
        return ['act-now', 'plan-larger', 'focused-follow-up', 'nurture'][0 if urgency >= 50 and size >= 50 else 1 if size >= 50 else 2 if urgency >= 50 else 3]
    index = min(range(4), key=lambda i: (urgency - model['centers'][i][0]) ** 2 + (size - model['centers'][i][1]) ** 2)
    return ['act-now', 'plan-larger', 'focused-follow-up', 'nurture'][index]

IDS = ['act-now', 'plan-larger', 'focused-follow-up', 'nurture']
