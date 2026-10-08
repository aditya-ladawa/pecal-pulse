import type {
  TextMessagePart,
  ReasoningMessagePart,
  ToolCallMessagePart,
  ThreadMessageLike,
} from "@assistant-ui/react";
export type Page = "dashboard" | "customers" | "follow-ups" | "insights";
export type ActionType = "upcoming" | "inactivity" | "discovery";
export type Segment = "Frequent" | "Intermittent" | "Occasional";
export type CustomerFilters = {
  industry: string;
  segment: string;
  action: ActionType | "all";
  retention: "all" | "lower" | "moderate" | "higher";
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
  email_draft?: {
    subject: string;
    body: string;
    language: "en" | "de";
    status: "draft";
    snapshot_id: string;
    reference_date: string;
    reason_ids: string[];
    review_notes: string[];
  } | null;
  request_key?: string | null;
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
  kind: "bar" | "line" | "heatmap";
  labels: string[];
  datasets: { name: string; values: (number | null)[] }[];
  unit: "calibrations" | "instruments" | "customers" | "correlation";
  source: "mock" | "historical";
}
export type UiCommand =
  | {
      type: "opportunities.filters.set";
      payload: Partial<import("./opportunities").OpportunityFilters>;
    }
  | {
      type: "opportunities.cluster.select";
      payload: { cluster_id: string | null };
    }
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
            activity_view?: "monthly" | "quarter";
          }
        | { control: "dashboard.action_limit"; value: 5 | 10 | 12 }
        | { control: "customers.view"; value: "accounts" | "follow-ups" }
        | { control: "customers.offset" | "dashboard.offset"; value: number }
        | { control: "dashboard.display_limit"; value: 100 | 200 | 500 | 1000 }
        | { control: "dashboard.preview"; value: string | null };
    };
export type DomainEvent =
  | {
      type: "followup.created" | "followup.updated";
      payload: Followup;
    }
  | {
      type: "accounts.assigned";
      payload: { customer_ids: string[]; owner: string };
    }
  | {
      type: "customer.workflow.updated";
      payload: {
        customer_id: string;
        workflow: import("./sales-v2").Detail["workflow"];
        action: import("./sales-v2").Action | null;
        suppressed_requirement_ids: string[];
      };
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
  value: number | null;
  unit: string;
  scope: string;
  definition: string;
}
export interface PageSnapshot {
  page: Page;
  title: string;
  metrics: PageMetric[];
  sections?: string[];
  visible_rows?: Record<string, unknown>[];
  loading?: boolean;
}
export interface WorkspaceContext {
  language?: "en" | "de";
  opportunity_filters?: import("./opportunities").OpportunityFilters;
  opportunity_cluster?: string | null;
  opportunity_model_version?: string;
  opportunity_selection_revision?: string;
  commercial_scenario?: import("./opportunities").CommercialScenario | null;
  customer_view?: "accounts" | "follow-ups";
  customer_offset?: number;
  dashboard_offset?: number;
  opportunity_drawer_id?: string | null;
  opportunity_display_limit?: number;
  current_date?: string;

  page: Page;
  customer_id: string | null;
  filters: CustomerFilters;
  reference_date: string;
  visible_customer_ids: string[];
  action_limit: 5 | 10 | 12;
  customer_tab: CustomerTab;
  customer_activity_view: "monthly" | "quarter";
  artifact_ids: string[];
  page_snapshot?: PageSnapshot;
  snapshot_id?: string;
}
export interface ChatStatus {
  mode: "agent";
  configured: boolean;
  model: string;
  data_mode: "mock" | "historical";
  snapshot_id?: string;
  checkpointing: "sqlite";
}
