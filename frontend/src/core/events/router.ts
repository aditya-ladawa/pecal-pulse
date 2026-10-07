"use client";
import { useSalesStore } from "@/modules/sales/store";
import type { EventEnvelope, UiCommand } from "@/types/sales";
/** The single UI update boundary, used by human controls and agent receipts. */
export function dispatchEvent(event: EventEnvelope) {
  const s = useSalesStore.getState();
  switch (event.type) {
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
      if (s.data.customers.some((c) => c.id === event.payload.customer_id))
        s.set({ selectedId: event.payload.customer_id });
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
