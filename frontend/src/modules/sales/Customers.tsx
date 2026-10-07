"use client";
import { useEffect, useMemo, useState } from "react";
import {
  Search,
  ArrowUpRight,
  ArrowDownToLine,
  CalendarDays,
  Sparkles,
  Info,
  ShieldCheck,
  Layers,
  Check,
  ChevronRight,
} from "lucide-react";
import type { EChartsOption } from "echarts";
import { useSalesStore, filterCustomers, defaultFilters } from "./store";
import { dispatchCommand, dispatchEvent } from "@/core/events/router";
import { saveFollowup } from "./api";
import { Chart } from "@/modules/artifacts/Chart";
import { Avatar, Badge, Card, ActionBadge } from "@/components/ui/Primitives";
import type { Customer, CustomerFilters } from "@/types/sales";
const months = (s: string) =>
  new Date(s + "-01T12:00:00").toLocaleDateString("en-GB", {
    month: "short",
    year: "2-digit",
  });
export function Customers() {
  const data = useSalesStore((s) => s.data),
    filters = useSalesStore((s) => s.filters),
    selectedId = useSalesStore((s) => s.selectedId);
  const [activeTab, setTab] = useState<"activity" | "portfolio" | "next-step">(
    "activity",
  );
  const visible = useMemo(
    () => filterCustomers(data, filters),
    [data, filters],
  );
  const customer = visible.find((c) => c.id === selectedId) || visible[0];
  useEffect(() => {
    if (customer && customer.id !== selectedId)
      dispatchCommand({
        type: "customers.select",
        payload: { customer_id: customer.id },
      });
  }, [customer, selectedId]);
  const filter = (patch: Partial<CustomerFilters>) =>
    dispatchCommand({ type: "customers.filters.set", payload: patch });
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ONE ACCOUNT. THE WHOLE PICTURE.</div>
          <h1>
            Customer workspace<span className="heading-dot">.</span>
          </h1>
          <p>
            Explore the signal, understand the account, and make the next step
            useful.
          </p>
        </div>
        <Badge tone="green">
          <UsersIcon /> {visible.length} of {data.customers.length} accounts
        </Badge>
      </div>
      <div className="filter-bar">
        <label>
          Industry
          <select
            aria-label="Industry"
            value={filters.industry}
            onChange={(e) => filter({ industry: e.target.value })}
          >
            <option value="all">All industries</option>
            {data.sector_labels.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Customer segment
          <select
            aria-label="Customer segment"
            value={filters.segment}
            onChange={(e) =>
              filter({ segment: e.target.value as CustomerFilters["segment"] })
            }
          >
            <option value="all">All segments</option>
            {["Frequent", "Intermittent", "Occasional"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Action purpose
          <select
            aria-label="Action purpose"
            value={filters.action}
            onChange={(e) =>
              filter({ action: e.target.value as CustomerFilters["action"] })
            }
          >
            <option value="all">All actions</option>
            <option value="upcoming">Upcoming needs</option>
            <option value="inactivity">Activity review</option>
            <option value="discovery">Service discovery</option>
          </select>
        </label>
        <button
          className="text-link reset-filters"
          onClick={() => filter(defaultFilters)}
        >
          Reset filters
        </button>
      </div>
      <div className="customer-grid">
        <Card className="customer-list">
          <div className="list-heading">
            <h2>
              Your accounts <span>{visible.length}</span>
            </h2>
            <div className="search-field">
              <Search size={16} />
              <input
                aria-label="Search customers"
                placeholder="Find an account or ID…"
                value={filters.query}
                onChange={(e) => filter({ query: e.target.value })}
              />
            </div>
          </div>
          <div className="customer-list-scroll">
            {visible.map((c, i) => (
              <button
                key={c.id}
                className={`customer-item ${customer?.id === c.id ? "selected" : ""}`}
                onClick={() =>
                  dispatchCommand({
                    type: "customers.select",
                    payload: { customer_id: c.id },
                  })
                }
              >
                <div className="customer-item-top">
                  <Avatar initials={c.initials} index={i} />
                  <div>
                    <strong>{c.name}</strong>
                    <small>
                      {c.industry} · {c.id}
                    </small>
                  </div>
                  <ChevronRight size={14} />
                </div>
                <div className="customer-item-bottom">
                  <ActionBadge action={c.action} />
                  <span>{c.window}</span>
                </div>
              </button>
            ))}
            {!visible.length && (
              <div className="empty-state">
                <Search size={28} />
                <h3>No matching accounts</h3>
                <p>Try another industry, segment or search term.</p>
                <button
                  className="button light"
                  onClick={() => filter(defaultFilters)}
                >
                  Clear filters
                </button>
              </div>
            )}
          </div>
          <div className="list-footer">
            Synthetic accounts · sorted by demo priority
          </div>
        </Card>
        <div className="customer-detail">
          {customer ? (
            <>
              <Card className="customer-profile">
                <div className="customer-profile-top">
                  <Avatar
                    initials={customer.initials}
                    large
                    index={data.customers.indexOf(customer)}
                  />
                  <div>
                    <div className="eyebrow">{customer.id} · DEMO ACCOUNT</div>
                    <h2>{customer.name}</h2>
                    <div className="profile-tags">
                      <span>{customer.industry}</span>
                      <span>•</span>
                      <span>{customer.segment} activity</span>
                      <span>•</span>
                      <span>Owner: {customer.owner}</span>
                    </div>
                  </div>
                </div>
                <div className="customer-profile-actions">
                  <button
                    className="button dark"
                    onClick={() => setTab("next-step")}
                  >
                    <Sparkles size={15} /> Prepare conversation
                  </button>
                  <button
                    className="button light"
                    onClick={() => setTab("next-step")}
                  >
                    <CalendarDays size={15} /> Add follow-up
                  </button>
                  <ActionBadge action={customer.action} />
                </div>
              </Card>
              <div
                className="detail-tabs"
                role="tablist"
                aria-label="Customer evidence sections"
              >
                {(["activity", "portfolio", "next-step"] as const).map(
                  (t, i) => (
                    <button
                      role="tab"
                      aria-selected={activeTab === t}
                      aria-controls={`customer-${t}`}
                      id={`tab-${t}`}
                      key={t}
                      className={activeTab === t ? "active" : ""}
                      onClick={() => setTab(t)}
                    >
                      {
                        [
                          "Activity & forecast",
                          "Portfolio & opportunities",
                          "Conversation & next step",
                        ][i]
                      }
                    </button>
                  ),
                )}
              </div>
              <div
                role="tabpanel"
                id={`customer-${activeTab}`}
                aria-labelledby={`tab-${activeTab}`}
              >
                {activeTab === "activity" ? (
                  <Activity customer={customer} />
                ) : activeTab === "portfolio" ? (
                  <Portfolio customer={customer} />
                ) : (
                  <NextStep key={customer.id} customer={customer} />
                )}
              </div>
            </>
          ) : (
            <Card className="empty-state">
              <Layers size={30} />
              <h2>Your next customer is here.</h2>
              <p>
                Adjust the filters to find an account and open its evidence.
              </p>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
function UsersIcon() {
  return <Layers size={13} />;
}
function Activity({ customer: c }: { customer: Customer }) {
  const option = useMemo<EChartsOption>(
    () => ({
      tooltip: { trigger: "axis" },
      legend: {
        bottom: 0,
        icon: "circle",
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { fontSize: 10 },
        data: ["Observed demo activity", "Mock forecast", "Illustrative range"],
      },
      grid: { top: 24, left: 40, right: 20, bottom: 65 },
      xAxis: {
        type: "category",
        data: c.months.map(months),
        boundaryGap: false,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 10, interval: 2 },
      },
      yAxis: {
        type: "value",
        name: "Calibrations",
        nameTextStyle: { fontSize: 10 },
        splitLine: { lineStyle: { color: "#edf0e9" } },
      },
      series: [
        {
          name: "range floor",
          type: "line",
          stack: "range",
          data: [...Array(12).fill(null), ...c.forecast_low],
          lineStyle: { opacity: 0 },
          symbol: "none",
          areaStyle: { opacity: 0 },
          tooltip: { show: false },
        },
        {
          name: "Illustrative range",
          type: "line",
          stack: "range",
          data: [
            ...Array(12).fill(null),
            ...c.forecast_high.map((v, i) => v - c.forecast_low[i]),
          ],
          lineStyle: { opacity: 0 },
          symbol: "none",
          areaStyle: { color: "#cfdfc7", opacity: 0.6 },
          tooltip: { show: false },
        },
        {
          name: "Observed demo activity",
          type: "line",
          smooth: 0.25,
          data: [...c.activity, null, null, null],
          lineStyle: { width: 3, color: "#65815e" },
          itemStyle: { color: "#65815e" },
          symbolSize: 5,
          areaStyle: { color: "#eff4ea", opacity: 0.6 },
        },
        {
          name: "Mock forecast",
          type: "line",
          smooth: 0.25,
          data: [...Array(11).fill(null), c.activity[11], ...c.forecast],
          lineStyle: { type: "dashed", width: 3, color: "#dfaa74" },
          itemStyle: { color: "#dfaa74" },
          symbolSize: 6,
          markArea: {
            silent: true,
            itemStyle: { color: "#fdf8ed", opacity: 0.3 },
            label: {
              show: true,
              fontSize: 10,
              color: "#a08d6c",
              position: "insideTop",
              formatter: "Forecast window",
            },
            data: [[{ xAxis: 12 }, { xAxis: 14 }]],
          },
        },
      ],
    }),
    [c],
  );
  return (
    <>
      <div className="detail-metrics">
        <div>
          <span>Any activity · next 90 days</span>
          <strong>
            {Math.round(c.return_probability * 100)}
            <small>%</small>
          </strong>
          <p>Mock probability · not churn</p>
        </div>
        <div>
          <span>Since last activity</span>
          <strong>
            {c.recency_months}
            <small> months</small>
          </strong>
          <p>
            Typical gap: {c.cadence_months} month
            {c.cadence_months > 1 ? "s" : ""}
          </p>
        </div>
        <div>
          <span>Recorded upcoming needs</span>
          <strong>
            {c.recorded_due}
            <small> instruments</small>
          </strong>
          <p>Inferred needs shown separately</p>
        </div>
      </div>
      <Card>
        <div className="card-heading">
          <div>
            <div className="eyebrow">THE STORY IN THE DATA</div>
            <h2>Activity, with a look ahead</h2>
          </div>
          <Badge tone="orange">Mock forecast</Badge>
        </div>
        <Chart
          option={option}
          label={`${c.name}: synthetic monthly calibration activity and October to December 2026 forecast`}
          height={300}
        />
        <div className="card-footnote">
          <Info size={13} />
          Shaded range is illustrative. No model has produced these preview
          values.
        </div>
      </Card>
      <Card className="reason-card">
        <div className="reason-title">
          <span className={`reason-icon ${c.action}`}>
            <Info size={20} />
          </span>
          <div>
            <div className="eyebrow">WHY THIS ACCOUNT APPEARS</div>
            <h2>
              {c.action === "inactivity"
                ? "A change worth understanding"
                : c.action === "discovery"
                  ? "A useful discovery question"
                  : "An upcoming need to confirm"}
            </h2>
          </div>
        </div>
        <p>{c.reason}</p>
        <div className="evidence-chips">
          <Badge>History: 30 Sept 2026</Badge>
          <Badge tone="green">
            {c.action === "upcoming"
              ? "Recorded demo date"
              : "Observed demo pattern"}
          </Badge>
          <Badge>Current order status: unknown</Badge>
        </div>
        <div className="reason-next">
          <ShieldCheck size={17} />
          <span>
            Confirm timing, equipment status and existing quotations before
            treating this as an outreach-ready opportunity.
          </span>
        </div>
      </Card>
    </>
  );
}
function Portfolio({ customer: c }: { customer: Customer }) {
  return (
    <>
      <Card>
        <div className="card-heading">
          <div>
            <div className="eyebrow">OBSERVED EQUIPMENT</div>
            <h2>What we have seen calibrated</h2>
            <p>Demo portfolio quantities · not a complete owned inventory</p>
          </div>
          <Layers size={20} />
        </div>
        {c.groups.map((g, i) => (
          <div className="portfolio-group" key={g.name}>
            <span className={`group-symbol color-${i}`}>
              <Layers size={18} />
            </span>
            <div>
              <strong>{g.name}</strong>
              <div className="progress-track">
                <span
                  style={{
                    width:
                      (g.instruments /
                        Math.max(...c.groups.map((g) => g.instruments))) *
                        100 +
                      "%",
                  }}
                />
              </div>
            </div>
            <b>
              {g.instruments}
              <small> instruments</small>
            </b>
          </div>
        ))}
      </Card>
      <Card className="discovery-card">
        <Badge tone="purple">Peer-supported discovery · mock</Badge>
        <h2>A question about {c.peer_opportunity.group.toLowerCase()}</h2>
        <p>
          In this synthetic example,{" "}
          <strong>
            {Math.round(c.peer_opportunity.peer_prevalence * 100)}%
          </strong>{" "}
          of <strong>{c.peer_opportunity.peer_count}</strong> industry peers use
          this service. It is absent from this account’s observed demo
          categories.
        </p>
        <blockquote>
          “Do you use torque equipment, and would calibration support be
          useful?”
        </blockquote>
        <div className="small-note">
          This suggests a question. It does not establish owned equipment,
          competitor use or commercial value.
        </div>
      </Card>
      <Card>
        <div className="card-heading">
          <h2>Date quality & eligibility</h2>
          <Badge>Separate evidence tiers</Badge>
        </div>
        <div className="date-tiers">
          <div>
            <span className="tier-dot green" />
            Recorded upcoming dates<strong>{c.recorded_due}</strong>
          </div>
          <div>
            <span className="tier-dot orange" />
            Inferred upcoming windows<strong>{c.inferred_due}</strong>
          </div>
          <div>
            <span className="tier-dot neutral" />
            Unknown dates<strong>{c.unknown_dates}</strong>
          </div>
          <div>
            <span className="tier-dot purple" />
            Explicit stop flags<strong>{c.stopped}</strong>
          </div>
        </div>
        <p className="small-note">
          Stopped instruments need review before outreach. Unknown dates are not
          automatically assigned a calibration need.
        </p>
      </Card>
    </>
  );
}
function NextStep({ customer: c }: { customer: Customer }) {
  const [owner, setOwner] = useState(c.owner),
    [date, setDate] = useState("2026-10-14"),
    [outcome, setOutcome] = useState("Timing to confirm"),
    [note, setNote] = useState(""),
    [check, setCheck] = useState("Not checked"),
    [saving, setSaving] = useState(false),
    [result, setResult] = useState("");
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setResult("");
    try {
      const receipt = await saveFollowup({
        customer_id: c.id,
        owner,
        due_date: date,
        note:
          note +
          (check === "Not checked"
            ? ""
            : `\nManual current-order check: ${check}`),
        outcome,
      });
      dispatchEvent(receipt);
      setResult("Saved. Your next step is now in Follow-ups.");
    } catch (error) {
      setResult(error instanceof Error ? error.message : "Unable to save");
    } finally {
      setSaving(false);
    }
  }
  function exportBrief() {
    const text = `QUOTATION PREPARATION BRIEF — MOCK WORKSPACE\n\nAccount: ${c.name} (${c.id})\nReference: 30 Sept 2026 — synthetic evidence\nReason: ${c.reason}\nObserved groups: ${c.groups.map((g) => `${g.name} (${g.instruments} demo instruments)`).join(", ")}\nCurrent-order check: ${check} (manual)\nOwner: ${owner}\nNext step: ${note || "Not supplied"}\nRequested follow-up: ${date}\nOutcome: ${outcome}\n\nConfirm: actual instrument identifiers, contact details, service suitability, prices and delivery timing.\nNo live outreach or quotation submitted.`;
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = c.id + "-request-brief.txt";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <>
      <Card className="conversation-card">
        <div className="card-heading">
          <div>
            <div className="eyebrow">MAKE THE CONVERSATION USEFUL</div>
            <h2>Your preparation card</h2>
          </div>
          <Sparkles size={21} />
        </div>
        <div className="brief-section">
          <Badge tone="green">Known in the demo</Badge>
          <p>{c.reason}</p>
        </div>
        <div className="brief-section">
          <Badge tone="orange">Still to confirm</Badge>
          <p>
            Customer timing, equipment ownership, live quotations, contact
            details and service suitability.
          </p>
        </div>
        <div className="brief-section">
          <Badge tone="purple">Questions to ask</Badge>
          <ul>
            <li>Has the next calibration batch or its timing changed?</li>
            <li>
              Which instruments need attention, and is a quotation already being
              prepared?
            </li>
            <li>
              Would support for {c.peer_opportunity.group.toLowerCase()} be
              relevant?
            </li>
          </ul>
        </div>
        <button className="button light" onClick={exportBrief}>
          <ArrowDownToLine size={15} /> Export preparation brief
        </button>
      </Card>
      <Card>
        <div className="card-heading">
          <div>
            <div className="eyebrow">KEEP THE NEXT STEP MOVING</div>
            <h2>Record a follow-up</h2>
            <p>
              Manual demo workflow data, stored separately from the evidence.
            </p>
          </div>
        </div>
        <form onSubmit={save} className="followup-form">
          <div className="form-grid">
            <label>
              Action owner
              <select value={owner} onChange={(e) => setOwner(e.target.value)}>
                <option>Alex Meyer</option>
                <option>Hanna Weber</option>
                <option>Sales team</option>
              </select>
            </label>
            <label>
              Follow-up date
              <input
                type="date"
                required
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
            <label>
              Conversation outcome
              <select
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
              >
                {[
                  "Timing to confirm",
                  "Timing changed",
                  "Need confirmed",
                  "Not applicable",
                  "Equipment retired",
                ].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
            <label>
              Current quotation/order check
              <select value={check} onChange={(e) => setCheck(e.target.value)}>
                <option>Not checked</option>
                <option>Checked: no open request reported</option>
                <option>Quotation or order in progress</option>
              </select>
            </label>
          </div>
          <label>
            Next step or handover note
            <textarea
              value={note}
              required
              maxLength={2000}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What should happen next, and what did the customer confirm?"
              rows={3}
            />
          </label>
          <div className="form-bottom">
            <button className="button dark" type="submit" disabled={saving}>
              {saving ? (
                "Saving…"
              ) : (
                <>
                  <Check size={15} /> Save follow-up
                </>
              )}
            </button>
            <span className="form-result" role="status">
              {result}
            </span>
          </div>
        </form>
      </Card>
    </>
  );
}
