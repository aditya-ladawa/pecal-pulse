"use client";
import { useState } from "react";
import {
  ArrowUpRight,
  CalendarDays,
  Check,
  Clock3,
  RotateCcw,
  ListTodo,
} from "lucide-react";
import Link from "next/link";
import { useSalesStore } from "./store";
import { setFollowupStatus } from "./api";
import { dispatchEvent, openCustomer } from "@/core/events/router";
import { Badge, Card } from "@/components/ui/Primitives";
export function Followups() {
  const data = useSalesStore((s) => s.data),
    [filter, setFilter] = useState("open"),
    [error, setError] = useState(""),
    [pending, setPending] = useState<string | null>(null);
  const tasks = data.followups
    .filter((f) => filter === "all" || f.status === filter)
    .sort((a, b) => a.due_date.localeCompare(b.due_date));
  async function update(id: string, status: "open" | "done") {
    setPending(id);
    setError("");
    try {
      dispatchEvent(await setFollowupStatus(id, status));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update");
    } finally {
      setPending(null);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">A CONVERSATION IS JUST THE START</div>
          <h1>
            Keep the next step moving<span className="heading-dot">.</span>
          </h1>
          <p>Owners, agreed dates and context, all in one place.</p>
        </div>
        <Link className="button dark" href="/customers">
          Prepare an action <ArrowUpRight size={16} />
        </Link>
      </div>
      <div className="followup-summary">
        <span className="summary-icon">
          <ListTodo size={22} />
        </span>
        <div>
          <strong>
            {data.followups.filter((f) => f.status === "open").length} open
            actions
          </strong>
          <p>
            {
              data.followups.filter(
                (f) => f.status === "open" && f.due_date < data.demo_today,
              ).length
            }{" "}
            overdue · reference day 07 Oct 2026
          </p>
        </div>
        <Badge>Local demo workflow</Badge>
      </div>
      <div className="task-toolbar">
        <div
          className="pill-tabs"
          role="group"
          aria-label="Follow-up status filter"
        >
          {["open", "done", "all"].map((s) => (
            <button
              key={s}
              className={filter === s ? "active" : ""}
              onClick={() => setFilter(s)}
            >
              {s === "open"
                ? "To do"
                : s === "done"
                  ? "Completed"
                  : "All actions"}
            </button>
          ))}
        </div>
        <span>Manual changes are saved in the local backend.</span>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      <div className="task-list">
        {tasks.map((f) => {
          const overdue = f.status === "open" && f.due_date < data.demo_today;
          return (
            <Card
              key={f.id}
              className={`task-card ${f.status === "done" ? "done" : ""}`}
            >
              <button
                className="task-check"
                disabled={pending === f.id}
                aria-label={`${f.status === "done" ? "Reopen" : "Complete"} follow-up for ${f.customer_name}`}
                onClick={() =>
                  update(f.id, f.status === "done" ? "open" : "done")
                }
              >
                {f.status === "done" ? <Check size={18} /> : <span />}
              </button>
              <div className="task-content">
                <div className="task-title">
                  <button onClick={() => openCustomer(f.customer_id)}>
                    {f.customer_name}
                    <ArrowUpRight size={14} />
                  </button>
                  <Badge
                    tone={
                      overdue
                        ? "orange"
                        : f.status === "done"
                          ? "green"
                          : "neutral"
                    }
                  >
                    {f.status === "done"
                      ? "Completed"
                      : overdue
                        ? "Overdue"
                        : f.due_date === data.demo_today
                          ? "Due today"
                          : "Upcoming"}
                  </Badge>
                </div>
                <p>{f.note}</p>
                <div className="task-meta">
                  <span>
                    <CalendarDays size={13} />
                    {new Date(f.due_date + "T12:00:00").toLocaleDateString(
                      "en-GB",
                      { day: "numeric", month: "short", year: "numeric" },
                    )}
                  </span>
                  <span>
                    <span className="mini-avatar">
                      {f.owner
                        .split(" ")
                        .map((s) => s[0])
                        .join("")}
                    </span>
                    {f.owner}
                  </span>
                  <span>{f.outcome}</span>
                  <span className="muted">
                    {f.source === "manual" ? "Manually entered" : "Seeded mock"}
                  </span>
                </div>
              </div>
              <button
                className="icon-button"
                onClick={() => openCustomer(f.customer_id)}
                aria-label={`Open account ${f.customer_name}`}
              >
                <ArrowUpRight size={19} />
              </button>
            </Card>
          );
        })}
        {!tasks.length && (
          <Card className="empty-state">
            <Clock3 size={32} />
            <h2>
              {filter === "done"
                ? "No completed actions yet"
                : "A clear action list."}
            </h2>
            <p>
              {filter === "done"
                ? "Complete an action to see it here."
                : "Add a follow-up from a customer’s conversation workspace."}
            </p>
            <button className="button light" onClick={() => setFilter("all")}>
              <RotateCcw size={15} /> Show all actions
            </button>
          </Card>
        )}
      </div>
    </>
  );
}
