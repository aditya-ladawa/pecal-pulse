import type { Metadata } from "./sales-v2";
import type { Followup, PageMetric } from "./sales";
export interface OpportunityFilters {
  industry: string;
  segment: string;
  group: string;
  purpose: "all" | "upcoming" | "inactivity" | "discovery";
  window_days: 30 | 60 | 90;
  include_inferred: boolean;
  include_past_due: boolean;
}
export const defaultOpportunityFilters: OpportunityFilters = {
  industry: "all",
  segment: "all",
  group: "all",
  purpose: "all",
  window_days: 90,
  include_inferred: true,
  include_past_due: false,
};
export interface OpportunityPoint {
  customer_id: string;
  display_name: string;
  industry_id: string;
  industry_label: string;
  segment_id: string | null;
  segment_label: string | null;
  cluster_id: string | null;
  urgency_score: number | null;
  size_score: number | null;
  size_basis: string | null;
  components: Record<string, number | null>;
  due_recorded: number;
  due_inferred: number;
  due_selected_category: number;
  activity_flagged: boolean;
  inactivity_supported: boolean;
  activity_probability: number | null;
  expected_calibrations: number | null;
  forecast_start: string | null;
  forecast_end: string | null;
  priority_score: number;
  reasons: string[];
  reason_types: string[];
  next_action: string;
  readiness: string;
  owner: string | null;
  group_ids: string[];
}
export interface OpportunityResponse {
  metadata: Metadata;
  rule_version: string;
  model_version: string;
  selection_revision: string;
  filters: OpportunityFilters;
  selected_cluster: string | null;
  filter_options: Record<
    "industries" | "segments" | "groups",
    { value: string; label: string }[]
  >;
  matching_count: number;
  selected_count: number;
  unassigned_count: number;
  displayed_count: number;
  points: OpportunityPoint[];
  clusters: {
    id: string;
    label: string;
    color: string;
    urgency: number;
    size: number;
    matching_count: number;
  }[];
  quality: {
    method: string;
    note: string;
    silhouette: number | null;
    seed_agreement: number | null;
    outlier_agreement: number | null;
  };
  metrics: (PageMetric & { caption: string })[];
  recorded_total: number;
  inferred_total: number;
  forecast_supported: number;
  inactivity_supported: number;
  overdue_count: number;
  unassigned_owner_count: number;
  due_followups: Followup[];
  items: OpportunityPoint[];
  limit: number;
  offset: number;
  scenario: {
    estimated_contribution: number | null;
    assumptions: {
      currency: string;
      unit_contribution: number;
      source: string;
    };
    expected_quantity: number | null;
    interpretation: string;
  } | null;
}
export interface CommercialScenario {
  unit_contribution: number;
  source: string;
}
