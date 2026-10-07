"use client";
import { create } from "zustand";
import fixture from "../../../../data/mock/workspace.json";
import type {
  ChartArtifact,
  CustomerFilters,
  Page,
  Workspace,
  ChatMessage,
  CustomerTab,
  ChatStatus,
} from "@/types/sales";
interface SalesState {
  data: Workspace;
  filters: CustomerFilters;
  selectedId: string;
  sidebarCollapsed: boolean;
  assistantOpen: boolean;
  assistantExpanded: boolean;
  actionLimit: 5 | 10 | 12;
  customerTab: CustomerTab;
  threadId: string | null;
  chatStatus: ChatStatus | null;
  chatLoading: boolean;
  artifacts: ChartArtifact[];
  requestedPage: Page | null;
  notice: string;
  apiStatus: "connecting" | "connected" | "offline";
  messages: ChatMessage[];
  set: (patch: Partial<Omit<SalesState, "set">>) => void;
}
export const defaultFilters: CustomerFilters = {
  industry: "all",
  segment: "all",
  action: "all",
  query: "",
};
export const useSalesStore = create<SalesState>((set) => ({
  data: fixture as Workspace,
  filters: defaultFilters,
  selectedId: "DEMO-1001",
  sidebarCollapsed: false,
  assistantOpen: false,
  assistantExpanded: false,
  actionLimit: 10,
  customerTab: "activity",
  threadId: null,
  chatStatus: null,
  chatLoading: true,
  artifacts: [],
  requestedPage: null,
  notice: "",
  apiStatus: "connecting",
  messages: [],
  set: (patch) => set(patch),
}));
export const actionLabels = {
  upcoming: "Upcoming need",
  inactivity: "Activity review",
  discovery: "Service discovery",
};
export function filterCustomers(data: Workspace, filters: CustomerFilters) {
  return data.customers.filter(
    (c) =>
      (filters.industry === "all" || c.industry === filters.industry) &&
      (filters.segment === "all" || c.segment === filters.segment) &&
      (filters.action === "all" || c.action === filters.action) &&
      (!filters.query ||
        `${c.name} ${c.id}`
          .toLowerCase()
          .includes(filters.query.toLowerCase())),
  );
}
