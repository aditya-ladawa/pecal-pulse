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
import type { Bootstrap, CustomerList, Detail } from "@/types/sales-v2";
import {
  defaultOpportunityFilters,
  type OpportunityFilters,
  type OpportunityResponse,
  type CommercialScenario,
} from "@/types/opportunities";
interface SalesState {
  assistantLanguage: "en" | "de";
  voiceBusy: boolean;
  assistantSide: "left" | "right";
  voiceInputPending: boolean;
  voiceResponse: {
    id: string;
    text: string;
    kind?: "progress" | "final" | "error";
  } | null;
  voiceResetRevision: number;
  agentFeedback: {
    id: string;
    target: "navigation" | "filters" | "customer" | "controls" | "workflow";
    label: string;
  } | null;
  customerOffset: number;
  dashboardOffset: number;
  customerListLoading: boolean;
  opportunitiesLoading: boolean;
  workflowRevision: number;
  opportunities: OpportunityResponse | null;
  opportunityFilters: OpportunityFilters;
  opportunityCluster: string | null;
  opportunityDisplayLimit: number;
  opportunityDrawerId: string | null;
  opportunityRevision: number;
  commercialScenario: CommercialScenario | null;
  customerView: "accounts" | "follow-ups";
  v2: Bootstrap | null;
  v2List: CustomerList | null;
  v2Detail: Detail | null;
  v2Error: string;
  v2Loading: boolean;
  data: Workspace;
  filters: CustomerFilters;
  selectedId: string;
  sidebarCollapsed: boolean;
  assistantOpen: boolean;
  assistantExpanded: boolean;
  actionLimit: 5 | 10 | 12;
  customerTab: CustomerTab;
  customerActivityView: "monthly" | "quarter";
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
  retention: "all",
  query: "",
};
export const useSalesStore = create<SalesState>((set) => ({
  assistantLanguage: "en",
  voiceBusy: false,
  assistantSide: "right",
  voiceInputPending: false,
  voiceResponse: null,
  voiceResetRevision: 0,
  agentFeedback: null,
  customerOffset: 0,
  dashboardOffset: 0,
  customerListLoading: false,
  opportunitiesLoading: false,
  workflowRevision: 0,
  opportunities: null,
  opportunityFilters: defaultOpportunityFilters,
  opportunityCluster: null,
  opportunityDisplayLimit: 200,
  opportunityDrawerId: null,
  opportunityRevision: 0,
  commercialScenario: null,
  customerView: "accounts",
  v2: null,
  v2List: null,
  v2Detail: null,
  v2Error: "",
  v2Loading: true,
  data: fixture as Workspace,
  filters: defaultFilters,
  selectedId: "DEMO-1001",
  sidebarCollapsed: false,
  assistantOpen: false,
  assistantExpanded: false,
  actionLimit: 10,
  customerTab: "activity",
  customerActivityView: "monthly",
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
