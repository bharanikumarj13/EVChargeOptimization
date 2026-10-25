export interface GridGroup {
  grid_group_id: string;
  grid_group_name: string;
  grid_limit_kw: number;
  other_load_kw: number;
  residual_capacity_kw: number;
  created_at: string;
  updated_at: string;
}

export interface GridGroupCreate {
  grid_group_id: string;
  grid_group_name: string;
  grid_limit_kw: number;
  other_load_kw: number;
}

export interface Station {
  station_id: string;
  station_name: string;
  charger_count: number;
  available_chargers: number;
  charger_power_kw_per_charger: number;
  station_power_limit_kw: number;
  avg_session_minutes: number;
  grid_group_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface StationCreate {
  station_id: string;
  station_name: string;
  charger_count: number;
  available_chargers: number;
  charger_power_kw_per_charger: number;
  station_power_limit_kw: number;
  avg_session_minutes: number;
  grid_group_id: string;
  is_active: boolean;
}

export interface Scenario {
  scenario_id: string;
  name: string;
  description?: string;
  selected_forecast_id: string;
  planning_horizon_intervals: number;
  provider_mode: string;
  created_at: string;
  updated_at: string;
  allocation_count?: number;
}

export interface ScenarioCreate {
  scenario_id: string;
  name: string;
  description?: string;
  selected_forecast_id: string;
  planning_horizon_intervals: number;
  provider_mode: string;
}

export interface ForecastIntervalItem {
  forecast_id: string;
  scenario_id?: string;
  station_id: string;
  interval_start: string;
  interval_end: string;
  interval_minutes: number;
  predicted_arrivals: number;
  predicted_energy_kwh: number;
  model_version: string;
  generated_at: string;
}

export interface ForecastResponse {
  forecast_id: string;
  scenario_id?: string;
  model_version: string;
  generated_at: string;
  intervals: ForecastIntervalItem[];
  interval_count: number;
  station_ids: string[];
}

export interface StationAllocationResult {
  station_id: string;
  station_name?: string;
  predicted_arrivals: number;
  predicted_energy_kwh: number;
  estimated_served: number;
  estimated_unserved: number;
  allocated_power_kw: number;
  estimated_served_energy_kwh: number;
  estimated_unserved_energy_kwh: number;
  estimated_wait_minutes?: number | null;
  charger_utilization_pct: number;
  warnings: string[];
}

export interface AllocationRunResponse {
  allocation_id: string;
  scenario_id: string;
  forecast_id: string;
  operational_adjustment_id?: string | null;
  interval_start: string;
  interval_end: string;
  status: string;
  outcome_kind: string;
  algorithm_version: string;
  objective_description: string;
  constraint_validation_passed: boolean;
  warnings: string[];
  results: StationAllocationResult[];
  created_at: string;
}

export interface AllocationRunSummary {
  allocation_id: string;
  scenario_id: string;
  forecast_id: string;
  operational_adjustment_id?: string | null;
  interval_start: string;
  interval_end: string;
  status: string;
  outcome_kind: string;
  constraint_validation_passed: boolean;
  total_arrivals: number;
  total_served: number;
  total_unserved: number;
  total_allocated_power_kw: number;
  avg_utilization_pct: number;
  created_at: string;
}

export interface StationFeedbackOutcome {
  station_id: string;
  predicted_arrivals: number;
  estimated_served: number;
  estimated_unserved: number;
  allocated_power_kw: number;
  estimated_wait_minutes?: number | null;
  charger_utilization_pct: number;
  deferred_vehicles: number;
  deferred_energy_kwh: number;
}

export interface FeedbackResponse {
  feedback_id: string;
  scenario_id: string;
  forecast_id: string;
  allocation_id: string;
  outcome_kind: string;
  interval_start: string;
  interval_end: string;
  station_outcomes: StationFeedbackOutcome[];
  deferred_fraction: number;
  submission_status: string;
  idempotency_key: string;
  retry_count: number;
  error_details?: string | null;
  operational_adjustment_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface StationOperationalAdjustmentItem {
  station_id: string;
  original_predicted_arrivals: number;
  original_predicted_energy_kwh: number;
  deferred_vehicles_added: number;
  deferred_energy_kwh_added: number;
  adjusted_predicted_arrivals: number;
  adjusted_predicted_energy_kwh: number;
}

export interface OperationalAdjustmentResponse {
  operational_adjustment_id: string;
  source_feedback_id: string;
  parent_forecast_id: string;
  target_interval_start: string;
  target_interval_end: string;
  station_adjustments: StationOperationalAdjustmentItem[];
  calculation_assumptions: Record<string, any>;
  created_at: string;
}

export interface SystemSummaryMetrics {
  total_stations: number;
  active_stations: number;
  total_installed_chargers: number;
  total_available_chargers: number;
  total_grid_limit_kw: number;
  total_residual_grid_kw: number;
  total_optimization_runs: number;
  total_predicted_arrivals: number;
  total_estimated_served: number;
  total_estimated_unserved: number;
  total_allocated_power_kw: number;
  avg_charger_utilization_pct: number;
  latest_allocation_id?: string | null;
  latest_run_status?: string | null;
  recent_feedback_count: number;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  database: string;
  environment: string;
}

export interface IntegrationHealthResponse {
  status: string;
  provider_mode: string;
  is_mock: boolean;
  configured_api_base_url: string;
  last_successful_request?: string | null;
  feedback_delivery_status: string;
  recent_errors: string[];
  service_version: string;
  environment: string;
}
