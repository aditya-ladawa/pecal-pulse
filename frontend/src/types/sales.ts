import type {
  TextMessagePart,
  ReasoningMessagePart,
  ToolCallMessagePart,
  ThreadMessageLike,
} from "@assistant-ui/react";
export type Page = "dashboard" | "customers" | "follow-ups";
export type ActionType = "upcoming" | "inactivity" | "discovery";
export type Segment = "Frequent" | "Intermittent" | "Occasional";
export type CustomerFilters = {
  industry: string;
  segment: Segment | "all";
  action: ActionType | "all";
  query: string;
};
export interface Customer {
  id: string;
  name: string;
  initials: string;
  industry: string;
  segment: Segment;
  action: ActionType;
  priority: number;
  return_probability: number;
  recency_months: number;
  cadence_months: number;
  recorded_due: number;
  inferred_due: number;
  unknown_dates: number;
  stopped: number;
  reason: string;
  window: string;
  owner: string;
  groups: { name: string; instruments: number }[];
  months: string[];
  activity: number[];
  forecast: number[];
  forecast_low: number[];
  forecast_high: number[];
  peer_opportunity: {
    group: string;
    peer_prevalence: number;
    peer_count: number;
  };
}
export interface Followup {
  id: string;
  customer_id: string;
  customer_name: string;
  owner: string;
  due_date: string;
  note: string;
  outcome: string;
  status: "open" | "done";
  source: "mock" | "manual";
}
export interface Workspace {
  mode: "mock";
  reference_date: string;
  demo_today: string;
  customers: Customer[];
  sector_labels: string[];
  sector_correlation: number[][];
  followups: Followup[];
}
export interface ChartArtifact {
  id: string;
  title: string;
  kind: "bar" | "line";
  labels: string[];
  datasets: { name: string; values: number[] }[];
  unit: "calibrations" | "instruments" | "customers";
  source: "mock";
}
export type UiCommand =
  | { type: "ui.navigate"; payload: { page: Page } }
  | { type: "customers.filters.set"; payload: Partial<CustomerFilters> }
  | { type: "customers.select"; payload: { customer_id: string } }
  | { type: "artifact.created"; payload: ChartArtifact }
  | {
      type: "ui.control.set";
      payload:
        | {
            control: "customers.tab";
            value: "activity" | "portfolio" | "next-step";
          }
        | { control: "dashboard.action_limit"; value: 5 | 10 | 12 };
    };
export type DomainEvent = {
  type: "followup.created" | "followup.updated";
  payload: Followup;
};
export type EventEnvelope = (UiCommand | DomainEvent) & {
  id: string;
  timestamp: number;
  source: { type: "user" | "agent" | "backend" | "frontend" };
};
export type ChatPart =
  | TextMessagePart
  | ReasoningMessagePart
  | ToolCallMessagePart;
export interface ChatReply {
  message_id?: string;
  content?: ChatPart[];
  message: string;
  mode: "scripted_mock" | "agent";
  thread_id: string;
  events: EventEnvelope[];
  artifacts: ChartArtifact[];
}
export interface ChatMessage {
  content?: ChatPart[];
  status?: ThreadMessageLike["status"];
  id: string;
  role: "user" | "assistant";
  text: string;
  artifacts?: ChartArtifact[];
  actions?: string[];
}

export type CustomerTab = "activity" | "portfolio" | "next-step";
export interface PageMetric {
  label: string;
  value: number;
  unit: string;
  scope: string;
  definition: string;
}
export interface PageSnapshot {
  page: Page;
  title: string;
  metrics: PageMetric[];
}
export interface WorkspaceContext {
  page: Page;
  customer_id: string | null;
  filters: CustomerFilters;
  reference_date: string;
  visible_customer_ids: string[];
  action_limit: 5 | 10 | 12;
  customer_tab: CustomerTab;
  artifact_ids: string[];
  page_snapshot?: PageSnapshot;
}
export interface ChatStatus {
  mode: "agent";
  configured: boolean;
  model: string;
  data_mode: "mock";
  checkpointing: "sqlite";
}
