"use client";
import { Card, InfoHint } from "@/components/ui/Primitives";
import type { Action, Detail } from "@/types/sales-v2";

function equipmentLabel(detail: Detail, reason: Action["reasons"][number]) {
  const groupId = reason.id.split(":").slice(-3)[0];
  return (
    detail.portfolio.find((p) => p.group_id === groupId)?.group_label ||
    groupId?.replace(/^GRP-/, "").replaceAll("_", " ") ||
    "Equipment"
  );
}

export function BatchReasonSummary({
  detail,
  reason: r,
}: {
  detail: Detail;
  reason: Action["reasons"][number];
}) {
  const dates = r.id.split(":").slice(-2);
  const timing = [...new Set(dates)]
    .filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date))
    .map((date) =>
      new Date(date + "T12:00:00Z").toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      }),
    )
    .join(" – ");
  const past = r.title.includes("past due");
  const estimated = r.unknowns.some((u) => u.includes("inferred"));
  const upcoming = r.type === "upcoming";
  const groupId = r.id.split(":").slice(-3)[0];
  const pastWork = upcoming
    ? detail.portfolio.find((p) => p.group_id === groupId)
    : undefined;
  const historyPeriod = pastWork
    ? [
        ...new Set(
          [pastWork.window_start, pastWork.window_end].map((date) =>
            new Date(date.slice(0, 7) + "-01T12:00:00Z").toLocaleDateString(
              undefined,
              { month: "short", year: "numeric" },
            ),
          ),
        ),
      ].join(" – ")
    : "";
  return (
    <div className="batch-summary">
      {upcoming && (
        <div className="batch-quantity">
          <strong>
            {(r.quantity ?? r.instrument_ids.length).toLocaleString()}
          </strong>
          <small>instruments</small>
        </div>
      )}
      <div className="batch-context">
        <strong>
          {upcoming
            ? equipmentLabel(detail, r)
            : r.type === "inactivity"
              ? "Check reduced activity"
              : "Explore an additional service"}
        </strong>
        <span>
          {upcoming
            ? timing || "Timing to confirm"
            : "A conversation worth reviewing"}
        </span>
        <div className="batch-tags">
          <span className={past ? "batch-status review" : "batch-status"}>
            {upcoming
              ? past
                ? "Date passed · check status"
                : "Upcoming need"
              : "Review opportunity"}
          </span>
          {upcoming && (
            <small>
              {estimated ? "Estimated due window" : "Recorded due date"}
            </small>
          )}
        </div>
        {pastWork && (
          <small className="batch-past-work">
            Previous work in this category:{" "}
            {pastWork.calibration_events.toLocaleString()} calibrations ·{" "}
            {historyPeriod}
          </small>
        )}
      </div>
      <InfoHint
        label={`evidence for ${upcoming ? equipmentLabel(detail, r) + " " + timing : r.title}`}
      >
        <p>{r.explanation}</p>
        {r.unknowns.length > 0 && <p>To confirm: {r.unknowns.join("; ")}</p>}
        <small>
          History reference: {detail.metadata.reference_date}. A passed date
          does not confirm outstanding work. Previous category work includes all
          observed calibrations in that category, not only the instruments in
          this batch.
        </small>
      </InfoHint>
    </div>
  );
}

export function CustomerSignals({ detail: d }: { detail: Detail }) {
  const reasons = d.action?.reasons || [];
  const groups = new Map<
    string,
    {
      label: string;
      status: string;
      ids: Set<string>;
      start: string;
      end: string;
      estimated: boolean;
    }
  >();
  for (const r of reasons.filter((r) => r.type === "upcoming")) {
    const label = equipmentLabel(d, r);
    const status = r.title.includes("past due")
      ? "Date passed — confirm status"
      : "Coming due";
    const key = `${label}:${status}`;
    const [start, end] = r.id.split(":").slice(-2);
    const group = groups.get(key) || {
      label,
      status,
      ids: new Set<string>(),
      start,
      end,
      estimated: false,
    };
    if (start < group.start) group.start = start;
    if (end > group.end) group.end = end;
    group.estimated ||= r.unknowns.some((u) => u.includes("inferred"));
    r.instrument_ids.forEach((id) => group.ids.add(id));
    groups.set(key, group);
  }
  return (
    <Card className="customer-signals">
      <div className="card-heading">
        <h2>Why contact this customer?</h2>
        <InfoHint label="contact reasons">
          These are reasons to review the account, not confirmed churn or
          guaranteed sales. Dates come from historical records; check current
          plans before contacting the customer.
        </InfoHint>
      </div>
      {reasons.some((r) => r.type === "inactivity") &&
        d.prediction?.inactivity.flagged && (
          <div className="sales-signal orange">
            <strong>Check in on reduced activity</strong>
            <ul>
              {d.prediction.inactivity.reasons.map((r) => (
                <li key={r}>
                  {r.includes("50%")
                    ? "Calibration work in the latest three months is at least half below the previous year’s quarterly average."
                    : r.includes("cadence")
                      ? "This customer has been quiet longer than their usual calibration cycle."
                      : r}
                </li>
              ))}
            </ul>
            <small>
              Ask whether timing, equipment or requirements have changed.
            </small>
          </div>
        )}
      {groups.size > 0 && (
        <>
          <p>
            Confirm the planned calibration batch and whether earlier dates have
            already been handled.
          </p>
          <div className="integrated-table">
            <table>
              <thead>
                <tr>
                  <th>Equipment</th>
                  <th>Instruments</th>
                  <th>Timing</th>
                  <th>Reason to discuss</th>
                </tr>
              </thead>
              <tbody>
                {[...groups.values()].slice(0, 5).map((g) => (
                  <tr key={g.label + g.status}>
                    <td>{g.label}</td>
                    <td>{g.ids.size.toLocaleString()}</td>
                    <td>
                      {[g.start, g.end]
                        .filter((v, i, a) => a.indexOf(v) === i)
                        .map((v) =>
                          /^\d{4}-\d{2}-\d{2}$/.test(v)
                            ? new Date(v + "T12:00:00Z").toLocaleDateString(
                                undefined,
                                { day: "numeric", month: "short" },
                              )
                            : "Confirm timing",
                        )
                        .join(" – ")}
                    </td>
                    <td>
                      {g.status}
                      {g.estimated && <small>Includes estimated dates</small>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {groups.size > 5 && (
            <small>
              {groups.size - 5} more equipment groups in the detailed evidence.
            </small>
          )}
        </>
      )}
      {reasons.some((r) => r.type === "discovery") && (
        <div className="sales-signal">
          <strong>Explore an additional service</strong>
          <p>
            Similar customers use other calibration categories. Ask whether
            these would be relevant to this account.
          </p>
        </div>
      )}
      {!reasons.length && !d.prediction?.inactivity.flagged && (
        <p>
          No current contact trigger. Review the history before deciding on
          outreach.
        </p>
      )}
    </Card>
  );
}
