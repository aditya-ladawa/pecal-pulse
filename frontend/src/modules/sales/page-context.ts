import type { Workspace, PageSnapshot } from "@/types/sales";

// Shared by the rendered dashboard cards and the assistant's send-time context.
export function dashboardSnapshot(data: Workspace): PageSnapshot {
  return {
    page: "dashboard",
    title: "Your next conversation",
    metrics: [
      {
        label: "Customers to review",
        value: data.customers.length,
        unit: "customers",
        scope:
          "All workspace customers; independent of shortlist limit and customer filters",
        definition: "Number of demo accounts available for review.",
      },
      {
        label: "Recorded upcoming needs",
        value: data.customers.reduce((sum, c) => sum + c.recorded_due, 0),
        unit: "instruments",
        scope:
          "All workspace customers; next 30 days; independent of shortlist limit and customer filters",
        definition:
          "Sum of recorded_due across all accounts: instruments with recorded calibration due dates in the demo upcoming window. Excludes inferred dates. This is a synthetic requirement count, not orders, quotations, revenue, or a forecast.",
      },
      {
        label: "Follow-ups needing attention",
        value: data.followups.filter(
          (f) => f.status === "open" && f.due_date <= data.demo_today,
        ).length,
        unit: "follow-ups",
        scope: `Open tasks due or overdue on demo date ${data.demo_today}`,
        definition:
          "Open follow-ups whose due date is on or before the demo date.",
      },
      {
        label: "Activity review signals",
        value: data.customers.filter((c) => c.action === "inactivity").length,
        unit: "customers",
        scope: "All workspace customers",
        definition:
          "Accounts flagged with unusual activity gaps to investigate; not confirmed churn.",
      },
    ],
  };
}
