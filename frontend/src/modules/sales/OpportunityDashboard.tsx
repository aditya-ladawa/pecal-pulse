"use client";
import { useEffect, useState } from "react";
import type { EChartsOption } from "echarts";
import { ArrowUpRight, Download, Save, X } from "lucide-react";
import { Card, InfoHint } from "@/components/ui/Primitives";
import { axisNumber, Chart } from "@/modules/artifacts/Chart";
import { useSalesStore } from "./store";
import { request, getV2Detail, getV2Followups, patchV2Workflow } from "./api";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { CustomerEvidence } from "./IntegratedWorkspace";
import { mapPosition, opportunityRegions } from "./opportunity-regions";
import type {
  OpportunityFilters,
  OpportunityPoint,
  OpportunityResponse,
} from "@/types/opportunities";
import type { Detail } from "@/types/sales-v2";

const format = (n: number | null | undefined) =>
  n == null
    ? "Unavailable"
    : n.toLocaleString(undefined, { maximumFractionDigits: 1 });
const STORAGE_KEY = "pecal-opportunity-shortlists-v1";
interface SavedList {
  name: string;
  snapshot: string;
  reference: string;
  model: string;
  saved_at: string;
  filters: OpportunityFilters;
  cluster: string | null;
  ids: string[];
}
function download(name: string, content: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
export function OpportunityDashboard() {
  const s = useSalesStore(),
    sid = s.v2!.metadata.snapshot_id;
  const [pending, setPending] = useState(false),
    [error, setError] = useState("");
  const offset = s.dashboardOffset;
  const setOffset = (value: number) => s.set({ dashboardOffset: value });
  const [detail, setDetail] = useState<Detail | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedLists, setSavedLists] = useState<SavedList[]>([]);
  const data = s.opportunities;
  useEffect(() => {
    s.set({ commercialScenario: null });
  }, [s.set]);
  useEffect(() => {
    try {
      setSavedLists(JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"));
    } catch {
      setSavedLists([]);
    }
  }, []);
  useEffect(() => {
    setOffset(0);
  }, [s.opportunityFilters, s.opportunityCluster, s.actionLimit]);
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setPending(true);
    s.set({ opportunitiesLoading: true });
    setError("");
    const params = new URLSearchParams({
      snapshot_id: sid,
      ...Object.fromEntries(
        Object.entries(s.opportunityFilters).map(([k, v]) => [k, String(v)]),
      ),
      display_limit: String(s.opportunityDisplayLimit),
      limit: String(s.actionLimit),
      offset: String(offset),
    });
    if (s.opportunityCluster) params.set("cluster_id", s.opportunityCluster);
    request<OpportunityResponse>(`v2/opportunities?${params}`, {
      signal: controller.signal,
    })
      .then((r) => {
        if (alive) s.set({ opportunities: r });
      })
      .catch((e) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) {
          setPending(false);
          s.set({ opportunitiesLoading: false });
        }
      });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [
    sid,
    s.opportunityFilters,
    s.opportunityCluster,
    s.opportunityDisplayLimit,
    s.actionLimit,
    offset,
    s.opportunityRevision,
    s.set,
  ]);
  useEffect(() => {
    if (!s.opportunityDrawerId) {
      setDetail(null);
      return;
    }
    let alive = true;
    setDetail(null);
    setError("");
    getV2Detail(sid, s.opportunityDrawerId, s.opportunityFilters)
      .then((d) => {
        if (alive) {
          setDetail(d);
          s.set({ v2Detail: d, selectedId: d.profile.customer_id });
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") s.set({ opportunityDrawerId: null });
    };
    document.addEventListener("keydown", close);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      alive = false;
      document.removeEventListener("keydown", close);
      document.body.style.overflow = previous;
    };
  }, [
    sid,
    s.opportunityDrawerId,
    s.opportunityFilters,
    s.workflowRevision,
    s.set,
  ]);
  const changeFilters = (patch: Partial<OpportunityFilters>) =>
    s.set({
      opportunityFilters: { ...s.opportunityFilters, ...patch },
      opportunityCluster: null,
    });
  const open = (id: string) =>
    s.set({
      opportunityDrawerId: id,
      selectedId: id,
      customerTab: "activity",
    });
  const refresh = async () => {
    if (!s.opportunityDrawerId) return;
    const [d, tasks] = await Promise.all([
      getV2Detail(sid, s.opportunityDrawerId, s.opportunityFilters),
      getV2Followups(sid),
    ]);
    setDetail(d);
    s.set({
      v2Detail: d,
      data: { ...useSalesStore.getState().data, followups: tasks.items },
      opportunityRevision: useSalesStore.getState().opportunityRevision + 1,
    });
  };
  const changeWorkflow = async (patch: unknown) => {
    if (!s.opportunityDrawerId) return;
    setSaving(true);
    setError("");
    try {
      await patchV2Workflow(sid, s.opportunityDrawerId, patch);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  const saveList = () => {
    if (!data || pending) return;
    const list: SavedList = {
      name: `${data.clusters.find((c) => c.id === data.selected_cluster)?.label || "All opportunities"} · ${data.items.length} accounts`,
      snapshot: sid,
      reference: data.metadata.reference_date,
      model: data.model_version,
      saved_at: new Date().toISOString(),
      filters: data.filters,
      cluster: data.selected_cluster,
      ids: data.items.map((p) => p.customer_id),
    };
    const next = [list, ...savedLists].slice(0, 10);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      setSavedLists(next);
      s.set({ notice: "Shortlist saved on this browser" });
    } catch {
      setError(
        "Unable to save this shortlist in browser storage. Export it instead.",
      );
    }
  };
  const exportList = () => {
    if (!data) return;
    const lines = [
      `PeCal Pulse · ${data.items.length} accounts from ${data.selected_count} selected`,
      `History reference: ${data.metadata.reference_date}; generated: ${new Date().toISOString()}`,
      `Model: ${data.model_version}; selection: ${data.selection_revision}`,
      `Filters: ${JSON.stringify(data.filters)}; cluster: ${data.selected_cluster || "all"}`,
      "",
      ...data.items.flatMap((p) => [
        p.display_name,
        `ID: ${p.customer_id}`,
        `${p.industry_label} · ${p.segment_label || "Insufficient segment history"} · priority ${format(p.priority_score)}/100`,
        `${p.due_recorded} recorded + ${p.due_inferred} inferred due instruments; activity review: ${p.activity_flagged ? "yes" : "no supported flag"}`,
        `Owner: ${p.owner || "Unassigned"}; readiness: ${p.readiness}`,
        `Next: ${p.next_action}`,
        ...p.reasons,
        "",
      ]),
    ];
    download("pecal-action-shortlist.txt", lines.join("\n"));
  };
  const chart: EChartsOption = data
    ? {
        animationDuration: 250,
        tooltip: {
          trigger: "item",
          renderMode: "richText",
          formatter: (params) => {
            // Custom region polygons fire item tooltips without a data
            // payload; fall back to the series name instead of crashing.
            const raw = params as unknown as {
              data?: {
                point?: OpportunityPoint;
                cluster?: string;
                groupLabel?: string;
              };
              seriesName?: string;
            };
            const p = raw.data;
            if (p?.cluster)
              return `${p.groupLabel}\nClick to select this group`;
            const c = p?.point;
            if (c)
              return `${c.display_name}\n${c.industry_label} · ${c.segment_label || "Unassigned segment"}\nUrgency percentile ${format(c.urgency_score)} · size percentile ${format(c.size_score)}\n${c.size_basis?.replaceAll("_", " ")}\n${c.due_recorded + c.due_inferred} due instruments\nClick to prepare conversation`;
            const region = raw.seriesName?.replace(/ region$/, "");
            return region && region !== raw.seriesName
              ? `${region}\nClick to select this group`
              : "";
          },
        },
        grid: { left: 58, right: 32, top: 32, bottom: 70 },
        xAxis: {
          type: "value",
          min: -100,
          max: 100,
          axisLabel: { formatter: axisNumber },
          name: "Relative action urgency →",
          nameLocation: "middle",
          nameGap: 40,
          splitLine: { lineStyle: { color: "#e9eee5" } },
          axisLine: { show: false },
        },
        yAxis: {
          type: "value",
          min: -100,
          max: 100,
          axisLabel: { formatter: axisNumber },
          name: "Relative opportunity size",
          nameGap: 14,
          splitLine: { lineStyle: { color: "#e9eee5" } },
          axisLine: { show: false },
        },
        dataZoom: [
          { type: "inside", xAxisIndex: 0 },
          { type: "inside", yAxisIndex: 0 },
        ],
        series: [
          ...opportunityRegions(data.clusters).map((c) => ({
            name: `${c.label} region`,
            type: "custom" as const,
            clip: true,
            z: 0,
            renderItem: (
              _params: unknown,
              api: { coord: (p: number[]) => number[] },
            ) => ({
              type: "polygon" as const,
              shape: {
                points: c.polygon.map((p) => api.coord(p.map(mapPosition))),
              },
              style: {
                fill: c.color,
                opacity: !data.selected_cluster
                  ? 0.2
                  : data.selected_cluster === c.id
                    ? 0.32
                    : 0.1,
                stroke: c.color,
                lineWidth: data.selected_cluster === c.id ? 2 : 1,
              },
            }),
            data: [
              {
                value: [mapPosition(c.urgency), mapPosition(c.size)],
                cluster: c.id,
                groupLabel: c.label,
              },
            ],
          })),
          ...data.clusters.map((c) => ({
            name: c.label,
            type: "scatter" as const,
            symbolSize: 8,
            itemStyle: {
              color: c.color,
              opacity:
                !data.selected_cluster || data.selected_cluster === c.id
                  ? 0.65
                  : 0.12,
            },
            emphasis: { scale: 2, itemStyle: { opacity: 1 } },
            data: data.points
              .filter((p) => p.cluster_id === c.id)
              .map((p) => ({
                value: [
                  mapPosition(p.urgency_score!),
                  mapPosition(p.size_score!),
                ],
                point: p,
              })),
          })),
          {
            name: "Group centers",
            type: "scatter",
            symbolSize: 4,
            z: 5,
            data: data.clusters
              .filter((c) => c.matching_count > 0)
              .map((c) => ({
                value: [mapPosition(c.urgency), mapPosition(c.size)],
                cluster: c.id,
                groupLabel: c.label,
                itemStyle: {
                  color: c.color,
                  borderColor: c.color,
                  borderWidth: 0,
                },
                label: {
                  show: true,
                  formatter: c.label,
                  color: "#35432f",
                  fontSize: 11,
                  position: "top" as const,
                },
              })),
          },
        ],
      }
    : {};
  return (
    <>
      <div className="page-heading opportunity-heading">
        <div>
          <h1>Opportunity dashboard</h1>
        </div>
      </div>
      <div className="filters opportunity-filters">
        {(
          [
            ["industry", "Sector", "industries"],
            ["group", "Equipment category", "groups"],
            ["segment", "Customer segment", "segments"],
          ] as const
        ).map(([key, label, options]) => (
          <label key={key}>
            {label}
            <select
              aria-label={label}
              value={s.opportunityFilters[key]}
              onChange={(e) => changeFilters({ [key]: e.target.value })}
            >
              <option value="all">All {label.toLowerCase()}s</option>
              {data?.filter_options[options].map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label>
          Opportunity type
          <select
            aria-label="Opportunity type"
            value={s.opportunityFilters.purpose}
            onChange={(e) =>
              changeFilters({
                purpose: e.target.value as OpportunityFilters["purpose"],
              })
            }
          >
            <option value="all">All opportunities</option>
            <option value="upcoming">Upcoming needs</option>
            <option value="inactivity">Activity review</option>
            <option value="discovery">Service discovery</option>
          </select>
        </label>
        <label>
          Due window
          <select
            aria-label="Due window"
            value={s.opportunityFilters.window_days}
            onChange={(e) =>
              changeFilters({
                window_days: Number(e.target.value) as 30 | 60 | 90,
              })
            }
          >
            {[30, 60, 90].map((n) => (
              <option key={n} value={n}>
                Next {n} days
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && (
        <p className="opportunity-error" role="alert">
          {error}
        </p>
      )}
      {!data ? (
        <Card>
          <p role="status">Preparing opportunity map…</p>
        </Card>
      ) : (
        <div
          aria-busy={pending}
          className={pending ? "opportunity-updating" : ""}
        >
          <Card className="opportunity-map">
            <div className="card-heading">
              <div>
                <h2>Where should we focus?</h2>
                <InfoHint label="opportunity clusters">
                  Four opportunity groups, independent of customer segments.
                  Axes show relative percentile positions from −100 to +100;
                  zero is the reference-cohort median. Size uses quantities, not
                  profit. Shaded boundaries follow the frozen model. Filters do
                  not refit it; identical evidence stays together.
                </InfoHint>
              </div>
              <label className="point-limit">
                Show
                <select
                  aria-label="Map point limit"
                  value={s.opportunityDisplayLimit}
                  onChange={(e) =>
                    s.set({ opportunityDisplayLimit: Number(e.target.value) })
                  }
                >
                  <option value={200}>200 points</option>
                  <option value={500}>500 points</option>
                  <option value={1000}>1,000 points</option>
                </select>
              </label>
            </div>
            <div className="opportunity-legend">
              <button
                className={!s.opportunityCluster ? "selected" : ""}
                aria-pressed={!s.opportunityCluster}
                disabled={pending}
                onClick={() => s.set({ opportunityCluster: null })}
              >
                All opportunities <b>{format(data.matching_count)}</b>
              </button>
              {data.clusters.map((c) => (
                <button
                  key={c.id}
                  className={s.opportunityCluster === c.id ? "selected" : ""}
                  aria-pressed={s.opportunityCluster === c.id}
                  disabled={pending}
                  onClick={() =>
                    s.set({
                      opportunityCluster:
                        s.opportunityCluster === c.id ? null : c.id,
                    })
                  }
                >
                  <i style={{ background: c.color }} />
                  {c.label} <b>{format(c.matching_count)}</b>
                </button>
              ))}
            </div>
            <Chart
              option={chart}
              height={480}
              label="Customer opportunities plotted by urgency and opportunity size. Select a group using the buttons above, or click a customer point."
              onClick={(params) => {
                if (pending) return;
                const hit = params.data as {
                  point?: OpportunityPoint;
                  cluster?: string;
                };
                if (hit.cluster) s.set({ opportunityCluster: hit.cluster });
                else if (hit.point) open(hit.point.customer_id);
              }}
            />
            <div className="opportunity-map-footer">
              <span>
                {format(data.displayed_count)} displayed ·{" "}
                {format(data.matching_count - data.unassigned_count)} scored ·{" "}
                {format(data.selected_count)} selected
              </span>
              <button
                className="text-button"
                disabled={pending}
                onClick={() => s.set({ opportunityCluster: "needs-evidence" })}
              >
                {format(data.unassigned_count)} need more evidence
              </button>
              <label>
                <input
                  type="checkbox"
                  checked={s.opportunityFilters.include_inferred}
                  onChange={(e) =>
                    changeFilters({ include_inferred: e.target.checked })
                  }
                />{" "}
                Include inferred dates
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={s.opportunityFilters.include_past_due}
                  onChange={(e) =>
                    changeFilters({ include_past_due: e.target.checked })
                  }
                />{" "}
                Review past-due records
              </label>
            </div>
          </Card>
          <div className="metrics opportunity-metrics">
            {data.metrics.map((m, i) => (
              <div
                className={`metric ${["mint", "peach", "lavender", "mint"][i]}`}
                key={m.label}
                title={m.definition}
              >
                <div className="metric-top">
                  {m.label}{" "}
                  <InfoHint label={m.label}>
                    {m.definition} {m.caption}
                  </InfoHint>
                </div>
                <strong>
                  {m.value == null ? (
                    "Unavailable"
                  ) : (
                    <AnimatedNumber value={Number(m.value.toFixed(1))} />
                  )}
                </strong>
                {i === 3 && (
                  <button
                    className="text-button"
                    onClick={() =>
                      s.set({
                        customerView: "follow-ups",
                        requestedPage: "customers",
                      })
                    }
                  >
                    View follow-ups →
                  </button>
                )}
              </div>
            ))}
          </div>
          <div className="opportunity-attention">
            <div>
              <strong>{format(data.overdue_count)} overdue follow-ups</strong>
              <span>Keep agreed next steps moving.</span>
            </div>
            <div>
              <strong>
                {format(data.unassigned_owner_count)} opportunities without an
                owner
              </strong>
              <span>Open an account to assign responsibility.</span>
            </div>
            {data.due_followups.map((f) => (
              <button
                className="button"
                key={f.id}
                onClick={() => open(f.customer_id)}
              >
                {f.customer_name} · {f.due_date}
                <ArrowUpRight size={14} />
              </button>
            ))}
          </div>
          <Card>
            <div className="card-heading">
              <div>
                <h2>Your next best conversations</h2>
                <InfoHint label="customer shortlist">
                  {data.selected_count.toLocaleString()} selected customers,
                  ranked by evidence priority. The shortlist and metrics use the
                  full selected group, not just displayed dots.
                </InfoHint>
              </div>
              <div className="opportunity-toolbar">
                <label>
                  Shortlist
                  <select
                    aria-label="Shortlist size"
                    value={s.actionLimit}
                    onChange={(e) =>
                      s.set({
                        actionLimit: Number(e.target.value) as 5 | 10 | 12,
                      })
                    }
                  >
                    {[5, 10, 12].map((n) => (
                      <option value={n} key={n}>
                        {n} accounts
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="button"
                  disabled={pending || !data.items.length}
                  onClick={saveList}
                >
                  <Save size={14} /> Save
                </button>
                <button
                  className="button"
                  disabled={pending || !data.items.length}
                  onClick={exportList}
                >
                  <Download size={14} /> Export
                </button>
              </div>
            </div>
            <div className="integrated-table">
              <table>
                <thead>
                  <tr>
                    <th>Customer / sector / segment</th>
                    <th>Why now</th>
                    <th>Due instruments</th>
                    <th>Activity</th>
                    <th>Priority</th>
                    <th>Owner / next action</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((p) => (
                    <tr key={p.customer_id}>
                      <td>
                        <strong>{p.display_name}</strong>
                        <small>{p.industry_label}</small>
                        <span className="badge neutral">
                          {p.segment_label || "Insufficient segment history"}
                        </span>
                      </td>
                      <td>
                        {p.reason_types.includes("upcoming")
                          ? "Upcoming calibration needs"
                          : p.activity_flagged
                            ? "Check reduced activity"
                            : p.reason_types.includes("discovery")
                              ? "Explore an additional service"
                              : "Review customer history"}
                        <small>
                          {p.size_basis?.replaceAll("_", " ") || "Unscored"} ·{" "}
                          {p.readiness === "review_required"
                            ? "Confirm details first"
                            : p.readiness.replaceAll("_", " ")}
                        </small>
                      </td>
                      <td>
                        {format(p.due_recorded + p.due_inferred)}
                        <small>
                          {p.due_recorded} dates on file · {p.due_inferred}{" "}
                          estimated
                          {data.filters.group !== "all"
                            ? ` · ${p.due_selected_category} in category`
                            : ""}
                        </small>
                      </td>
                      <td>
                        <span
                          className={`badge ${p.activity_flagged ? "orange" : "neutral"}`}
                        >
                          {p.activity_flagged
                            ? "Review inactivity"
                            : p.inactivity_supported
                              ? "No review flag"
                              : "Insufficient evidence"}
                        </span>
                        <small>
                          {p.activity_probability == null
                            ? "Return forecast unavailable"
                            : `${Math.round(p.activity_probability * 100)}% chance of calibration activity`}
                        </small>
                      </td>
                      <td>
                        <strong>{format(p.priority_score)}</strong>
                        <small>rule score / 100</small>
                        {p.priority_components &&
                          Object.keys(p.priority_components).length > 0 && (
                            <InfoHint
                              label={`priority breakdown for ${p.display_name}`}
                            >
                              {`Score parts (0–1, null means no evidence): ${Object.entries(
                                p.priority_components,
                              )
                                .map(
                                  ([k, v]) =>
                                    `${k.replace(/_/g, " ")} ${v == null ? "—" : (v as number).toFixed(2)}`,
                                )
                                .join(" · ")}. Weights${
                                data?.ranking_weights
                                  ? ` (${Object.entries(data.ranking_weights)
                                      .map(
                                        ([k, w]) =>
                                          `${k.replace(/_/g, " ")} ${Math.round((w as number) * 100)}%`,
                                      )
                                      .join(", ")})`
                                  : ""
                              } are business assumptions, not measured prices; expected value is priority points, never euros.`}
                            </InfoHint>
                          )}
                      </td>
                      <td>
                        {p.owner || "Unassigned"}
                        <small>{p.next_action}</small>
                      </td>
                      <td>
                        <button
                          className="button"
                          disabled={pending}
                          onClick={() => open(p.customer_id)}
                        >
                          Prepare <ArrowUpRight size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!data.items.length && (
                <p>
                  No accounts match this selection. Reset the group or adjust
                  filters.
                </p>
              )}
            </div>
            <div className="integrated-pagination">
              <button
                className="button"
                disabled={pending || !offset}
                onClick={() => setOffset(Math.max(0, offset - s.actionLimit))}
              >
                Previous
              </button>
              <span>
                {data.selected_count ? offset + 1 : 0}–
                {Math.min(offset + s.actionLimit, data.selected_count)} of{" "}
                {format(data.selected_count)}
              </span>
              <button
                className="button"
                disabled={
                  pending || offset + s.actionLimit >= data.selected_count
                }
                onClick={() => setOffset(offset + s.actionLimit)}
              >
                Next
              </button>
            </div>
            <small>
              History reference {data.metadata.reference_date} ·{" "}
              {data.forecast_supported}/{data.selected_count} forecast coverage
              · calibration events, not orders. Equipment filters select
              accounts; forecasts remain all-services.
            </small>
            {savedLists.length > 0 && (
              <details className="saved-lists">
                <summary>Saved shortlists ({savedLists.length})</summary>
                {savedLists.map((l, i) => (
                  <div key={l.saved_at}>
                    <span>
                      {l.name} · {l.saved_at.slice(0, 10)} · {l.reference}
                    </span>
                    <button
                      className="text-button"
                      onClick={() => {
                        if (l.snapshot !== sid) {
                          setError(
                            "This shortlist uses another snapshot. Export it for review.",
                          );
                          return;
                        }
                        s.set({
                          opportunityFilters: l.filters,
                          opportunityCluster: l.cluster,
                        });
                        s.set({
                          notice:
                            "Selection restored; current workflow rechecked. Saved membership available in export.",
                        });
                      }}
                    >
                      Restore selection
                    </button>
                    <button
                      className="text-button"
                      onClick={() =>
                        download(
                          `shortlist-${i + 1}.json`,
                          JSON.stringify(l, null, 2),
                          "application/json",
                        )
                      }
                    >
                      Export saved IDs
                    </button>
                  </div>
                ))}
              </details>
            )}
          </Card>
        </div>
      )}
      {s.opportunityDrawerId && (
        <div
          className="opportunity-drawer-backdrop"
          onClick={() => s.set({ opportunityDrawerId: null })}
        >
          <aside
            className="opportunity-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Customer conversation preparation"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="opportunity-drawer-header">
              <strong>Prepare the conversation</strong>
              <button
                className="icon-button"
                aria-label="Close customer preparation"
                onClick={() => s.set({ opportunityDrawerId: null })}
              >
                <X size={20} />
              </button>
            </div>
            {error && <p role="alert">{error}</p>}
            {detail ? (
              <CustomerEvidence
                detail={detail}
                pending={saving}
                onWorkflow={changeWorkflow}
                onSaved={refresh}
              />
            ) : (
              <Card>
                <p>Loading account evidence…</p>
              </Card>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
