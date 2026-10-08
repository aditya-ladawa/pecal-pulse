"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useSalesStore } from "./store";
import { OpportunityDashboard } from "./OpportunityDashboard";
import {
  getV2Bootstrap,
  getV2Customers,
  getV2Detail,
  getV2Followups,
  patchV2Workflow,
  request,
} from "./api";
import { openCustomer, dispatchEvent } from "@/core/events/router";
import { axisNumber, axisPercent, Chart, ArtifactChart } from "@/modules/artifacts/Chart";
import { InstrumentTiming } from "./InstrumentTiming";
import { Card, InfoHint } from "@/components/ui/Primitives";
import type { Bootstrap, Detail, InsightsEvidence } from "@/types/sales-v2";
import type { ChartArtifact } from "@/types/sales";
import type { EventEnvelope, PageSnapshot } from "@/types/sales";
import {
  BatchReasonSummary,
  CustomerSignals,
  PeerQuestions,
  SalesPreparation,
  salesBriefLines,
} from "./CustomerSignals";
const count = (value: number | null | undefined) =>
  value == null
    ? "Unavailable"
    : value.toLocaleString(undefined, { maximumFractionDigits: 1 });
export function integratedSnapshot(
  boot: Bootstrap,
  detail: Detail | null,
  page: "dashboard" | "customers" | "follow-ups" | "insights",
): PageSnapshot {
  const opportunities = useSalesStore.getState().opportunities;
  if (page === "dashboard") {
    const metrics =
      opportunities?.metrics.map(({ caption, ...metric }) => ({
        ...metric,
        value: metric.value == null ? null : Number(metric.value.toFixed(1)),
      })) || [];
    if (opportunities?.scenario && metrics[1])
      metrics[1] = {
        ...metrics[1],
        label: "Estimated contribution · scenario",
        value: opportunities.scenario.estimated_contribution,
        unit: "EUR",
        definition:
          "Supported account-wide calibration forecast multiplied by supplied unit contribution; not net profit or incremental outreach benefit.",
      };
    return { page, title: "Opportunity dashboard", metrics };
  }
  const metrics =
    page === "customers" &&
    detail &&
    useSalesStore.getState().customerTab === "activity"
      ? [
          {
            label: "Chance of calibration activity",
            value:
              detail.prediction?.activity.probability == null
                ? null
                : Number(
                    (detail.prediction.activity.probability * 100).toFixed(1),
                  ),
            unit: "%",
            scope: detail.profile.display_name,
            definition:
              "Chance of at least one calibration in the next three complete months, not a sale or churn prediction.",
          },
          ...(detail.prediction?.calibration_volume.expected_total != null
            ? [
                {
                  label: "Estimated calibrations · next 3 months",
                  value: Number(
                    detail.prediction.calibration_volume.expected_total.toFixed(
                      1,
                    ),
                  ),
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
      page === "customers"
        ? detail?.profile.display_name || "Customer workspace"
        : page === "insights"
          ? "Insights"
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
    s.filters.retention,
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
  if (
    pathname === "/follow-ups" ||
    (pathname === "/customers" && s.customerView === "follow-ups")
  )
    return (
      <>
        <Heading
          title="Follow-ups"
          text="Agreed follow-ups, persisted locally and separate from the SQL source."
        />
        <Card>
          <CustomerViews />
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
      <div className="customers-workspace">
        <div className="customers-toolbar">
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
                {(
                  [
                    ["upcoming", "Calibration need"],
                    ["inactivity", "Reduced activity"],
                    ["discovery", "Service to explore"],
                  ] as const
                ).map(
                  ([value, label]) =>
                    boot.filter_options.actions.includes(value) && (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ),
                )}
              </select>
            </label>
            <label>
              Retention risk
              <select
                aria-label="Retention risk"
                value={s.filters.retention}
                onChange={(e) =>
                  s.set({
                    filters: {
                      ...s.filters,
                      retention: e.target.value as typeof s.filters.retention,
                    },
                  })
                }
              >
                <option value="all">All risks</option>
                <option value="higher">Higher risk</option>
                <option value="moderate">Moderate risk</option>
                <option value="lower">Lower risk</option>
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
          <CustomerViews />
        </div>
        {error && <p role="alert">{error}</p>}
        <div className="integrated-customer-grid">
          <Card className="accounts-pane">
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
            <div className="accounts-scroll">
              {s.v2List?.items.map((item) => (
                <button
                  key={item.profile.customer_id}
                  className={`integrated-account ${item.profile.customer_id === s.selectedId ? "selected" : ""}`}
                  onClick={() =>
                    s.set({ selectedId: item.profile.customer_id })
                  }
                >
                  <strong>{item.profile.display_name}</strong>
                  <span>
                    {item.profile.industry_label || "Unknown industry"}
                  </span>
                  <small>
                    {item.primary_action?.primary_type === "upcoming"
                      ? "Calibration need"
                      : item.primary_action?.primary_type === "inactivity"
                        ? "Check reduced activity"
                        : item.primary_action?.primary_type === "discovery"
                          ? "Explore a service"
                          : "Review history"}
                  </small>
                </button>
              ))}
            </div>
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
          <div className="customer-detail-pane">
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
      </div>
    );
  if (pathname !== "/insights") return <OpportunityDashboard />;
  return <InsightsView boot={boot} report={report} artifacts={s.artifacts} />;
}
function InsightsView({
  boot,
  report,
  artifacts,
}: {
  boot: Bootstrap;
  report: {
    supported_customers: number;
    selected_activity: string;
    selected_volume: string;
    activity_metrics: Record<string, { test: { roc_auc: number | null; brier: number } }>;
    volume_metrics: Record<string, { test: { wape: number | null; mae: number } }>;
  } | null;
  artifacts: ChartArtifact[];
}) {
  const [evidence, setEvidence] = useState<InsightsEvidence | null>(null);
  const [evidenceMissing, setEvidenceMissing] = useState(false);
  useEffect(() => {
    let alive = true;
    request<InsightsEvidence>(
      `v2/insights-evidence?snapshot_id=${boot.metadata.snapshot_id}`,
    )
      .then((r) => {
        if (alive) {
          setEvidence(r);
          setEvidenceMissing(!r.retention && !r.volume && !r.summary);
        }
      })
      .catch(() => {
        if (alive) setEvidenceMissing(true);
      });
    return () => {
      alive = false;
    };
  }, [boot.metadata.snapshot_id]);
  const sectors = boot.sectors;
  const summary = evidence?.summary ?? null;
  const retention = evidence?.retention ?? null;
  const volume = evidence?.volume ?? null;
  const industryRows = Object.entries(summary?.industry_expected ?? {})
    .map(([id, v]) => ({ id, label: v.label || id, expected: v.expected || 0, accounts: v.accounts || 0 }))
    .sort((a, b) => b.expected - a.expected)
    .slice(0, 12);
  const riskRows = Object.entries(summary?.retention_by_industry ?? {})
    .map(([id, v]) => ({
      id,
      label: v.label || id,
      higher: v.higher || 0,
      moderate: v.moderate || 0,
      lower: v.lower || 0,
    }))
    .sort((a, b) => b.higher + b.moderate - (a.higher + a.moderate))
    .slice(0, 10);
  const challengerRows = Object.entries(volume?.challengers ?? {}).map(([method, stages]) => ({
    method,
    validationMae: stages.validation?.mae,
    testMae: stages.test?.mae,
    testWape: stages.test?.wape,
  }));
  const tiers = retention?.tier_distribution_at_reference ?? {};
  const sectorTotals =
    sectors?.history.map((h) => ({
      label: h.label,
      total: h.monthly.reduce((sum, p) => sum + p.calibration_events, 0),
    })) ?? [];
  const sectorSum = sectorTotals.reduce((sum, r) => sum + r.total, 0);
  const pieRows = sectorTotals
    .filter((r) => r.total > 0)
    .map((r) => ({ ...r, share: sectorSum ? r.total / sectorSum : 0 }))
    .sort((a, b) => b.total - a.total);
  const pieWindow = sectors?.history[0]?.monthly.length
    ? `${sectors.history[0].monthly[0].month}–${
        sectors.history[0].monthly[sectors.history[0].monthly.length - 1].month
      }`
    : "";
  return (
    <>
      <Heading title="Insights" text="Where the work is coming from, where risk sits, and how far to trust the numbers" />
      {evidenceMissing && (
        <Card>
          <p>
            Offline evidence is not published for this snapshot, so this page
            shows sector history and model quality only. Rebuild the
            retention/volume/insights sidecars for full detail.
          </p>
        </Card>
      )}
      <Card>
        <div className="card-heading">
          <h2>Expected calibrations by industry</h2>
          <InfoHint label="expected calibrations by industry">
            Sums of supported 3-month account forecasts per industry.
            Directional totals for focus planning, not confirmed orders.
          </InfoHint>
        </div>
        {industryRows.length ? (
          <Chart
            label="Supported expected calibrations for the next three months by industry"
            height={330}
            option={{
              tooltip: { trigger: "axis" },
              grid: { left: 60, right: 20, bottom: 80, top: 30 },
              xAxis: {
                type: "category",
                name: "Calibrations",
                nameLocation: "middle",
                nameGap: 56,
                data: industryRows.map((r) => r.label),
                axisLabel: { rotate: 32, fontSize: 9, interval: 0 },
              },
              yAxis: { type: "value", name: "Expected calibrations", axisLabel: { formatter: axisNumber } },
              series: [
                {
                  name: "Expected calibrations",
                  type: "bar",
                  data: industryRows.map((r) => Math.round(r.expected)),
                },
              ],
            }}
          />
        ) : (
          <p>Industry forecast totals unavailable for this snapshot.</p>
        )}
      </Card>
      <Card>
        <div className="card-heading">
          <h2>Retention risk by industry</h2>
          <InfoHint label="retention risk by industry">
            Measured tiers from past silence episodes: of similarly silent
            accounts, how many returned within three months. Higher risk
            means fewer returned — a check-in signal, never a churn label.
          </InfoHint>
        </div>
        {riskRows.length ? (
          <Chart
            label="Accounts by measured retention-risk tier per industry"
            height={330}
            option={{
              tooltip: { trigger: "axis" },
              legend: { type: "scroll" },
              grid: { left: 60, right: 20, bottom: 80, top: 50 },
              xAxis: {
                type: "category",
                name: "Accounts",
                nameLocation: "middle",
                nameGap: 56,
                data: riskRows.map((r) => r.label),
                axisLabel: { rotate: 32, fontSize: 9, interval: 0 },
              },
              yAxis: { type: "value", name: "Accounts", axisLabel: { formatter: axisNumber } },
              series: [
                { name: "Higher risk", type: "bar", stack: "risk", data: riskRows.map((r) => r.higher) },
                { name: "Moderate risk", type: "bar", stack: "risk", data: riskRows.map((r) => r.moderate) },
                { name: "Lower risk", type: "bar", stack: "risk", data: riskRows.map((r) => r.lower) },
              ],
            }}
          />
        ) : (
          <p>Retention tiers unavailable for this snapshot.</p>
        )}
      </Card>
      <div className="integrated-charts">
        <Card>
          <div className="card-heading">
            <h2>Do silent customers come back?</h2>
            <InfoHint label="measured return curve">
              Of accounts that went silent after repeated activity, the share
              that returned within the next three months, by elapsed silence.
              Regular histories return more often; long silences return less.
              Based on {(retention?.episodes || 0).toLocaleString()} fully
              observed past episodes — still-silent episodes with unknown
              outcomes are excluded, never counted as lost.
            </InfoHint>
          </div>
          {retention ? (
            <Chart
              label="Share of silent accounts returning within three months, by elapsed silence"
              height={300}
              option={{
                tooltip: { trigger: "axis" },
                legend: { type: "scroll" },
                grid: { left: 55, right: 20, bottom: 35, top: 50 },
                xAxis: {
                  type: "category",
                  name: "Silent months",
                  data: (retention.forward_curve.regular || []).map((p) => String(p.silent_months)),
                },
                yAxis: {
                  type: "value",
                  name: "Returned",
                  min: 0,
                  max: 1,
                  axisLabel: { formatter: (v: number) => `${axisPercent(v)}` },
                },
                series: (["regular", "irregular"] as const)
                  .filter((k) => retention.forward_curve[k]?.length)
                  .map((k) => ({
                    name: k === "regular" ? "Regular history" : "Irregular history",
                    type: "line",
                    showSymbol: true,
                    data: retention.forward_curve[k].map((p) => p.return_rate),
                  })),
              }}
            />
          ) : (
            <p>Return-curve evidence unavailable for this snapshot.</p>
          )}
        </Card>
        <Card>
          <div className="card-heading">
            <h2>Volume methods put to the test</h2>
            <InfoHint label="volume method comparison">
              Croston, TSB and industry-pooled estimators were scored on the
              pipeline's own chronological validation windows with the same
              MAE selection rule. The simple 12-month average still wins, so
              it stays — this table is the receipt.
            </InfoHint>
          </div>
          {challengerRows.length ? (
            <div className="integrated-table">
              <table>
                <thead>
                  <tr>
                    <th>Method</th>
                    <th>Validation MAE</th>
                    <th>Test MAE</th>
                    <th>Test WAPE</th>
                  </tr>
                </thead>
                <tbody>
                  <tr key={volume!.served_method}>
                    <td>{volume!.served_method.replaceAll("_", " ")} (served)</td>
                    <td>
                      {volume!.served_test.mae == null ? "—" : volume!.served_test.mae.toFixed(2)}
                    </td>
                    <td>
                      {volume!.served_test.mae == null ? "—" : volume!.served_test.mae.toFixed(2)}
                    </td>
                    <td>
                      {volume!.served_test.wape == null ? "—" : `${(volume!.served_test.wape * 100).toFixed(1)}%`}
                    </td>
                  </tr>
                  {challengerRows.map((r) => (
                    <tr key={r.method}>
                      <td>{r.method.replaceAll("_", " ")}</td>
                      <td>{r.validationMae == null ? "—" : r.validationMae.toFixed(2)}</td>
                      <td>{r.testMae == null ? "—" : r.testMae.toFixed(2)}</td>
                      <td>{r.testWape == null ? "—" : `${(r.testWape * 100).toFixed(1)}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <small>
                Lower MAE is better. Selection used validation only; test
                columns are descriptive. Units are calibration events per
                3-month window.
              </small>
            </div>
          ) : (
            <p>Method comparison unavailable for this snapshot.</p>
          )}
        </Card>
      </div>
      <div className="integrated-charts">
        <Card>
          <div className="card-heading">
            <h2>Where the calibration work comes from</h2>
            <InfoHint label="share of calibrations by industry">
              Share of observed calibration events per industry over the
              sector history window. Descriptive history, not a forecast and
              not revenue.
            </InfoHint>
          </div>
          {sectors?.history.length ? (
            <Chart
              label="Share of observed calibrations by industry over the sector window"
              height={330}
              option={{
                tooltip: {
                  trigger: "item",
                  formatter: (p) => {
                    const row = pieRows[(p as { dataIndex: number }).dataIndex];
                    return row
                      ? `${row.label}<br/>${row.total.toLocaleString()} calibrations · ${axisPercent(row.share)} of total`
                      : "";
                  },
                },
                legend: { type: "scroll", bottom: 0, textStyle: { fontSize: 10 } },
                series: [
                  {
                    name: "Calibration share",
                    type: "pie",
                    radius: ["42%", "68%"],
                    center: ["50%", "45%"],
                    avoidLabelOverlap: true,
                    label: {
                      show: true,
                      formatter: (p) => axisPercent((Number(p.percent) || 0) / 100),
                    },
                    labelLine: { length: 8, length2: 8 },
                    data: pieRows.map((r) => ({ name: r.label, value: r.total })),
                  },
                ],
              }}
            />
          ) : (
            <p>
              Sector analytics unavailable:{" "}
              {boot.metadata.modules.sectors?.reason}
            </p>
          )}
          <small>
            {pieWindow} · {sectors?.history.length} industries · observed
            calibration events, not orders or revenue.
          </small>
        </Card>
        {sectors && (
          <Card>
            <h2>Next-month sector outlook</h2>
            <p>
              Separately evaluated one-step baselines for capacity planning,
              not account prioritization.
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
      </div>
      {tiers && Object.keys(tiers).length > 0 && (
        <Card>
          <h2>Retention tiers right now</h2>
          <p>
            {(tiers.lower || 0).toLocaleString()} lower risk ·{" "}
            {(tiers.moderate || 0).toLocaleString()} moderate risk ·{" "}
            {(tiers.higher || 0).toLocaleString()} higher risk ·{" "}
            {(tiers.unavailable || 0).toLocaleString()} without enough history
            for a tier. Filter these accounts on the Customers page under
            Retention risk.
          </p>
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
      {artifacts.map((a) => (
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
        <h1>{title}</h1>
      </div>
    </div>
  );
}
function Metric({
  label,
  value,
  caption,
  suffix = "",
}: {
  label: string;
  value: number | null | undefined;
  caption: string;
  suffix?: string;
}) {
  return (
    <div className="metric mint">
      <div className="metric-top">{label}</div>
      <strong>
        {count(value)}
        {value == null ? "" : suffix}
      </strong>
      <InfoHint label={label}>{caption}</InfoHint>
    </div>
  );
}
export function CustomerEvidence({
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
  const activityView = s.customerActivityView;
  const [showAllReasons, setShowAllReasons] = useState(false);
  const [portfolioPage, setPortfolioPage] = useState(0);
  useEffect(() => setPortfolioPage(0), [d.profile.customer_id]);
  const visiblePortfolioPage = Math.min(
    portfolioPage,
    Math.max(0, Math.ceil(d.portfolio.length / 5) - 1),
  );
  useEffect(() => setShowAllReasons(false), [d.profile.customer_id]);
  const prediction = d.prediction;
  const volume = prediction?.calibration_volume;
  const batchReasons =
    d.action?.reasons.filter((r) => r.type === "upcoming") || [];
  const monthName = (value: string) =>
    new Date(value.slice(0, 7) + "-01T12:00:00Z").toLocaleDateString(
      undefined,
      { month: "short", year: "numeric" },
    );
  const period = volume
    ? `${monthName(volume.window_start)} – ${monthName(volume.window_end)}`
    : "Forecast unavailable";
  const futureMonths = volume
    ? Array.from({ length: 3 }, (_, i) => {
        const date = new Date(
          volume.window_start.slice(0, 7) + "-01T12:00:00Z",
        );
        date.setUTCMonth(date.getUTCMonth() + i);
        return date.toISOString().slice(0, 7);
      })
    : [];
  const activityHistory = d.history.slice(
    activityView === "monthly" ? -24 : -3,
  );
  const forecastQuality = d.forecast_quality;
  const forecastSupported =
    volume?.support.status === "supported" && volume.expected_total != null;
  const exportBrief = () => {
    const lines = salesBriefLines(d);
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
      <Card className="customer-detail-header">
        <div className="customer-header-layout">
          <div className="customer-header-main">
            <div className="customer-account-identity">
              <h2>{d.profile.display_name}</h2>
              <p>{d.profile.industry_label || "Sector not supplied"}</p>
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
                    ? "Overview"
                    : tab === "portfolio"
                      ? "Equipment"
                      : "Next step"}
                </button>
              ))}
            </div>
          </div>
          {s.customerTab === "activity" && (
            <div className="customer-forecast-summary">
              <span className="forecast-meta">
                Outlook: {period} · History through {d.metadata.reference_date}
              </span>
              <div className="forecast-boxes">
                <div className="forecast-box">
                  <span>
                    Chance of calibration activity{" "}
                    <InfoHint label="chance of calibration activity">
                      {prediction?.activity.probability == null
                        ? prediction?.activity.support.reason ||
                          "There is not enough history to estimate calibration activity."
                        : "Chance of at least one calibration in the three-month outlook. This is not a probability of an order, churn or sales conversion."}
                    </InfoHint>
                  </span>
                  <b>
                    {prediction?.activity.probability == null
                      ? "Unavailable"
                      : `${(prediction.activity.probability * 100).toFixed(1)}%`}
                  </b>
                </div>
                <div className="forecast-box">
                  <span>
                    Estimated next 3 months{" "}
                    <InfoHint label="estimated calibrations next three months">
                      {forecastSupported
                        ? `Rough quarter-total estimate from this account's history through ${d.metadata.reference_date}. Monthly predictions and uncertainty intervals are not supplied.`
                        : volume?.support.reason ||
                          "Insufficient history for a supported forecast."}
                    </InfoHint>
                  </span>
                  <b>
                    {forecastSupported
                      ? `≈ ${Math.round(volume!.expected_total!)} calibrations`
                      : "Unavailable"}
                  </b>
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>
      {s.customerTab === "activity" ? (
        <>
          <Card className="customer-activity-card">
            <div className="card-heading">
              <h2>Customer activity</h2>
              <select
                aria-label="Customer activity view"
                value={activityView}
                onChange={(e) =>
                  s.set({
                    customerActivityView: e.target.value as
                      | "monthly"
                      | "quarter",
                  })
                }
              >
                <option value="monthly">24 months of history</option>
                <option value="quarter">3 months of history</option>
              </select>
              <InfoHint label="customer activity forecast">
                Historical bars count completed calibrations, not orders. The
                shaded area marks the three-month forecast window, not a
                confidence interval.
                {forecastSupported ? (
                  <>
                    <p>
                      Data used:{" "}
                      {forecastQuality?.input_months != null
                        ? `the customer's ${forecastQuality.input_months} months of calibration history`
                        : "the customer's historical calibration features"}{" "}
                      through {d.metadata.reference_date}.
                    </p>
                    <p>
                      {forecastQuality?.wape != null
                        ? `Historical forecast error: ${(forecastQuality.wape * 100).toFixed(0)}% WAPE across ${forecastQuality.test_windows?.toLocaleString() ?? "supported"} test windows${forecastQuality.test_customers != null ? ` from ${forecastQuality.test_customers.toLocaleString()} customers` : ""}. Total absolute error divided by total actual volume; not this customer's accuracy.`
                        : "Historical forecast error is unavailable."}
                    </p>
                    {forecastQuality?.segment_wape != null && (
                      <p>
                        {`Accounts like this (${forecastQuality.segment_label ?? "same behavior group"}): about ${(forecastQuality.segment_wape * 100).toFixed(0)}% aggregate error on ${forecastQuality.segment_windows?.toLocaleString() ?? "supported"} past windows. Estimates for steady high-volume accounts are far more reliable than for occasional ones.`}
                      </p>
                    )}
                    <p>
                      This is a rough volume estimate. Monthly predictions have
                      not been validated.
                    </p>
                  </>
                ) : (
                  <p>
                    {volume?.support.reason ||
                      "Insufficient history for a supported forecast."}
                  </p>
                )}
              </InfoHint>
            </div>
            <Chart
              height={340}
              label={`${d.profile.display_name} historical calibrations and shaded three-month forecast window`}
              option={{
                tooltip: { trigger: "axis" },
                grid: { left: 48, right: 16, bottom: 40, top: 56 },
                xAxis: {
                  type: "category",
                  data: [
                    ...activityHistory.map((h) => h.month),
                    ...futureMonths,
                  ],
                },
                yAxis: { type: "value", min: 0, minInterval: 1, axisLabel: { formatter: axisNumber } },
                series: [
                  {
                    name: "Completed calibrations",
                    type: "bar",
                    barMaxWidth: 30,
                    data: [
                      ...activityHistory.map((h) => h.calibration_events),
                      ...futureMonths.map(() => null),
                    ],
                    markArea: futureMonths.length
                      ? {
                          silent: true,
                          itemStyle: {
                            color: "rgba(160, 146, 193, 0.32)",
                            borderColor: "rgba(112, 91, 151, 0.55)",
                            borderWidth: 1.5,
                          },
                          label: {
                            show: true,
                            position: "insideTop",
                            distance: 6,
                            color: "#3a2a52",
                            fontSize: 16,
                            fontWeight: 800,
                            lineHeight: 20,
                            backgroundColor: "rgba(255, 255, 255, 0.94)",
                            padding: [8, 12],
                            borderRadius: 10,
                            borderColor: "rgba(112, 91, 151, 0.35)",
                            borderWidth: 1,
                            formatter: `3-month total\n${forecastSupported ? `≈ ${Math.round(volume!.expected_total!)} calibrations` : "Insufficient history"}`,
                          },
                          data: [
                            [
                              { xAxis: futureMonths[0] },
                              { xAxis: futureMonths[2] },
                            ],
                          ],
                        }
                      : undefined,
                  },
                ],
              }}
            />
          </Card>
          <CustomerSignals detail={d} />
          {batchReasons.length > 0 && (
            <Card>
              <details>
                <summary>Review batches and update their status</summary>
                <p className="batch-guidance">
                  Confirm timing and whether the work is already handled. Update
                  only the relevant batch.
                </p>
                {batchReasons.length > 5 && (
                  <button
                    className="button"
                    onClick={() => setShowAllReasons(!showAllReasons)}
                  >
                    {showAllReasons
                      ? "Show top 5 batches"
                      : `Show all ${batchReasons.length} batches`}
                  </button>
                )}
                {d.action ? (
                  batchReasons
                    .slice(0, showAllReasons ? undefined : 5)
                    .map((r) => (
                      <div className="batch-review" key={r.id}>
                        <BatchReasonSummary detail={d} reason={r} />
                        <div className="batch-actions">
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
              </details>
            </Card>
          )}
        </>
      ) : s.customerTab === "portfolio" ? (
        <div className="equipment-layout">
          <Card>
            <div className="card-heading">
              <h2>Calibration work with us</h2>
              <InfoHint label="calibration work history">
                Observed calibration events, not total owned equipment. This
                history only covers work recorded with Perschmann.
              </InfoHint>
            </div>
            <div className="integrated-table">
              <table>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Completed calibrations</th>
                  </tr>
                </thead>
                <tbody>
                  {d.portfolio
                    .slice(
                      visiblePortfolioPage * 5,
                      visiblePortfolioPage * 5 + 5,
                    )
                    .map((p) => (
                      <tr key={p.group_id}>
                        <td>{p.group_label}</td>
                        <td>{count(p.calibration_events)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            {d.portfolio.length > 5 && (
              <div className="integrated-pagination">
                <button
                  className="button"
                  disabled={visiblePortfolioPage === 0}
                  onClick={() => setPortfolioPage(visiblePortfolioPage - 1)}
                >
                  Previous categories
                </button>
                <small>
                  {visiblePortfolioPage + 1} /{" "}
                  {Math.ceil(d.portfolio.length / 5)}
                </small>
                <button
                  className="button"
                  disabled={
                    (visiblePortfolioPage + 1) * 5 >= d.portfolio.length
                  }
                  onClick={() => setPortfolioPage(visiblePortfolioPage + 1)}
                >
                  Next categories
                </button>
              </div>
            )}
          </Card>
          <Card>
            <h2>Services to ask about</h2>
            <PeerQuestions detail={d} />
          </Card>
          <InstrumentTiming detail={d} />
        </div>
      ) : (
        <>
          <Card>
            <div className="card-heading">
              <h2>Conversation preparation</h2>
              <button className="button" onClick={exportBrief}>
                Export brief
              </button>
            </div>
            <SalesPreparation detail={d} />
            <form
              className="integrated-form"
              key={d.profile.customer_id + (d.workflow.account_owner || "")}
              onSubmit={async (e) => {
                e.preventDefault();
                const owner = String(
                  new FormData(e.currentTarget).get("account_owner") || "",
                ).trim();
                await onWorkflow({ account_owner: owner || null });
              }}
            >
              <label>
                Responsible teammate
                <input
                  name="account_owner"
                  maxLength={100}
                  defaultValue={d.workflow.account_owner || ""}
                  placeholder="Assign a teammate"
                />
              </label>
              <button className="button" disabled={pending}>
                Save owner
              </button>
            </form>
            <label>
              Is a quote or order already being handled?
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
                <option value="unknown">Not checked yet</option>
                <option value="reported_none">
                  Checked — no current quote or order reported
                </option>
                <option value="in_progress">Yes — already being handled</option>
              </select>
            </label>
            <small>
              Check with your team before contacting the customer. Historical
              records do not show live quotations or orders.
            </small>
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
                <input
                  name="owner"
                  required
                  maxLength={100}
                  defaultValue={d.workflow.account_owner || ""}
                />
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

function CustomerViews() {
  const s = useSalesStore();
  return (
    <div className="customer-tabs" aria-label="Customer workspace view">
      <button
        aria-pressed={s.customerView === "accounts"}
        onClick={() =>
          s.set({ customerView: "accounts", requestedPage: "customers" })
        }
      >
        Accounts
      </button>
      <button
        aria-pressed={s.customerView === "follow-ups"}
        onClick={() =>
          s.set({ customerView: "follow-ups", requestedPage: "customers" })
        }
      >
        Follow-ups
      </button>
    </div>
  );
}
