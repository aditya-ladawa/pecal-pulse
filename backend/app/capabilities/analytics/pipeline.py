"""Reproducible offline analytics; never invoked by API requests."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from math import log1p
from platform import python_version

import numpy as np
import sklearn
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (adjusted_rand_score, average_precision_score,
                             brier_score_loss, mean_absolute_error, roc_auc_score,
                             silhouette_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import (FEATURE_NAMES, feature_row, inactivity_evidence, index_history,
                       iso_month, month_index, next_month_window, observed_months,
                       support, volume_baselines)
from .sectors import build_sectors
from .snapshot import normalize_snapshot

VERSION = "analytics-v2"
SEED = 42


def _activity_metrics(y: np.ndarray, probability: np.ndarray) -> dict:
    return {"n": len(y), "roc_auc": float(roc_auc_score(y, probability)) if len(set(y)) > 1 else None,
            "average_precision": float(average_precision_score(y, probability)) if len(set(y)) > 1 else None,
            "brier": float(brier_score_loss(y, probability))}


def _volume_metrics(y: np.ndarray, predicted: np.ndarray) -> dict:
    error = predicted - y
    return {"n": len(y), "mae": float(mean_absolute_error(y, predicted)),
            "wape": float(np.abs(error).sum() / y.sum()) if y.sum() else None,
            "bias": float(error.mean())}


def _observations(histories: dict, start: int, end: int) -> dict:
    # All feature cutoffs and their three-month labels are known by `end`.
    records = {"train": [], "calibration": [], "validation": [], "test": []}
    for customer_id, history in histories.items():
        for cutoff in range(start + 6, end - 2):
            if support(history, cutoff)["status"] != "supported":
                continue
            if cutoff <= end - 17:
                stage = "train"
            elif cutoff == end - 14:
                stage = "calibration"
            elif cutoff == end - 11:
                stage = "validation"
            elif end - 8 <= cutoff <= end - 3:
                stage = "test"
            else:
                continue
            future = sum(history.get(t, {}).get("calibration_events", 0)
                         for t in range(cutoff + 1, cutoff + 4))
            vector, _ = feature_row(history, cutoff)
            records[stage].append({"customer_id": customer_id, "cutoff": cutoff,
                "x": vector, "activity": int(future > 0), "volume": future,
                "baselines": volume_baselines(history, cutoff)})
    return records


def _segment(histories: dict, end: int) -> tuple[dict, list, list]:
    ids, vectors, raw = [], [], []
    for customer_id, history in sorted(histories.items()):
        active = observed_months(history, end)
        if len(active) < 2 or end - active[0] + 1 < 12:
            continue
        recent = [history.get(t, {}).get("calibration_events", 0) for t in range(end - 23, end + 1)]
        positive = [v for v in recent if v > 0]
        recency = end - active[-1]
        breadth = max((row["equipment_group_count"] for t, row in history.items() if t <= end), default=0)
        raw.append({"volume_24m": sum(recent), "active_months_24m": len(positive),
                    "recency_months": recency, "max_monthly_group_breadth": breadth,
                    "observed_months": min(24, end - active[0] + 1)})
        vectors.append([log1p(sum(recent)), len(positive) / min(24, end - active[0] + 1), recency,
                        log1p(sum(positive) / len(positive) if positive else 0),
                        float(np.std(recent) / (np.mean(recent) + 1)), log1p(breadth)])
        ids.append(customer_id)
    if len(ids) < 12:
        return {}, [], []
    z = StandardScaler().fit_transform(vectors)
    candidates, fitted = [], {}
    unique_rows = len(np.unique(z, axis=0))
    for k in range(3, min(6, len(ids) // 3, unique_rows) + 1):
        model = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(z)
        alternate = KMeans(n_clusters=k, n_init=10, random_state=7).fit(z)
        sizes = Counter(model.labels_)
        candidate = {"k": k, "silhouette": float(silhouette_score(z, model.labels_,
                         sample_size=min(1600, len(z)), random_state=SEED)),
                     "seed_ari": float(adjusted_rand_score(model.labels_, alternate.labels_)),
                     "cluster_sizes": [sizes[j] for j in range(k)]}
        candidates.append(candidate)
        fitted[k] = model
    if not candidates:
        return {}, [], []
    selected = max(candidates, key=lambda item: (item["silhouette"], item["seed_ari"]))
    labels = fitted[selected["k"]].labels_
    assigned = {customer: f"segment-{int(label) + 1}" for customer, label in zip(ids, labels)}
    summaries = []
    for j in range(selected["k"]):
        items = [item for item, label in zip(raw, labels) if label == j]
        means = {name: float(np.mean([item[name] for item in items])) for name in raw[0]}
        if means["active_months_24m"] >= 10:
            label = "Frequent, high-volume"
        elif means["recency_months"] >= 12:
            label = "Long inactive"
        elif means["volume_24m"] < 20:
            label = "Occasional, low-volume"
        else:
            label = "Intermittent batches"
        summaries.append({"id": f"segment-{j + 1}", "label": label, "method": "kmeans",
                          "customers": len(items), "description": "Observed behavior over up to 24 complete months",
                          "feature_means": means})
    return assigned, summaries, candidates


def build_outputs(snapshot: dict) -> dict:
    """Train/evaluate on a normalized snapshot and return JSON-ready artifacts.

    Input keys are Member 1's `manifest`, `profiles`, `history`, `month_grid`.
    The typed result of data.service.load_snapshot is accepted directly. Real snapshots
    must come from Member 1; no mock to historical conversion is implicit.
    """
    snapshot = normalize_snapshot(snapshot)
    manifest = snapshot["manifest"]
    snapshot_id = manifest["snapshot_id"]
    reference = manifest["reference_date"]
    complete = manifest["complete_through_month"]
    if reference[:7] != complete:
        raise ValueError("Reference date and complete-through month differ")
    window_start, window_end = next_month_window(reference)
    start, end = month_index(manifest["history_start"]), month_index(complete)
    if start > end:
        raise ValueError("History start follows complete-through month")
    histories = index_history(snapshot["history"], complete)
    if any(t < start for history in histories.values() for t in history):
        raise ValueError("History precedes manifest history_start")
    profiles = snapshot["profiles"]
    profile_ids = [p["customer_id"] for p in profiles]
    if len(profile_ids) != len(set(profile_ids)):
        raise ValueError("Duplicate customer profile")
    if set(histories) - set(profile_ids):
        raise ValueError("History has unknown customer ID")
    complete_coverage = snapshot["month_grid"] == [iso_month(t) for t in range(start, end + 1)]
    assigned, segments, segment_candidates = _segment(histories, end) if complete_coverage else ({}, [], [])
    records = _observations(histories, start, end) if complete_coverage and end - start + 1 >= 32 else {}
    supported = bool(records) and all(len(records[stage]) >= 5 for stage in
                                      ("train", "calibration", "validation", "test"))
    volume_supported = supported
    activity_model = volume_model = calibrator = None
    activity_choice = volume_choice = None
    activity_eval, volume_eval = {}, {}
    reliability = []
    prevalence = None
    if supported:
        def arrays(stage: str):
            rows = records[stage]
            return (np.asarray([r["x"] for r in rows]),
                    np.asarray([r["activity"] for r in rows]),
                    np.asarray([r["volume"] for r in rows]))
        x_train, y_train, v_train = arrays("train")
        if len(set(y_train)) < 2:
            supported = False
        else:
            prevalence = float(y_train.mean())
    if supported:
        activity_models = {
            "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=1200, random_state=SEED)),
            "boosted_trees": HistGradientBoostingClassifier(max_leaf_nodes=15, max_iter=180,
                l2_regularization=10, early_stopping=False, random_state=SEED),
        }
        x_cal, y_cal, _ = arrays("calibration")
        x_val, y_val, v_val = arrays("validation")
        x_test, y_test, v_test = arrays("test")
        candidates = {}
        for name, model in activity_models.items():
            model.fit(x_train, y_train)
            raw_cal = model.predict_proba(x_cal)[:, 1]
            iso = IsotonicRegression(out_of_bounds="clip").fit(raw_cal, y_cal)
            for calibration, mapping in (("raw", None), ("isotonic", iso)):
                key = f"{name}/{calibration}"
                raw_val = model.predict_proba(x_val)[:, 1]
                probability = mapping.predict(raw_val) if mapping else raw_val
                candidates[key] = (model, mapping)
                activity_eval[key] = {"validation": _activity_metrics(y_val, probability)}
        activity_eval["prevalence_baseline"] = {"validation": _activity_metrics(y_val, np.full(len(y_val), prevalence))}
        activity_eval["recency_baseline"] = {"validation": _activity_metrics(y_val, np.exp(-x_val[:, 3] / 6))}
        activity_choice = min(activity_eval, key=lambda key: activity_eval[key]["validation"]["brier"])
        if activity_choice in candidates:
            activity_model, calibrator = candidates[activity_choice]
        for key, (model, mapping) in candidates.items():
            raw = model.predict_proba(x_test)[:, 1]
            activity_eval[key]["test"] = _activity_metrics(y_test, mapping.predict(raw) if mapping else raw)
        activity_eval["prevalence_baseline"]["test"] = _activity_metrics(y_test, np.full(len(y_test), prevalence))
        activity_eval["recency_baseline"]["test"] = _activity_metrics(y_test, np.exp(-x_test[:, 3] / 6))
        if activity_model:
            raw_selected = activity_model.predict_proba(x_test)[:, 1]
            selected_test = calibrator.predict(raw_selected) if calibrator else raw_selected
        elif activity_choice == "prevalence_baseline":
            selected_test = np.full(len(y_test), prevalence)
        else:
            selected_test = np.exp(-x_test[:, 3] / 6)
        for bin_number in range(10):
            lower, upper = bin_number / 10, (bin_number + 1) / 10
            mask = (selected_test >= lower) & (selected_test < upper if bin_number < 9 else selected_test <= 1)
            if mask.any():
                reliability.append({"probability_lower": float(lower), "n": int(mask.sum()),
                    "predicted": float(selected_test[mask].mean()),
                    "observed": float(y_test[mask].mean())})
    if volume_supported:
        x_val, _, v_val = arrays("validation")
        x_test, _, v_test = arrays("test")
        volume_models = {"boosted_poisson": HistGradientBoostingRegressor(loss="poisson", max_leaf_nodes=15,
            max_iter=200, l2_regularization=20, early_stopping=False, random_state=SEED)} if v_train.sum() > 0 else {}
        for name, model in volume_models.items():
            model.fit(x_train, v_train)
            volume_eval[name] = {"validation": _volume_metrics(v_val, np.maximum(0, model.predict(x_val))),
                                 "test": _volume_metrics(v_test, np.maximum(0, model.predict(x_test)))}
        for name in ("previous_3_months", "previous_12_months_divided_by_4", "same_3_months_last_year"):
            volume_eval[name] = {stage: _volume_metrics(
                arrays(stage)[2], np.asarray([r["baselines"][name] for r in records[stage]]))
                for stage in ("validation", "test")}
        volume_choice = min(volume_eval, key=lambda key: volume_eval[key]["validation"]["mae"])
        volume_model = volume_models.get(volume_choice)
    predictions = []
    for profile in profiles:
        customer_id = profile["customer_id"]
        history = histories.get(customer_id, {})
        status = support(history, end)
        volume_status = dict(status)
        if not supported and status["status"] == "supported":
            status = {**status, "status": "unavailable", "reason": "No validated chronological model stages"}
        if not volume_supported and volume_status["status"] == "supported":
            volume_status = {**volume_status, "status": "unavailable", "reason": "No validated chronological volume stages"}
        vector = None
        if status["status"] == "supported" or volume_status["status"] == "supported":
            vector, details = feature_row(history, end)
            x = np.asarray([vector])
            if status["status"] != "supported":
                probability = None
            elif activity_model:
                raw = activity_model.predict_proba(x)[:, 1]
                probability = float(calibrator.predict(raw)[0] if calibrator else raw[0])
            elif activity_choice == "prevalence_baseline":
                probability = prevalence
            else:
                probability = float(np.exp(-vector[3] / 6))
            expected = (float(max(0, volume_model.predict(x)[0])) if volume_model else
                        volume_baselines(history, end)[volume_choice]) if volume_status["status"] == "supported" else None
        else:
            active = observed_months(history, end)
            details = {"recency_months": end - active[-1] if active else None,
                       "cadence_months": float(np.median(np.diff(active))) if len(active) > 1 else None}
            probability = expected = None
        inactivity = inactivity_evidence(history, end)
        if not complete_coverage:
            inactivity = {**inactivity, "flagged": False, "recency_to_cadence": None,
                "baseline_volume": None, "deficit_fraction": None, "reasons": [],
                "support": {**inactivity["support"], "status": "unavailable",
                            "reason": "Snapshot month_grid does not certify continuous history"}}
        predictions.append({"snapshot_id": snapshot_id, "customer_id": customer_id,
            "reference_date": reference, "segment_id": assigned.get(customer_id),
            "activity": {"target": "any_calibration_next_3_months", "probability": probability,
                "window_start": window_start, "window_end": window_end,
                "model_version": VERSION, "support": status},
            "calibration_volume": {"metric": "calibration_events", "horizon_months": 3,
                "window_start": window_start, "window_end": window_end, "expected_total": expected,
                "lower": None, "upper": None, "interval_level": None, "monthly": None,
                "method": volume_choice or "unavailable", "model_version": VERSION, "support": volume_status},
            "recency_months": details["recency_months"], "cadence_months": details["cadence_months"],
            "inactivity": inactivity, "explanation":
                [{"feature": name, "value": float(value), "contribution": None}
                 for name, value in zip(FEATURE_NAMES, vector)] if vector else []})
    sectors = build_sectors(profiles, histories, manifest["history_start"], complete,
                            covered_months=snapshot["month_grid"])
    for payload in (sectors,):
        payload.update({"snapshot_id": snapshot_id, "reference_date": reference, "model_version": VERSION})
    stage_counts = {stage: len(records.get(stage, [])) for stage in ("train", "calibration", "validation", "test")}
    report = {"snapshot_id": snapshot_id, "reference_date": reference, "model_version": VERSION,
        "seed": SEED, "input_sha256": hashlib.sha256(json.dumps(snapshot, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
        "runtime": {"python": python_version(), "numpy": np.__version__, "scikit_learn": sklearn.__version__},
        "feature_names": list(FEATURE_NAMES),
        "source_quality_flags": manifest["quality_flags"],
        "history_coverage": {"continuous_complete_grid": complete_coverage,
                             "covered_months": len(snapshot["month_grid"])},
        "eligibility": "At least 2 active months, 12 months observed tenure and activity within last 12 months",
        "target": "at least one observed calibration in next three complete months",
        "volume_unit": "calibration_events", "feature_cutoff": complete,
        "label_window": {"start": window_start, "end": window_end},
        "evaluation_unit": "customer-origin; repeated origins for an account are not independent people",
        "stage_cutoffs": {"train_end": iso_month(end - 17), "calibration": iso_month(end - 14),
            "validation": iso_month(end - 11), "test_start": iso_month(end - 8),
            "test_end": iso_month(end - 3)},
        "stage_label_end": {"train": iso_month(end - 14), "calibration": iso_month(end - 11),
            "validation": iso_month(end - 8), "test": iso_month(end)},
        "stage_rows": stage_counts, "supported_customers": sum(p["activity"]["support"]["status"] == "supported" for p in predictions),
        "stage_unique_customers": {stage: len({row["customer_id"] for row in records.get(stage, [])})
            for stage in stage_counts},
        "total_customers": len(predictions), "selected_activity": activity_choice,
        "volume_supported_customers": sum(p["calibration_volume"]["support"]["status"] == "supported" for p in predictions),
        "selected_volume": volume_choice, "activity_metrics": activity_eval,
        "volume_metrics": volume_eval, "activity_reliability": reliability,
        "segment_candidates": segment_candidates,
        "limitations": ["No churn or causal outreach label", "No monthly customer forecast or interval validation",
                        "Inactivity may reflect changed timing, equipment changes, seasonality or incomplete records",
                        "Model selection uses validation only; test metrics are descriptive"]}
    return {"manifest": {"snapshot_id": snapshot_id, "reference_date": reference,
                "model_version": VERSION, "source_complete_through_month": complete,
                "ready": supported and volume_supported, "activity_ready": supported,
                "volume_ready": volume_supported},
            "predictions": predictions, "segments": segments, "sectors": sectors,
            "model_report": report}
