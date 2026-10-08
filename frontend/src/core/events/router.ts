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
        dashboardOffset: 0,
        opportunitiesLoading: true,
      });
      break;
    case "opportunities.cluster.select":
      s.set({
        opportunityCluster: event.payload.cluster_id,
        dashboardOffset: 0,
        opportunitiesLoading: true,
      });
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
        s.set({ actionLimit: event.payload.value, dashboardOffset: 0 });
      else if (event.payload.control === "customers.view")
        s.set({ customerView: event.payload.value });
      else if (event.payload.control === "customers.offset")
        s.set({
          customerOffset: event.payload.value,
          customerListLoading: true,
        });
      else if (event.payload.control === "dashboard.offset")
        s.set({
          dashboardOffset: event.payload.value,
          opportunitiesLoading: true,
        });
      else if (event.payload.control === "dashboard.display_limit")
        s.set({ opportunityDisplayLimit: event.payload.value });
      else if (event.payload.control === "dashboard.preview")
        s.set({
          opportunityDrawerId: event.payload.value,
          ...(event.payload.value
            ? {
                selectedId: event.payload.value,
                customerTab: "activity" as const,
                v2Detail: null,
              }
            : {}),
        });
      break;
    case "ui.navigate":
      s.set({ requestedPage: event.payload.page });
      break;
    case "customers.filters.set":
      s.set({
        filters: { ...s.filters, ...event.payload },
        customerOffset: 0,
        customerListLoading: true,
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
          v2Detail: null,
        });
      break;
    case "artifact.created":
      // Artifacts belong to the assistant message, not to Dashboard/Insights.
      break;
    case "accounts.assigned":
    case "customer.workflow.updated":
      s.set({
        workflowRevision: s.workflowRevision + 1,
        opportunityRevision: s.opportunityRevision + 1,
        notice:
          event.type === "accounts.assigned"
            ? `${event.payload.customer_ids.length} accounts assigned to ${event.payload.owner}`
            : "Customer next step updated",
      });
      break;
    case "followup.created":
    case "followup.updated":
      s.set({
        opportunityRevision: s.opportunityRevision + 1,
        workflowRevision: s.workflowRevision + 1,
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
