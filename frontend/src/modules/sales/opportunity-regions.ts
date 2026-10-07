import type { OpportunityResponse } from "@/types/opportunities";

/** Exact nearest-center regions for the same model used by the API. */
export function opportunityRegions(clusters: OpportunityResponse["clusters"]) {
  return clusters.map((center) => {
    let polygon: number[][] = [
      [0, 0],
      [100, 0],
      [100, 100],
      [0, 100],
    ];
    for (const other of clusters) {
      if (other.id === center.id) continue;
      const a = 2 * (other.urgency - center.urgency);
      const b = 2 * (other.size - center.size);
      const bound =
        other.urgency ** 2 +
        other.size ** 2 -
        center.urgency ** 2 -
        center.size ** 2;
      const next: number[][] = [];
      for (let i = 0; i < polygon.length; i++) {
        const p = polygon[i],
          q = polygon[(i + 1) % polygon.length];
        const dp = a * p[0] + b * p[1] - bound;
        const dq = a * q[0] + b * q[1] - bound;
        if (dp <= 1e-8) next.push(p);
        if ((dp < 0 && dq > 0) || (dp > 0 && dq < 0)) {
          const t = dp / (dp - dq);
          next.push([p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])]);
        }
      }
      polygon = next;
    }
    return { ...center, polygon };
  });
}

/** Median-centered percentile position; not a probability or negative quantity. */
export const mapPosition = (percentile: number) => 2 * percentile - 100;
