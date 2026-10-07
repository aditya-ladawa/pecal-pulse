"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useSalesStore } from "./store";
import {
  getV2Bootstrap,
  getV2Customers,
  getV2Detail,
  getV2Followups,
  patchV2Workflow,
  request,
} from "./api";
import { openCustomer, dispatchEvent } from "@/core/events/router";
import { Chart, ArtifactChart } from "@/modules/artifacts/Chart";
import { Card } from "@/components/ui/Primitives";
import type { Bootstrap, Detail } from "@/types/sales-v2";
import type { EventEnvelope, PageSnapshot } from "@/types/sales";
const count = (value: number | null | undefined) =>
  value == null
    ? "Unavailable"
    : value.toLocaleString(undefined, { maximumFractionDigits: 1 });
export function integratedSnapshot(
  boot: Bootstrap,
  detail: Detail | null,
  page: "dashboard" | "customers" | "follow-ups",
): PageSnapshot {
  const metrics =
    page === "dashboard"
      ? [
          {
            label: "Customers to review",
            value: boot.kpis.customers.value,
            unit: "customers",
            scope: "All snapshot accounts",
            definition: "Accounts in the source snapshot.",
          },
          {
            label: "Recorded requirement records",
            value: boot.kpis.requirements_by_kind.recorded || 0,
            unit: "instruments",
            scope: "All snapshot instruments; all dates",
            definition:
              "Instruments with recorded requirement dates. Includes excluded/review-required cases; not a near-term forecast or order count.",
          },
          {
            label: "Inferred requirement records",
            value:
              (boot.kpis.requirements_by_kind.nominal_interval || 0) +
              (boot.kpis.requirements_by_kind.repeat_history || 0),
            unit: "instruments",
            scope: "All snapshot instruments; all dates",
            definition:
              "Nominal-interval and repeat-history requirement tiers; not confirmed upcoming work.",
          },
          {
            label: "Open follow-ups",
            value: boot.kpis.open_followups.value,
            unit: "tasks",
            scope: "Local workflow store",
            definition: "All open follow-ups; not only overdue tasks.",
          },
        ]
      : page === "customers" && detail
        ? [
            {
              label: "Recorded requirement records",
              value: detail.requirements.filter((r) => r.kind === "recorded")
                .length,
              unit: "instruments",
              scope: detail.profile.display_name,
              definition:
                "Recorded requirement evidence; examine window and eligibility before outreach.",
            },
            ...(detail.prediction?.calibration_volume.expected_total != null
              ? [
                  {
                    label: "Expected calibrations · next 3 months",
                    value: detail.prediction.calibration_volume.expected_total,
                    unit: "calibration events",
                    scope: `${detail.prediction.calibration_volume.window_start} through ${detail.prediction.calibration_volume.window_end}`,
                    definition:
                      "Validated model/baseline quarter-total outlook. No monthly customer prediction or uncertainty interval is supplied.",
                  },
                ]
              : []),
          ]
        : [];
  return {
    page,
    title:
      page === "dashboard"
        ? "Your next conversation"
        : page === "customers"
          ? detail?.profile.display_name || "Customer workspace"
          : "Follow-ups",
    metrics,
  };
}
export function IntegratedWorkspace() {
  const pathname = usePathname();
  const s = useSalesStore();
  const [offset, setOffset] = useState(0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<{
    supported_customers: number;
    selected_activity: string;
    selected_volume: string;
    activity_metrics: Record<
      string,
      { test: { roc_auc: number | null; brier: number } }
    >;
    volume_metrics: Record<
      string,
      { test: { wape: number | null; mae: number } }
    >;
  } | null>(null);
  const boot = s.v2!;
  const sid = boot.metadata.snapshot_id;
  useEffect(() => {
    let alive = true;
    request<{ model_report: NonNullable<typeof report> }>(
      `v2/model-report?snapshot_id=${sid}`,
    )
      .then((r) => {
        if (alive) setReport(r.model_report);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [sid]);
  useEffect(() => {
    setOffset(0);
  }, [
    s.filters.industry,
    s.filters.segment,
    s.filters.action,
    s.filters.query,
  ]);
  useEffect(() => {
    if (pathname !== "/customers") return;
    let alive = true;
    setPending(true);
    setError("");
    getV2Customers(sid, s.filters, offset)
      .then((list) => {
        if (alive) s.set({ v2List: list });
      })
      .catch((e) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) setPending(false);
      });
    return () => {
      alive = false;
    };
  }, [sid, pathname, s.filters, offset, s.set]);
  useEffect(() => {
    if (pathname !== "/customers" || !s.selectedId) return;
    let alive = true;
    s.set({ v2Detail: null });
    getV2Detail(sid, s.selectedId)
      .then((detail) => {
        if (alive) s.set({ v2Detail: detail });
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [sid, pathname, s.selectedId, s.set]);
  const refresh = async () => {
    const [detail, tasks, boot] = await Promise.all([
      getV2Detail(sid, s.selectedId),
      getV2Followups(sid),
      getV2Bootstrap(),
    ]);
    s.set({
      v2: boot,
      v2Detail: detail,
      data: { ...useSalesStore.getState().data, followups: tasks.items },
    });
  };
  const changeWorkflow = async (payload: unknown) => {
    setPending(true);
    setError("");
    try {
      await patchV2Workflow(sid, s.selectedId, payload);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  };
  if (pathname === "/follow-ups")
    return (
      <>
        <Heading
          title="Keep the next step moving."
          text="Agreed follow-ups, persisted locally and separate from the SQL source."
        />
        <Card>
          <h2>Follow-ups</h2>
          {s.data.followups.length === 0 ? (
            <p>No follow-ups yet. Open a customer and record the next step.</p>
          ) : (
            s.data.followups.map((task) => (
              <div className="integrated-task" key={task.id}>
                <div>
                  <button
                    className="text-button"
                    onClick={() => openCustomer(task.customer_id)}
                  >
                    {task.customer_name}
                  </button>
                  <p>{task.note}</p>
                  <small>
                    {task.owner} · {task.due_date} · {task.outcome}
                  </small>
                </div>
                <button
                  className="button"
                  onClick={async () => {
                    try {
                      const event = await request<EventEnvelope>(
                        `v2/followups/${task.id}`,
                        {
                          method: "PATCH",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({
                            status: task.status === "open" ? "done" : "open",
                          }),
                        },
                      );
                      dispatchEvent(event);
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  {task.status === "open" ? "Complete" : "Reopen"}
                </button>
              </div>
            ))
          )}
          {error && <p role="alert">{error}</p>}
        </Card>
      </>
    );
  if (pathname === "/customers")
    return (
      <>
        <Heading
          title="Customer workspace."
          text="Explore actual history, model support and evidence before taking action."
        />
        <div className="filters integrated-filters">
          <label>
            Industry
            <select
              aria-label="Industry"
              value={s.filters.industry}
              onChange={(e) =>
                s.set({ filters: { ...s.filters, industry: e.target.value } })
              }
            >
              <option value="all">All industries</option>
              {boot.filter_options.industries.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Segment
            <select
              aria-label="Customer segment"
              value={s.filters.segment}
              onChange={(e) =>
                s.set({ filters: { ...s.filters, segment: e.target.value } })
              }
            >
              <option value="all">All segments</option>
              {boot.filter_options.segments.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Purpose
            <select
              aria-label="Action purpose"
              value={s.filters.action}
              onChange={(e) =>
                s.set({
                  filters: {
                    ...s.filters,
                    action: e.target.value as typeof s.filters.action,
                  },
                })
              }
            >
              <option value="all">All actions</option>
              {boot.filter_options.actions.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
          <label>
            Search
            <input
              aria-label="Search customers"
              value={s.filters.query}
              onChange={(e) =>
                s.set({ filters: { ...s.filters, query: e.target.value } })
              }
              placeholder="Account name or ID"
            />
          </label>
        </div>
        {error && <p role="alert">{error}</p>}
        <div className="integrated-customer-grid">
          <Card>
            <h2>Your accounts · {count(s.v2List?.total)}</h2>
            {s.v2Detail &&
              s.v2List &&
              !s.v2List.items.some(
                (item) => item.profile.customer_id === s.selectedId,
              ) && (
                <p>
                  The selected account remains open independently of these
                  filters and this list page.
                </p>
              )}
            {pending && <p>Loading accounts…</p>}
            {s.v2List?.items.map((item) => (
              <button
                key={item.profile.customer_id}
                className={`integrated-account ${item.profile.customer_id === s.selectedId ? "selected" : ""}`}
                onClick={() => s.set({ selectedId: item.profile.customer_id })}
              >
                <strong>{item.profile.display_name}</strong>
                <span>{item.profile.industry_label || "Unknown industry"}</span>
                <small>
                  {item.primary_action?.primary_type || "No supported action"} ·{" "}
                  {item.primary_action?.readiness || "Review history"}
                </small>
              </button>
            ))}
            {!pending && s.v2List?.total === 0 && (
              <p>No accounts match these filters.</p>
            )}
            <div className="integrated-pagination">
              <button
                className="button"
                disabled={offset === 0 || pending}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                Previous
              </button>
              <span>
                {offset + 1}–{Math.min(offset + 20, s.v2List?.total || 0)}
              </span>
              <button
                className="button"
                disabled={pending || offset + 20 >= (s.v2List?.total || 0)}
                onClick={() => setOffset(offset + 20)}
              >
                Next
              </button>
            </div>
          </Card>
          <div>
            {s.v2Detail ? (
              <CustomerEvidence
                detail={s.v2Detail}
                pending={pending}
                onWorkflow={changeWorkflow}
                onSaved={refresh}
              />
            ) : (
              <Card>
                <p>Loading selected account…</p>
              </Card>
            )}
          </div>
        </div>
      </>
    );
  const sectors = boot.sectors;
  const corr = sectors?.correlation;
  return (
    <>
      <Heading
        title="Your next conversation."
        text="A ranked shortlist supported by historical evidence and explicit unknowns."
      />
      <div className="metrics">
        <Metric
          label="Customers to review"
          value={boot.kpis.customers.value}
          caption="All snapshot accounts"
        />
        <Metric
          label="Recorded requirement records"
          value={boot.kpis.requirements_by_kind.recorded || 0}
          caption="All recorded dates · eligibility varies"
        />
        <Metric
          label="Inferred requirement records"
          value={
            (boot.kpis.requirements_by_kind.nominal_interval || 0) +
            (boot.kpis.requirements_by_kind.repeat_history || 0)
          }
          caption="Nominal interval or repeated history"
        />
        <Metric
          label="Open follow-ups"
          value={boot.kpis.open_followups.value}
          caption="Local workflow store"
        />
      </div>
      <Card>
        <div className="card-heading">
          <div>
            <h2>Good reasons to reach out</h2>
            <p>
              Quantity and evidence priority · review required before outreach
            </p>
          </div>
          <button
            className="button"
            onClick={() => s.set({ requestedPage: "customers" })}
          >
            View all accounts →
          </button>
        </div>
        {boot.actions.length === 0 ? (
          <p>No supported actions in this snapshot.</p>
        ) : (
          <div className="integrated-table">
            <table>
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Why now</th>
                  <th>Priority</th>
                  <th>Readiness</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {boot.actions.slice(0, s.actionLimit).map((action) => (
                  <tr key={action.customer_id}>
                    <td>
                      {s.v2List?.items.find(
                        (c) => c.profile.customer_id === action.customer_id,
                      )?.profile.display_name ||
                        `Account ${action.customer_id.slice(0, 8)}`}
                    </td>
                    <td>
                      {action.reasons[0]?.title}
                      <small>{action.suggested_next_step}</small>
                    </td>
                    <td>{count(action.priority_score)}/100</td>
                    <td>{action.readiness.replaceAll("_", " ")}</td>
                    <td>
                      <button
                        className="button"
                        onClick={() => openCustomer(action.customer_id)}
                      >
                        Review
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <div className="integrated-charts">
        <Card>
          <h2>Sector activity</h2>
          {sectors?.history.length ? (
            <Chart
              label="Observed monthly calibration events by sector"
              height={310}
              option={{
                tooltip: { trigger: "axis" },
                legend: { type: "scroll" },
                grid: { left: 55, right: 20, bottom: 35, top: 50 },
                xAxis: {
                  type: "category",
                  data: sectors.history[0].monthly.map((p) => p.month),
                },
                yAxis: { type: "value", name: "Calibrations" },
                series: sectors.history.map((h) => ({
                  name: h.label,
                  type: "line",
                  showSymbol: false,
                  data: h.monthly.map((p) => p.calibration_events),
                })),
              }}
            />
          ) : (
            <p>
              Sector analytics unavailable:{" "}
              {boot.metadata.modules.sectors?.reason}
            </p>
          )}
        </Card>
        <Card>
          <h2>Sector movement correlation</h2>
          {corr ? (
            <>
              <Chart
                label="Pearson correlation of monthly log changes by industry"
                height={420}
                option={{
                  tooltip: {
                    formatter: (p) => {
                      const v = (p as { data: number[] }).data;
                      return `${corr.labels[v[0]]} / ${corr.labels[v[1]]}<br/>Correlation: ${v[2].toFixed(2)} · ${corr.pair_sample_counts[v[1]][v[0]]} aligned changes`;
                    },
                  },
                  grid: { left: 125, right: 30, top: 20, bottom: 120 },
                  xAxis: {
                    type: "category",
                    data: corr.labels,
                    axisLabel: { rotate: 55, fontSize: 9 },
                  },
                  yAxis: {
                    type: "category",
                    data: corr.labels,
                    axisLabel: { fontSize: 9 },
                  },
                  visualMap: {
                    min: -1,
                    max: 1,
                    show: false,
                    inRange: { color: ["#edb482", "#f5f5ec", "#72966a"] },
                  },
                  series: [
                    {
                      type: "heatmap",
                      data: corr.values.flatMap((row, y) =>
                        row.flatMap((v, x) => (v == null ? [] : [[x, y, v]])),
                      ),
                    },
                  ],
                }}
              />
              <small>
                {corr.method} · {corr.window_start}–{corr.window_end}. Blank
                pairs lack support. Correlation does not establish causation or
                predict sector direction.
              </small>
            </>
          ) : (
            <p>No supported correlation matrix.</p>
          )}
        </Card>
      </div>
      {sectors && (
        <Card>
          <h2>Next-month sector outlook</h2>
          <p>
            Separately evaluated one-step baselines; not derived from
            correlation.
          </p>
          <div className="integrated-table">
            <table>
              <thead>
                <tr>
                  <th>Industry</th>
                  <th>Month</th>
                  <th>Expected calibrations</th>
                  <th>Method</th>
                </tr>
              </thead>
              <tbody>
                {sectors.forecasts.map((f) => (
                  <tr key={f.industry_id}>
                    <td>
                      {
                        sectors.history.find(
                          (h) => h.industry_id === f.industry_id,
                        )?.label
                      }
                    </td>
                    <td>{f.forecast_month}</td>
                    <td>{count(f.expected)}</td>
                    <td>{f.method || "Insufficient history"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {report && (
        <Card>
          <h2>Model quality & coverage</h2>
          <p>
            {report.supported_customers.toLocaleString()} accounts with
            supported activity predictions of{" "}
            {boot.kpis.customers.value.toLocaleString()} source accounts.
            Targets use the three full months after the history reference date.
          </p>
          <p>
            Activity: {report.selected_activity} · holdout ROC AUC{" "}
            {report.activity_metrics[
              report.selected_activity
            ]?.test.roc_auc?.toFixed(3) || "Unavailable"}{" "}
            · Brier{" "}
            {report.activity_metrics[
              report.selected_activity
            ]?.test.brier?.toFixed(3) || "Unavailable"}
            .
          </p>
          <p>
            Volume: {report.selected_volume} · holdout WAPE{" "}
            {report.volume_metrics[report.selected_volume]?.test.wape == null
              ? "Unavailable"
              : (
                  report.volume_metrics[report.selected_volume].test.wape! * 100
                ).toFixed(1) + "%"}
            . Customer quantities are directional; they are not confirmed orders
            or staffing commitments.
          </p>
          <small>
            Evaluation uses repeated historical customer-origin observations. No
            confirmed churn labels, campaign uplift or financial value are
            measured. Current instrument master values are extracted now, not
            reconstructed as of the history reference date.
          </small>
        </Card>
      )}
      {s.artifacts.map((a) => (
        <Card key={a.id}>
          <h2>{a.title}</h2>
          <ArtifactChart artifact={a} />
        </Card>
      ))}
    </>
  );
}
function Heading({ title, text }: { title: string; text: string }) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">EVIDENCE INTO ACTION</div>
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
    </div>
  );
}
function Metric({
  label,
  value,
  caption,
}: {
  label: string;
  value: number | null | undefined;
  caption: string;
}) {
  return (
    <div className="metric mint">
      <div className="metric-top">{label}</div>
      <strong>{count(value)}</strong>
      <span>{caption}</span>
    </div>
  );
}
function CustomerEvidence({
  detail: d,
  pending,
  onWorkflow,
  onSaved,
}: {
  detail: Detail;
  pending: boolean;
  onWorkflow: (p: unknown) => Promise<void>;
  onSaved: () => Promise<void>;
}) {
  const s = useSalesStore();
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [showAllReasons, setShowAllReasons] = useState(false);
  useEffect(() => setShowAllReasons(false), [d.profile.customer_id]);
  const prediction = d.prediction;
  const volume = prediction?.calibration_volume;
  const exportBrief = () => {
    const lines = [
      d.profile.display_name,
      `History reference: ${d.metadata.reference_date}`,
      "Known facts",
      ...d.preparation.facts.map((f) => f.text),
      "Unknowns",
      ...d.preparation.unknowns,
      "Questions",
      ...d.preparation.questions,
      "Next step",
      d.preparation.suggested_next_step,
    ];
    const url = URL.createObjectURL(
      new Blob([lines.join("\n")], { type: "text/plain" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `preparation-${d.profile.customer_id.slice(0, 8)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <>
      <Card>
        <div className="card-heading">
          <div>
            <small style={{ overflowWrap: "anywhere" }}>
              {d.profile.customer_id}
            </small>
            <h2>{d.profile.display_name}</h2>
            <p>
              {d.profile.industry_label || "Unknown industry"} ·{" "}
              {d.profile.name_source === "identifier"
                ? "Identifier-based name"
                : "Verified name"}
            </p>
          </div>
          <button
            className="button"
            onClick={() => s.set({ assistantOpen: true })}
          >
            Ask Pulse
          </button>
        </div>
        <div
          className="customer-tabs"
          role="tablist"
          aria-label="Customer evidence sections"
        >
          {(["activity", "portfolio", "next-step"] as const).map((tab) => (
            <button
              role="tab"
              aria-selected={s.customerTab === tab}
              key={tab}
              onClick={() => s.set({ customerTab: tab })}
            >
              {tab === "activity"
                ? "Activity & forecast"
                : tab === "portfolio"
                  ? "Portfolio & opportunities"
                  : "Conversation & next step"}
            </button>
          ))}
        </div>
      </Card>
      {s.customerTab === "activity" ? (
        <>
          <div className="metrics integrated-detail-metrics">
            <Metric
              label="Any calibration · next 3 months"
              value={
                prediction?.activity.probability == null
                  ? null
                  : prediction.activity.probability * 100
              }
              caption={
                prediction?.activity.probability == null
                  ? prediction?.activity.support.reason || "Unsupported history"
                  : "Probability % · not churn or conversion"
              }
            />
            <Metric
              label="Expected calibrations · next 3 months"
              value={volume?.expected_total}
              caption={
                volume
                  ? `${volume.window_start}–${volume.window_end} · ${volume.method}`
                  : "No supported forecast"
              }
            />
          </div>
          <Card>
            <h2>Observed customer activity</h2>
            <Chart
              label={`${d.profile.display_name} observed calibration history`}
              option={{
                tooltip: { trigger: "axis" },
                grid: { left: 50, right: 20, bottom: 40, top: 20 },
                xAxis: {
                  type: "category",
                  data: d.history.map((h) => h.month),
                },
                yAxis: { type: "value" },
                series: [
                  {
                    name: "Observed calibrations",
                    type: "bar",
                    data: d.history.map((h) => h.calibration_events),
                  },
                ],
              }}
            />
            <p>
              {volume?.monthly
                ? "Monthly forecasts supplied."
                : "Forecast is a three-month total; monthly predictions and uncertainty intervals are unavailable."}
            </p>
            {prediction?.inactivity.flagged && (
              <p>
                <strong>Activity review:</strong>{" "}
                {prediction.inactivity.reasons.join(" ")}
              </p>
            )}
          </Card>
          <Card>
            <h2>Why this account appears</h2>
            <p>
              Due-window actions use 90 days before and after the history
              reference; older and later records remain in Portfolio evidence.
              Past-due records require a timing check.
            </p>
            {d.action && d.action.reasons.length > 5 && (
              <button
                className="button"
                onClick={() => setShowAllReasons(!showAllReasons)}
              >
                {showAllReasons
                  ? "Show top 5 reasons"
                  : `Show all ${d.action.reasons.length} reasons`}
              </button>
            )}
            {d.action ? (
              d.action.reasons
                .slice(0, showAllReasons ? undefined : 5)
                .map((r) => (
                  <div className="integrated-reason" key={r.id}>
                    <strong>{r.title}</strong>
                    <p>{r.explanation}</p>
                    <small>
                      Quantity: {count(r.quantity)} {r.quantity_unit} ·{" "}
                      {r.unknowns.join(" · ")}
                    </small>
                    <div className="integrated-pagination">
                      <button
                        className="button"
                        disabled={pending}
                        onClick={() =>
                          onWorkflow({
                            suppression: {
                              reason_id: r.id,
                              status: "resolved",
                              until: null,
                              note: "Not applicable; manually confirmed in prototype",
                              updated_at: new Date().toISOString(),
                            },
                          })
                        }
                      >
                        Mark not applicable
                      </button>
                      <button
                        className="button"
                        disabled={pending}
                        onClick={() => {
                          const until = new Date();
                          until.setDate(until.getDate() + 30);
                          void onWorkflow({
                            suppression: {
                              reason_id: r.id,
                              status: "snoozed",
                              until: until.toISOString().slice(0, 10),
                              note: "Manual 30-day snooze",
                              updated_at: new Date().toISOString(),
                            },
                          });
                        }}
                      >
                        Snooze 30 days
                      </button>
                    </div>
                  </div>
                ))
            ) : (
              <p>No active supported action. History remains available.</p>
            )}
          </Card>
        </>
      ) : s.customerTab === "portfolio" ? (
        <>
          <Card>
            <h2>Observed calibrated portfolio</h2>
            <div className="integrated-table">
              <table>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Distinct instruments</th>
                    <th>Calibration events</th>
                  </tr>
                </thead>
                <tbody>
                  {d.portfolio.map((p) => (
                    <tr key={p.group_id}>
                      <td>{p.group_label}</td>
                      <td>{count(p.distinct_instruments)}</td>
                      <td>{count(p.calibration_events)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              Calibration counts do not represent distinct owned instruments.
              This portfolio covers observed work with Perschmann.
            </p>
          </Card>
          <Card>
            <h2>Peer-supported discovery questions</h2>
            {d.peer_opportunities.length ? (
              d.peer_opportunities.map((p, i) => (
                <div className="integrated-reason" key={i}>
                  <strong>
                    {p.group_label} · {(p.prevalence * 100).toFixed(0)}% of{" "}
                    {p.peer_count} peers
                  </strong>
                  <p>{p.question}</p>
                </div>
              ))
            ) : (
              <p>No category meets the peer-support thresholds.</p>
            )}
          </Card>
          <Card>
            <h2>Requirement evidence</h2>
            <p>
              {d.requirements.length} instrument records ·{" "}
              {d.requirements.filter((r) => r.kind === "unknown").length} with
              unknown dates ·{" "}
              {
                d.requirements.filter((r) => r.eligibility === "excluded")
                  .length
              }{" "}
              excluded.
            </p>
            <div className="integrated-table">
              <table>
                <thead>
                  <tr>
                    <th>Evidence</th>
                    <th>Window</th>
                    <th>Eligibility</th>
                  </tr>
                </thead>
                <tbody>
                  {d.requirements.slice(0, 50).map((r) => (
                    <tr key={r.id}>
                      <td>{r.kind.replaceAll("_", " ")}</td>
                      <td>
                        {r.window_start || "Unknown"} –{" "}
                        {r.window_end || "Unknown"}
                      </td>
                      <td>{r.eligibility.replaceAll("_", " ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {d.requirements.length > 50 && (
              <small>
                Showing first 50 records; all counts use the full account.
              </small>
            )}
          </Card>
        </>
      ) : (
        <>
          <Card>
            <div className="card-heading">
              <h2>Conversation preparation</h2>
              <button className="button" onClick={exportBrief}>
                Export brief
              </button>
            </div>
            <h3>Known facts</h3>
            <ul>
              {d.preparation.facts.slice(0, 8).map((f, i) => (
                <li key={i}>{f.text}</li>
              ))}
            </ul>
            <h3>To confirm</h3>
            <ul>
              {d.preparation.unknowns.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
            <h3>Useful questions</h3>
            <ul>
              {d.preparation.questions.slice(0, 5).map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
            <p>
              Showing up to 8 facts and 5 questions; Export brief includes the
              complete evidence pack.
            </p>
            <p>{d.preparation.suggested_next_step}</p>
            <label>
              Quotation/order check
              <select
                value={d.workflow.checks.quotation_order}
                disabled={pending}
                onChange={(e) =>
                  onWorkflow({
                    checks: {
                      quotation_order: e.target.value,
                      checked_by: "Prototype user",
                    },
                  })
                }
              >
                <option value="unknown">Unknown</option>
                <option value="reported_none">
                  Manually checked: none reported
                </option>
                <option value="in_progress">In progress</option>
              </select>
            </label>
          </Card>
          <Card>
            <h2>Record the next step</h2>
            <form
              className="integrated-form"
              onSubmit={async (e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const values = new FormData(form);
                setSaving(true);
                setError("");
                try {
                  const event = await request<EventEnvelope>(
                    `v2/followups?snapshot_id=${d.metadata.snapshot_id}`,
                    {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        customer_id: d.profile.customer_id,
                        owner: values.get("owner"),
                        due_date: values.get("date"),
                        note: values.get("note"),
                        outcome: values.get("outcome"),
                        reason_ids: d.action?.reasons.map((r) => r.id) || [],
                      }),
                    },
                  );
                  dispatchEvent(event);
                  await onSaved();
                  form.reset();
                } catch (err) {
                  setError((err as Error).message);
                } finally {
                  setSaving(false);
                }
              }}
            >
              <label>
                Owner
                <input name="owner" required maxLength={100} />
              </label>
              <label>
                Follow-up date
                <input name="date" type="date" required />
              </label>
              <label>
                Outcome
                <select name="outcome">
                  {[
                    "Timing to confirm",
                    "Timing changed",
                    "Need confirmed",
                    "Not applicable",
                    "Equipment retired",
                  ].map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </select>
              </label>
              <label>
                Next step
                <textarea name="note" required maxLength={2000} />
              </label>
              <button className="button dark" disabled={saving}>
                {saving ? "Saving…" : "Save follow-up"}
              </button>
              {error && <p role="alert">{error}</p>}
            </form>
          </Card>
        </>
      )}
    </>
  );
}
