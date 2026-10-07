"use client";
import { useSalesStore } from "@/modules/sales/store";
import type { EventEnvelope, UiCommand } from "@/types/sales";
/** The single UI update boundary, used by human controls and agent receipts. */
export function dispatchEvent(event: EventEnvelope) {
  const s = useSalesStore.getState();
  switch (event.type) {
    case "opportunities.filters.set":
      s.set({
        opportunityFilters: { ...s.opportunityFilters, ...event.payload },
        opportunityCluster: null,
      });
      break;
    case "opportunities.cluster.select":
      s.set({ opportunityCluster: event.payload.cluster_id });
      break;

    case "ui.control.set":
      if (event.payload.control === "customers.tab")
        s.set({
          customerTab: event.payload.value,
          ...(event.payload.activity_view
            ? { customerActivityView: event.payload.activity_view }
            : {}),
        });
      else if (event.payload.control === "dashboard.action_limit")
        s.set({ actionLimit: event.payload.value });
      break;
    case "ui.navigate":
      s.set({ requestedPage: event.payload.page });
      break;
    case "customers.filters.set":
      s.set({
        filters: { ...s.filters, ...event.payload },
        notice: "Customer filters updated",
      });
      break;
    case "customers.select":
      if (
        s.v2 ||
        s.data.customers.some((c) => c.id === event.payload.customer_id)
      )
        s.set({
          selectedId: event.payload.customer_id,
          customerView: "accounts",
        });
      break;
    case "artifact.created":
      s.set({
        artifacts: [
          ...s.artifacts.filter((a) => a.id !== event.payload.id),
          event.payload,
        ],
        notice: "Chart added to your workspace",
      });
      break;
    case "followup.created":
    case "followup.updated":
      s.set({
        opportunityRevision: s.opportunityRevision + 1,
        data: {
          ...s.data,
          followups: [
            ...s.data.followups.filter((f) => f.id !== event.payload.id),
            event.payload,
          ],
        },
        notice:
          event.type === "followup.created"
            ? "Follow-up saved"
            : "Follow-up updated",
      });
      break;
  }
}
export function dispatchCommand(command: UiCommand) {
  dispatchEvent({
    ...command,
    id: crypto.randomUUID(),
    timestamp: Date.now(),
    source: { type: "user" },
  });
}
export function openCustomer(id: string) {
  dispatchCommand({
    type: "customers.filters.set",
    payload: { industry: "all", segment: "all", action: "all", query: "" },
  });
  dispatchCommand({ type: "customers.select", payload: { customer_id: id } });
  dispatchCommand({ type: "ui.navigate", payload: { page: "customers" } });
}
