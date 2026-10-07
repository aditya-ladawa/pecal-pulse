export interface Metadata {
  snapshot_id: string;
  reference_date: string;
  mode: "mock" | "historical";
  workflow_today: string;
  modules: Record<string, { status: string; reason: string | null }>;
}
export interface Action {
  customer_id: string;
  primary_type: "upcoming" | "inactivity" | "discovery";
  priority_score: number;
  readiness: string;
  suggested_next_step: string;
  components: Record<string, number | null>;
  reasons: {
    id: string;
    type: string;
    title: string;
    explanation: string;
    quantity: number | null;
    quantity_unit: string;
    unknowns: string[];
    instrument_ids: string[];
  }[];
}
export interface Profile {
  customer_id: string;
  display_name: string;
  industry_id: string | null;
  industry_label: string | null;
  name_source: string;
}
export interface Summary {
  profile: Profile;
  segment_id: string | null;
  primary_action: Action | null;
  recency_months: number | null;
  activity_probability: number | null;
}
export interface CustomerList {
  metadata: Metadata;
  items: Summary[];
  total: number;
  limit: number;
  offset: number;
}
export interface Sectors {
  history: {
    industry_id: string;
    label: string;
    customers: number;
    monthly: { month: string; calibration_events: number }[];
  }[];
  forecasts: {
    industry_id: string;
    method: string;
    forecast_month: string;
    expected: number | null;
    test_mae: Record<string, number | null>;
  }[];
  correlation: {
    labels: string[];
    values: (number | null)[][];
    pair_sample_counts: number[][];
    method: string;
    warnings: string[];
    window_start: string;
    window_end: string;
  } | null;
}
export interface Bootstrap {
  metadata: Metadata;
  filter_options: {
    industries: { value: string; label: string }[];
    segments: { value: string; label: string }[];
    actions: string[];
  };
  kpis: {
    customers: { value: number };
    eligible_requirements: { value: number };
    requirements_by_kind: Record<string, number>;
    open_followups: { value: number };
  };
  actions: Action[];
  due_followups: import("./sales").Followup[];
  sectors: Sectors | null;
}
export interface Support {
  status: string;
  reason: string | null;
  history_months: number;
  active_months: number;
}
export interface Detail {
  metadata: Metadata;
  profile: Profile;
  history: {
    month: string;
    calibration_events: number;
    distinct_instruments: number;
  }[];
  portfolio: {
    group_id: string;
    group_label: string;
    distinct_instruments: number | null;
    calibration_events: number;
    window_start: string;
    window_end: string;
  }[];
  requirements: {
    id: string;
    kind: string;
    instrument_id: string;
    eligibility: string;
    stopped: boolean | null;
    window_start: string | null;
    window_end: string | null;
    method: string;
    unknowns: string[];
  }[];
  prediction: {
    segment_id: string | null;
    activity: {
      probability: number | null;
      window_start: string;
      window_end: string;
      support: Support;
    };
    calibration_volume: {
      expected_total: number | null;
      window_start: string;
      window_end: string;
      method: string;
      support: Support;
      monthly: { month: string; expected: number }[] | null;
    };
    inactivity: {
      flagged: boolean;
      reasons: string[];
      recency_to_cadence: number | null;
    };
  } | null;
  action: Action | null;
  peer_opportunities: {
    group_label: string;
    prevalence: number;
    peer_count: number;
    question: string;
  }[];
  preparation: {
    facts: { text: string }[];
    unknowns: string[];
    questions: string[];
    suggested_next_step: string;
  };
  workflow: {
    checks: {
      quotation_order: string;
      recent_contact: string;
      contact_details: string;
    };
    followups: import("./sales").Followup[];
    suppressions: { reason_id: string; status: string }[];
  };
}
