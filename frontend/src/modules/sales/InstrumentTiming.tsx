"use client";
import { useEffect, useState } from "react";
import { Card, InfoHint } from "@/components/ui/Primitives";
import type { Detail } from "@/types/sales-v2";

export function InstrumentTiming({ detail: d }: { detail: Detail }) {
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [d.profile.customer_id]);
  const tiers = d.requirement_tier_counts;
  const total =
    Object.values(tiers || {}).reduce((a, b) => a + b, 0) ||
    d.requirements.length;
  const groups = new Map<
    string,
    {
      label: string;
      start: string | null;
      end: string | null;
      kind: string;
      excluded: boolean;
      ids: Set<string>;
    }
  >();
  for (const r of d.requirements) {
    const key = [
      r.group_id,
      r.kind,
      r.window_start,
      r.window_end,
      r.eligibility,
    ].join(":");
    const row = groups.get(key) || {
      label:
        d.portfolio.find((p) => p.group_id === r.group_id)?.group_label ||
        "Equipment category unavailable",
      start: r.window_start,
      end: r.window_end,
      kind: r.kind,
      excluded: r.eligibility === "excluded",
      ids: new Set<string>(),
    };
    row.ids.add(r.instrument_id);
    groups.set(key, row);
  }
  const rows = [...groups.values()].sort((a, b) => b.ids.size - a.ids.size);
  const safePage = Math.min(page, Math.max(0, Math.ceil(rows.length / 5) - 1));
  const date = (value: string) =>
    new Date(value + "T12:00:00Z").toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  return (
    <Card className="timing-coverage">
      <div className="card-heading">
        <h2>Calibration dates</h2>
        <InfoHint label="calibration dates">
          Counts cover the full account. Recorded dates come from source
          records; estimated windows come from intervals or repeat history.
          Timing needs confirmation before outreach. Grouped details below cover
          only the loaded sample, not all {total.toLocaleString()} records.
        </InfoHint>
      </div>
      <div className="timing-counts">
        <div>
          <strong>
            {(
              tiers?.recorded ??
              d.requirements.filter((r) => r.kind === "recorded").length
            ).toLocaleString()}
          </strong>
          <span>Recorded dates</span>
        </div>
        <div>
          <strong>
            {(
              (tiers?.nominal_interval ??
                d.requirements.filter((r) => r.kind === "nominal_interval")
                  .length) +
              (tiers?.repeat_history ??
                d.requirements.filter((r) => r.kind === "repeat_history")
                  .length)
            ).toLocaleString()}
          </strong>
          <span>Estimated windows</span>
        </div>
        <div>
          <strong>
            {(
              tiers?.unknown ??
              d.requirements.filter((r) => r.kind === "unknown").length
            ).toLocaleString()}
          </strong>
          <span>Timing missing</span>
        </div>
      </div>
      <details>
        <summary>Grouped date details · loaded sample</summary>
        <small>
          {d.requirements.length.toLocaleString()} of {total.toLocaleString()}{" "}
          source records loaded.
        </small>
        <div className="integrated-table">
          <table>
            <thead>
              <tr>
                <th>Equipment / timing</th>
                <th>Instruments</th>
                <th>Date source</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(safePage * 5, safePage * 5 + 5).map((r, i) => (
                <tr key={safePage * 5 + i}>
                  <td>
                    {r.label}
                    <small>
                      {r.start
                        ? [
                            ...new Set(
                              [r.start, r.end].filter((v): v is string => !!v),
                            ),
                          ]
                            .map(date)
                            .join(" – ")
                        : "Timing to confirm"}
                      {r.excluded && " · Excluded from outreach"}
                    </small>
                  </td>
                  <td>{r.ids.size}</td>
                  <td>
                    {r.kind === "recorded"
                      ? "Recorded"
                      : r.kind === "unknown"
                        ? "Missing"
                        : "Estimated"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length > 5 && (
          <div className="integrated-pagination">
            <button
              className="button"
              disabled={safePage === 0}
              onClick={() => setPage(safePage - 1)}
            >
              Previous dates
            </button>
            <small>
              {safePage + 1} / {Math.ceil(rows.length / 5)}
            </small>
            <button
              className="button"
              disabled={(safePage + 1) * 5 >= rows.length}
              onClick={() => setPage(safePage + 1)}
            >
              Next dates
            </button>
          </div>
        )}
        {!rows.length && <p>No date details available.</p>}
      </details>
    </Card>
  );
}
