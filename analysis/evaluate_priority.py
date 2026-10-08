"""Rank-stability (sensitivity) check for the priority weights.

Usage: PECAL_ANALYTICS_ROOT=data/runtime/analytics-v2 ... actually v3:
  PECAL_ANALYTICS_ROOT=data/runtime/analytics-v3 uv run python -m analysis.evaluate_priority --snapshot-id private-snapshot --sample 250 --seed 7

Rebuilds account actions for a seeded sample under perturbed weight sets
(near-default Dirichlet draws plus targeted extremes) and reports Spearman
rank correlation plus top-decile overlap against the default weights.
Frozen artifacts are never modified; nothing is published.
"""

from __future__ import annotations

import argparse
import json
import random

from backend.app.capabilities.data import composition
from backend.app.capabilities.data.service import load_snapshot
from backend.app.capabilities.insights.actions import DEFAULT_WEIGHTS
from backend.app.capabilities.insights.compat import ranking_fn_for_composition


def spearman(order_a: list[str], order_b: list[str]) -> float:
    rank_b = {cid: i for i, cid in enumerate(order_b)}
    common = [cid for cid in order_a if cid in rank_b]
    n = len(common)
    if n < 2:
        return 1.0
    rank_a = {cid: i for i, cid in enumerate(common)}
    diffs = [(rank_a[c] - rank_b[c]) for c in common]
    return 1 - 6 * sum(d * d for d in diffs) / (n * (n * n - 1))


def draw_weights(rng: random.Random, base: dict[str, float], concentration: float = 40.0):
    import math

    draws = {k: rng.gammavariate(base[k] * concentration, 1.0) for k in base}
    total = sum(draws.values())
    return {k: draws[k] / total for k in base}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--sample", type=int, default=250)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--perturbations", type=int, default=24)
    parser.add_argument("--today", default="2026-10-07")
    args = parser.parse_args()

    snapshot = load_snapshot(args.snapshot_id)
    stats = composition.snapshot_stats(args.snapshot_id)
    rng = random.Random(args.seed)
    customers = sorted(p.customer_id for p in snapshot["profiles"])
    sample = rng.sample(customers, min(args.sample, len(customers)))

    def order_for(weights):
        rank = ranking_fn_for_composition(stats, weights=weights, today=args.today)
        scored = []
        for customer_id in sample:
            local = composition._local_inputs(args.snapshot_id, customer_id, args.today)
            action = rank(
                local["profile"], local["requirements"], local["prediction"],
                local["peers"], local["workflow"],
            )
            if action is not None:
                scored.append((customer_id, action.priority_score))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return [cid for cid, _ in scored]

    reference = order_for(dict(DEFAULT_WEIGHTS))
    sets = []
    for _ in range(args.perturbations):
        sets.append(("dirichlet", draw_weights(rng, DEFAULT_WEIGHTS)))
    no_ev = dict(DEFAULT_WEIGHTS)
    no_ev["expected_value"] = 0.0
    total = sum(no_ev.values())
    sets.append(("no-expected-value", {k: v / total for k, v in no_ev.items()}))
    heavy_ev = dict(DEFAULT_WEIGHTS)
    heavy_ev["expected_value"] = 0.5
    total = sum(heavy_ev.values())
    sets.append(("heavy-expected-value", {k: v / total for k, v in heavy_ev.items()}))

    results = []
    top_n = max(1, len(reference) // 10)
    top_reference = set(reference[:top_n])
    for name, weights in sets:
        order = order_for(weights)
        overlap = len(set(order[:top_n]) & top_reference) / top_n if top_n else 1.0
        results.append({"variant": name, "spearman": round(spearman(reference, order), 3),
                        "top_decile_overlap": round(overlap, 3)})
    rhos = [r["spearman"] for r in results]
    print(json.dumps({
        "sample": len(sample),
        "default_weights": DEFAULT_WEIGHTS,
        "mean_spearman": round(sum(rhos) / len(rhos), 3),
        "min_spearman": round(min(rhos), 3),
        "mean_top_decile_overlap": round(
            sum(r["top_decile_overlap"] for r in results) / len(results), 3),
        "variants": results,
    }, indent=1))


if __name__ == "__main__":
    main()
