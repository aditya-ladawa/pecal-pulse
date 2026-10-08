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
            {d.retention && (
              <p>
                Measured retention risk: <strong>{d.retention.tier}</strong>{" "}
                — {(d.retention.return_probability * 100).toFixed(0)}% of
                similarly silent accounts returned within{" "}
                {d.retention.forward_window_months} months (
                {d.retention.basis_episodes.toLocaleString()} past episodes).
                <InfoHint label="measured retention risk">
                  {`Based on past silence episodes after repeated activity, not a churn prediction. Accounts with ${d.retention.regular_history ? "regular" : "irregular"} history silent ${d.retention.silence_months} months returned at this rate. Repeated episodes for an account are not independent.`}
                </InfoHint>
              </p>
            )}
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

export function PeerQuestions({
  detail: d,
  activeOnly = false,
}: {
  detail: Detail;
  activeOnly?: boolean;
}) {
  const peers = d.peer_opportunities.filter(
    (p) =>
      !activeOnly ||
      d.action?.reasons.some(
        (r) => r.type === "discovery" && r.title.includes(p.group_label),
      ),
  );
  return (
    <>
      {peers.length ? (
        peers.slice(0, 3).map((p) => (
          <div className="sales-signal" key={p.group_label}>
            <div className="card-heading">
              <strong>{p.group_label}</strong>
              <InfoHint label={`industry comparison for ${p.group_label}`}>
                {Math.round(p.prevalence * 100)}% of{" "}
                {p.peer_count.toLocaleString()} observed customers in the same
                industry used this calibration category. This does not establish
                that this customer owns the equipment or needs the service.
              </InfoHint>
            </div>
            <p>
              “Do you use {p.group_label} equipment, and how do you currently
              arrange calibration?”
            </p>
            <small>
              Used by {Math.round(p.prevalence * 100)}% of similar-industry
              customers in our history.
            </small>
          </div>
        ))
      ) : (
        <p>No supported additional-service suggestion for this account.</p>
      )}
    </>
  );
}

export function salesBriefLines(d: Detail): string[] {
  const batches = d.action?.reasons.filter((r) => r.type === "upcoming") || [];
  const last = [...d.history].reverse().find((h) => h.calibration_events > 0);
  const quiet = d.action?.reasons.some((r) => r.type === "inactivity");
  const peers = d.peer_opportunities.filter((p) =>
    d.action?.reasons.some(
      (r) => r.type === "discovery" && r.title.includes(p.group_label),
    ),
  );
  return [
    d.profile.display_name,
    `History through ${d.metadata.reference_date}`,
    ...batches
      .slice(0, 5)
      .map(
        (r) =>
          `Confirm ${r.quantity ?? r.instrument_ids.length} instruments in ${equipmentLabel(d, r)}. Check timing and whether the batch has already been handled.`,
      ),
    ...(quiet
      ? [
          `Longer gap than this customer's usual pattern.${last ? ` Last observed calibration month: ${last.month}.` : ""}`,
          "Ask: Have calibration timing or equipment needs changed?",
        ]
      : []),
    ...peers
      .slice(0, 3)
      .map(
        (p) =>
          `Ask: Do you use ${p.group_label} equipment, and how do you currently arrange calibration?`,
      ),
    "Before contact: check current quotations/orders, recent conversations and the right contact person.",
    "Agree on the next step, owner and follow-up date.",
  ];
}

export function SalesPreparation({ detail: d }: { detail: Detail }) {
  const batches = d.action?.reasons.filter((r) => r.type === "upcoming") || [];
  const quiet = d.action?.reasons.some((r) => r.type === "inactivity");
  const discovery = d.action?.reasons.some((r) => r.type === "discovery");
  const last = [...d.history].reverse().find((h) => h.calibration_events > 0);
  return (
    <>
      {batches.length > 0 && (
        <div className="sales-signal">
          <strong>Confirm the calibration need</strong>
          <ul>
            {batches.slice(0, 3).map((r) => (
              <li key={r.id}>
                {r.quantity ?? r.instrument_ids.length} instruments ·{" "}
                {equipmentLabel(d, r)}
                {r.id
                  .split(":")
                  .slice(-2)
                  .filter(
                    (v, i, a) =>
                      /^\d{4}-\d{2}-\d{2}$/.test(v) && a.indexOf(v) === i,
                  )
                  .map(
                    (v, i) =>
                      `${i === 0 ? " · " : " – "}${new Date(v + "T12:00:00Z").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}`,
                  )
                  .join("")}
              </li>
            ))}
          </ul>
          <p>
            “Are these instruments still due for calibration? What timing and
            batch size would suit you?”
          </p>
        </div>
      )}
      {quiet && (
        <div className="sales-signal orange">
          <strong>Check in after a longer gap</strong>
          <p>
            This customer has been quieter than their usual pattern.
            {last &&
              ` Last recorded calibration activity: ${new Date(last.month + "-01T12:00:00Z").toLocaleDateString(undefined, { month: "short", year: "numeric" })}.`}
          </p>
          <p>
            “Have your calibration timing or equipment needs changed? Is there
            anything we can help plan?”
          </p>
          <InfoHint label="longer activity gap">
            A historical activity signal, not confirmed customer loss. Timing
            changes, seasonality and equipment changes can explain the gap.
          </InfoHint>
        </div>
      )}
      {discovery && (
        <>
          <h3>Ask about another service</h3>
          <PeerQuestions detail={d} activeOnly />
        </>
      )}
      {!batches.length && !quiet && !discovery && (
        <p>
          No active contact reason. Review the customer history before deciding
          on outreach.
        </p>
      )}
      <details>
        <summary>Before you contact them</summary>
        <ul>
          <li>
            {d.workflow.checks.quotation_order === "in_progress"
              ? "A quote or order is already being handled—coordinate with its owner."
              : d.workflow.checks.quotation_order === "reported_none"
                ? "The team reported no current quote or order."
                : "Check whether a quote or order is already being handled."}
          </li>
          <li>
            {d.workflow.checks.recent_contact === "unknown"
              ? "Check whether a colleague has recently spoken to this customer."
              : "Review the recorded contact check before outreach."}
          </li>
          <li>Confirm the right contact person and agree on a next step.</li>
        </ul>
      </details>
    </>
  );
}
