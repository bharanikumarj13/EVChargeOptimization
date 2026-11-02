import {
  GridGroup,
  GridGroupCreate,
  Station,
  StationCreate,
  Scenario,
  ScenarioCreate,
  ForecastResponse,
  AllocationRunResponse,
  AllocationRunSummary,
  FeedbackResponse,
  OperationalAdjustmentResponse,
  SystemSummaryMetrics,
  HealthResponse,
  IntegrationHealthResponse,
} from '../types/api';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8002';
const CLIENT_TOKEN = (import.meta.env.VITE_OPT_CLIENT_TOKEN || import.meta.env.VITE_API_TOKEN || '').trim();

async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers || {});
  if (CLIENT_TOKEN && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${CLIENT_TOKEN}`);
  }
  return fetch(url, { ...init, headers });
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorDetail = `HTTP Error ${response.status}: ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson.message) errorDetail = errJson.message;
      else if (errJson.detail) {
        errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // Use fallback errorDetail
    }
    throw new Error(errorDetail);
  }
  return response.json();
}

export const api = {
  // System Health
  async getHealth(): Promise<HealthResponse> {
    const res = await authFetch(`${API_BASE_URL}/healthz`);
    return handleResponse<HealthResponse>(res);
  },

  async getIntegrationHealth(): Promise<IntegrationHealthResponse> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/integration/health`);
    return handleResponse<IntegrationHealthResponse>(res);
  },

  // Reporting Summary
  async getSummaryMetrics(): Promise<SystemSummaryMetrics> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/reports/summary`);
    return handleResponse<SystemSummaryMetrics>(res);
  },

  getExportCsvUrl(): string {
    return `${API_BASE_URL}/api/v1/reports/allocations.csv`;
  },

  // Stations
  async getStations(activeOnly = false): Promise<Station[]> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/stations?active_only=${activeOnly}`);
    return handleResponse<Station[]>(res);
  },

  async createStation(station: StationCreate): Promise<Station> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/stations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(station),
    });
    return handleResponse<Station>(res);
  },

  async updateStation(stationId: string, update: Partial<StationCreate>): Promise<Station> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/stations/${stationId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    });
    return handleResponse<Station>(res);
  },

  async deactivateStation(stationId: string): Promise<Station> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/stations/${stationId}/deactivate`, {
      method: 'POST',
    });
    return handleResponse<Station>(res);
  },

  // Grid Groups
  async getGridGroups(): Promise<GridGroup[]> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/grid-groups`);
    return handleResponse<GridGroup[]>(res);
  },

  async createGridGroup(group: GridGroupCreate): Promise<GridGroup> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/grid-groups`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(group),
    });
    return handleResponse<GridGroup>(res);
  },

  async updateGridGroup(groupId: string, update: Partial<GridGroupCreate>): Promise<GridGroup> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/grid-groups/${groupId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    });
    return handleResponse<GridGroup>(res);
  },

  // Scenarios
  async getScenarios(): Promise<Scenario[]> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/scenarios`);
    return handleResponse<Scenario[]>(res);
  },

  async createScenario(scenario: ScenarioCreate): Promise<Scenario> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/scenarios`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(scenario),
    });
    return handleResponse<Scenario>(res);
  },

  async getScenario(scenarioId: string): Promise<Scenario> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/scenarios/${scenarioId}`);
    return handleResponse<Scenario>(res);
  },

  async getScenarioIterations(scenarioId: string): Promise<any[]> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/scenarios/${scenarioId}/iterations`);
    return handleResponse<any[]>(res);
  },

  // Allocations
  async runAllocation(req: {
    scenario_id: string;
    forecast_id: string;
    interval_start: string;
    interval_end: string;
    operational_adjustment_id?: string | null;
  }): Promise<AllocationRunResponse> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/allocations/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse<AllocationRunResponse>(res);
  },

  async getAllocation(allocationId: string): Promise<AllocationRunResponse> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/allocations/${allocationId}`);
    return handleResponse<AllocationRunResponse>(res);
  },

  async getRecentAllocations(limit = 50): Promise<AllocationRunSummary[]> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/allocations?limit=${limit}`);
    return handleResponse<AllocationRunSummary[]>(res);
  },

  async getScenarioAllocations(scenarioId: string, limit = 50): Promise<AllocationRunSummary[]> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/scenarios/${scenarioId}/allocations?limit=${limit}`);
    return handleResponse<AllocationRunSummary[]>(res);
  },

  // Feedback & Adjustments
  async submitFeedback(
    allocationId: string,
    req?: { deferred_fraction?: number; idempotency_key?: string }
  ): Promise<FeedbackResponse> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/allocations/${allocationId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req || {}),
    });
    return handleResponse<FeedbackResponse>(res);
  },

  async getFeedback(feedbackId: string): Promise<FeedbackResponse> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/feedback/${feedbackId}`);
    return handleResponse<FeedbackResponse>(res);
  },

  async getRecentFeedback(limit = 50): Promise<FeedbackResponse[]> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/feedback?limit=${limit}`);
    return handleResponse<FeedbackResponse[]>(res);
  },

  async getOperationalAdjustment(adjustmentId: string): Promise<OperationalAdjustmentResponse> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/operational-adjustments/${adjustmentId}`);
    return handleResponse<OperationalAdjustmentResponse>(res);
  },

  async getRecentOperationalAdjustments(limit = 50): Promise<OperationalAdjustmentResponse[]> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/operational-adjustments?limit=${limit}`);
    return handleResponse<OperationalAdjustmentResponse[]>(res);
  },

  // Forecasts
  async createForecast(req: {
    scenario_id: string;
    station_ids: string[];
    forecast_start: string;
    interval_minutes?: number;
    horizon_intervals?: number;
  }): Promise<{
    contract_version: string;
    forecast_id: string;
    scenario_id: string;
    status: string;
    demand_type: string;
    generated_at: string;
    interval_minutes: number;
    horizon_intervals: number;
    forecast_url: string;
  }> {
    const res = await authFetch(`${API_BASE_URL}/api/v1/forecasts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse(res);
  },

  async getForecast(forecastId: string, scenarioId?: string): Promise<ForecastResponse> {
    const url = scenarioId
      ? `${API_BASE_URL}/api/v1/forecasts/${forecastId}?scenario_id=${scenarioId}`
      : `${API_BASE_URL}/api/v1/forecasts/${forecastId}`;
    const res = await authFetch(url);
    return handleResponse<ForecastResponse>(res);
  },
};
