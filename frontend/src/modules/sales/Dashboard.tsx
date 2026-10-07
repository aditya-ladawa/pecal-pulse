"use client";
import { useMemo } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  ChevronRight,
  CalendarDays,
  Sparkles,
  UsersRound,
  Clock3,
  ChartNoAxesCombined,
  Plus,
  X,
} from "lucide-react";
import type { EChartsOption } from "echarts";
import { useSalesStore } from "./store";
import { dashboardSnapshot } from "./page-context";
import { dispatchCommand, openCustomer } from "@/core/events/router";
import { Chart, ArtifactChart } from "@/modules/artifacts/Chart";
import { ActionBadge, Avatar, Badge, Card } from "@/components/ui/Primitives";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
export function Dashboard() {
  const data = useSalesStore((s) => s.data),
    limit = useSalesStore((s) => s.actionLimit),
    set = useSalesStore((s) => s.set),
    artifacts = useSalesStore((s) => s.artifacts);
  const customers = data.customers;
  const metrics = dashboardSnapshot(data).metrics;
  const activeTasks = data.followups.filter((f) => f.status === "open");
  const segmentOption = useMemo<EChartsOption>(
    () => ({
      tooltip: { trigger: "item" },
      legend: { show: false },
      series: [
        {
          type: "pie",
          radius: ["62%", "84%"],
          center: ["40%", "49%"],
          itemStyle: { borderRadius: 8, borderWidth: 5, borderColor: "#fff" },
          label: { show: false },
          data: ["Frequent", "Intermittent", "Occasional"].map((name) => ({
            name,
            value: customers.filter((c) => c.segment === name).length,
          })),
        },
      ],
      graphic: [
        {
          type: "text",
          left: "33%",
          top: "39%",
          style: {
            text: String(customers.length),
            fill: "#2f402a",
            font: "600 35px sans-serif",
          },
        },
        {
          type: "text",
          left: "28%",
          top: "57%",
          style: {
            text: "demo accounts",
            fill: "#838c7d",
            font: "11px sans-serif",
          },
        },
      ],
    }),
    [customers],
  );
  const sectorOption = useMemo<EChartsOption>(
    () => ({
      tooltip: { trigger: "axis" },
      grid: { left: 37, right: 14, top: 20, bottom: 35 },
      xAxis: {
        type: "category",
        data: data.sector_labels,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          fontSize: 10,
          formatter: (v) => (v === "Manufacturing" ? "Manuf." : v),
        },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "#edf0e9" } } },
      series: [
        {
          name: "Mock next-quarter calibrations",
          type: "bar",
          barMaxWidth: 34,
          itemStyle: { borderRadius: [9, 9, 0, 0], color: "#99b88d" },
          data: data.sector_labels.map((ind) =>
            customers
              .filter((c) => c.industry === ind)
              .reduce(
                (sum, c) => sum + c.forecast.reduce((a, b) => a + b, 0),
                0,
              ),
          ),
        },
      ],
    }),
    [data, customers],
  );
  const correlationOption = useMemo<EChartsOption>(
    () => ({
      tooltip: {
        position: "top",
        formatter: (p) => {
          const point = p as unknown as { data: number[] };
          return `${data.sector_labels[point.data[0]]} × ${data.sector_labels[point.data[1]]}<br/>Mock correlation: ${point.data[2]}`;
        },
      },
      grid: { top: 10, bottom: 45, left: 110, right: 70 },
      xAxis: {
        type: "category",
        data: data.sector_labels,
        splitArea: { show: true },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          fontSize: 10,
          formatter: (v) => (v === "Manufacturing" ? "Manuf." : v),
        },
      },
      yAxis: {
        type: "category",
        data: data.sector_labels,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 11 },
      },
      visualMap: {
        min: 0,
        max: 1,
        calculable: false,
        orient: "vertical",
        right: 0,
        top: 40,
        inRange: { color: ["#f2f4e9", "#dce9ca", "#a4c397", "#527f51"] },
        text: ["1.0", "0.0"],
        itemHeight: 120,
        itemWidth: 9,
      },
      series: [
        {
          type: "heatmap",
          data: data.sector_correlation.flatMap((row, y) =>
            row.map((value, x) => [x, y, value]),
          ),
          label: {
            show: true,
            fontSize: 11,
            formatter: (p) => String((p.data as number[])[2]),
          },
          itemStyle: { borderColor: "#fff", borderWidth: 6, borderRadius: 7 },
        },
      ],
    }),
    [data],
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            A GOOD DAY STARTS WITH A CLEAR NEXT STEP
          </div>
          <h1>
            Your next conversation<span className="heading-dot">.</span>
          </h1>
          <p>
            A focused shortlist of customers to help, and the evidence behind
            each opportunity.
          </p>
        </div>
        <button
          className="button dark"
          onClick={() => set({ assistantOpen: true })}
        >
          <Sparkles size={16} /> Ask your assistant
        </button>
      </div>
      <div className="metrics">
        <div className="metric mint">
          <div className="metric-top">
            {metrics[0].label}
            <UsersRound size={18} />
          </div>
          <strong>
            <AnimatedNumber value={metrics[0].value} />
          </strong>
          <span>Across 5 demo industries</span>
          <div className="metric-decoration" />
        </div>
        <div className="metric peach">
          <div className="metric-top">
            {metrics[1].label}
            <CalendarDays size={18} />
          </div>
          <strong>
            <AnimatedNumber value={metrics[1].value} />
            <small> instruments</small>
          </strong>
          <span>Mock due-date window · next 30 days</span>
        </div>
        <div className="metric lavender">
          <div className="metric-top">
            {metrics[2].label}
            <Clock3 size={18} />
          </div>
          <strong>
            <AnimatedNumber value={metrics[2].value} />
          </strong>
          <span>Due or overdue on the demo date</span>
        </div>
        <div className="metric cream">
          <div className="metric-top">
            {metrics[3].label}
            <ChartNoAxesCombined size={18} />
          </div>
          <strong>
            <AnimatedNumber value={metrics[3].value} />
          </strong>
          <span>Unusual gaps to investigate</span>
        </div>
      </div>
      <Card className="opportunities">
        <div className="card-heading">
          <div>
            <div className="eyebrow">YOUR NEXT BEST ACTIONS</div>
            <h2>Good reasons to reach out</h2>
            <p>
              A review shortlist, with timing and instrument quantities kept
              visible.
            </p>
          </div>
          <div className="card-actions">
            <label className="compact-select">
              Show{" "}
              <select
                aria-label="Action shortlist size"
                value={limit}
                onChange={(e) =>
                  set({ actionLimit: Number(e.target.value) as 5 | 10 | 12 })
                }
              >
                <option value={5}>5 accounts</option>
                <option value={10}>10 accounts</option>
                <option value={12}>All 12</option>
              </select>
            </label>
            <Link href="/customers" className="text-link">
              View all <ArrowUpRight size={15} />
            </Link>
          </div>
        </div>
        <div className="table-scroll">
          <table className="opportunity-table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Why now</th>
                <th>Quantity basis</th>
                <th>Timing</th>
                <th>
                  <span className="sr-only">Open customer</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {customers.slice(0, limit).map((c, i) => (
                <tr key={c.id} onClick={() => openCustomer(c.id)}>
                  <td>
                    <div className="account-cell">
                      <Avatar initials={c.initials} index={i} />
                      <div>
                        <button
                          className="account-link"
                          onClick={(e) => {
                            e.stopPropagation();
                            openCustomer(c.id);
                          }}
                        >
                          {c.name}
                        </button>
                        <small>{c.industry}</small>
                      </div>
                    </div>
                  </td>
                  <td>
                    <ActionBadge action={c.action} />
                    <span className="table-reason">
                      {c.action === "upcoming"
                        ? "Confirm the next calibration batch"
                        : c.action === "inactivity"
                          ? "Three months without recorded activity"
                          : "Explore a peer-supported service"}
                    </span>
                  </td>
                  <td>
                    <strong>
                      {c.recorded_due ||
                        c.groups.reduce((s, g) => s + g.instruments, 0)}
                    </strong>{" "}
                    instruments
                    <small>
                      {c.action === "upcoming"
                        ? "Recorded demo due dates"
                        : "Observed demo portfolio"}
                    </small>
                  </td>
                  <td>
                    <span className="timing">
                      <span className={`timing-dot ${c.action}`} />
                      {c.window}
                    </span>
                  </td>
                  <td>
                    <button
                      className="row-arrow"
                      aria-label={`Open ${c.name}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        openCustomer(c.id);
                      }}
                    >
                      <ChevronRight size={17} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card-footnote">
          <span className="small-dot" />
          Priority uses timing, quantity and evidence in this mock. Financial
          value and outreach benefit are unknown.
        </div>
      </Card>
      <div className="chart-grid">
        <Card>
          <div className="card-heading">
            <div>
              <div className="eyebrow">THE BIGGER PICTURE</div>
              <h2>Your customer mix</h2>
            </div>
            <Badge>Mock segments</Badge>
          </div>
          <div className="mix-chart">
            <Chart
              option={segmentOption}
              label="Synthetic customer segment mix"
              height={230}
            />
            <div className="mix-legend">
              {["Frequent", "Intermittent", "Occasional"].map((s, i) => (
                <button
                  key={s}
                  onClick={() => {
                    dispatchCommand({
                      type: "customers.filters.set",
                      payload: {
                        segment: s as
                          | "Frequent"
                          | "Intermittent"
                          | "Occasional",
                        industry: "all",
                        action: "all",
                        query: "",
                      },
                    });
                    dispatchCommand({
                      type: "ui.navigate",
                      payload: { page: "customers" },
                    });
                  }}
                >
                  <i
                    style={{ background: ["#72966a", "#edb482", "#a9bad8"][i] }}
                  />
                  <span>{s}</span>
                  <b>{customers.filter((c) => c.segment === s).length}</b>
                </button>
              ))}
            </div>
          </div>
        </Card>
        <Card>
          <div className="card-heading">
            <div>
              <div className="eyebrow">LOOKING AHEAD</div>
              <h2>Activity by industry</h2>
            </div>
            <Badge tone="green">Mock forecast</Badge>
          </div>
          <Chart
            option={sectorOption}
            label="Synthetic calibration counts next quarter by industry"
            height={230}
          />
          <p className="chart-caption">
            Oct–Dec 2026 · calibration events, not orders or revenue
          </p>
        </Card>
      </div>
      <Card className="correlation-card">
        <div className="card-heading">
          <div>
            <div className="eyebrow">EXPLORE THE CONNECTIONS</div>
            <h2>Do sectors move together?</h2>
            <p>
              Inspect sector relationships before assuming shared demand
              patterns.
            </p>
          </div>
          <Badge>Illustrative correlation</Badge>
        </div>
        <div className="correlation-grid">
          <Chart
            option={correlationOption}
            label="Synthetic sector correlation heatmap. Not measured from the database."
            height={255}
          />
          <div className="correlation-note">
            <span className="note-icon">
              <ChartNoAxesCombined size={21} />
            </span>
            <h3>Context for a better question.</h3>
            <p>
              Automotive and electronics show similar movement in this example.
              A correlation is not a forecast or proof of cause.
            </p>
            <span>
              Real sector relationships and backtests will replace this mock.
            </span>
          </div>
        </div>
      </Card>
      {!!artifacts.length && (
        <section className="artifact-section">
          <div className="section-heading">
            <div>
              <div className="eyebrow">CREATED WITH YOUR ASSISTANT</div>
              <h2>Your workspace charts</h2>
            </div>
            <Badge tone="purple">
              <Plus size={12} /> {artifacts.length} artifact
              {artifacts.length > 1 ? "s" : ""}
            </Badge>
          </div>
          <div className="chart-grid">
            {artifacts.map((a) => (
              <Card key={a.id}>
                <div className="card-heading">
                  <h2>{a.title}</h2>
                  <button
                    className="icon-button"
                    aria-label={`Remove ${a.title}`}
                    onClick={() =>
                      set({
                        artifacts: artifacts.filter((item) => item.id !== a.id),
                      })
                    }
                  >
                    <X size={17} />
                  </button>
                </div>
                <ArtifactChart artifact={a} />
                <p className="chart-caption">
                  Synthetic {a.unit} · created through a typed workspace command
                </p>
              </Card>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
