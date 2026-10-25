import React, { useEffect, useState } from 'react';
import { api, API_BASE_URL } from '../services/api';
import { HealthResponse, IntegrationHealthResponse } from '../types/api';
import { StatusBadge } from '../components/StatusBadge';
import {
  Activity,
  Server,
  ShieldAlert,
  RefreshCw,
  Lock,
  ExternalLink,
} from 'lucide-react';

export const IntegrationHealthPage: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [integration, setIntegration] = useState<IntegrationHealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const checkHealth = async () => {
    try {
      setLoading(true);
      setError(null);
      const [healthData, integData] = await Promise.all([
        api.getHealth(),
        api.getIntegrationHealth(),
      ]);
      setHealth(healthData);
      setIntegration(integData);
    } catch (err: any) {
      setError(err.message || 'Health check failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkHealth();
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
        <RefreshCw className="w-7 h-7 animate-spin text-emerald-400" />
        <p className="text-sm font-medium">Checking integration interfaces and telemetry...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h2 className="text-2xl font-bold text-slate-100 tracking-tight">System & Integration Health</h2>
          <p className="text-sm text-slate-400 mt-1">
            Status of backend services, database persistence, and the EVCharge-Predict forecast adapter interface.
          </p>
        </div>
        <button
          onClick={checkHealth}
          className="flex items-center gap-2 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-xs font-semibold text-slate-300 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Re-test Health
        </button>
      </div>

      {error && (
        <div className="bg-rose-950/40 border border-rose-800/60 rounded-xl p-4 text-rose-300 text-sm flex items-center gap-3">
          <ShieldAlert className="w-5 h-5 text-rose-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Component Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Card 1: Backend & Database */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Server className="w-5 h-5 text-emerald-400" />
              <h3 className="font-semibold text-slate-100 text-sm">EVCharge-Opt Backend</h3>
            </div>
            <StatusBadge status={health?.status || 'unknown'} />
          </div>

          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between py-2 border-b border-slate-800/60">
              <span className="text-slate-400">Service Version</span>
              <span className="font-mono text-slate-200">{health?.version || '0.1.0'}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-800/60">
              <span className="text-slate-400">Runtime Environment</span>
              <span className="text-slate-200 capitalize">{health?.environment || 'development'}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-800/60">
              <span className="text-slate-400">Database Connection</span>
              <span className="font-semibold text-emerald-400 capitalize">{health?.database || 'healthy'}</span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-slate-400">API Documentation</span>
              <a
                href={`${API_BASE_URL}/docs`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
              >
                Open Swagger UI
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>
        </div>

        {/* Card 2: Predictor Adapter */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Activity className="w-5 h-5 text-emerald-400" />
              <h3 className="font-semibold text-slate-100 text-sm">Forecast Provider Adapter</h3>
            </div>
            <StatusBadge status={integration?.status || 'unknown'} />
          </div>

          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between py-2 border-b border-slate-800/60">
              <span className="text-slate-400">Provider Operating Mode</span>
              <span className="font-mono font-bold text-emerald-400 uppercase">
                {integration?.provider_mode} MODE
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-800/60">
              <span className="text-slate-400">Offline Mock Simulation</span>
              <span className="text-slate-200 font-medium">
                {integration?.is_mock ? 'Enabled (Deterministic fixtures)' : 'Disabled (Live HTTP)'}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-slate-800/60">
              <span className="text-slate-400">Partner Base URL</span>
              <span className="font-mono text-slate-300 truncate max-w-[200px]">
                {integration?.configured_api_base_url || 'N/A (Mock Mode)'}
              </span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-slate-400">Last Telemetry / Request</span>
              <span className="font-mono text-slate-300">
                {integration?.last_successful_request
                  ? new Date(integration.last_successful_request).toLocaleTimeString()
                  : 'Ready'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Secret Redaction & Security Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-3">
        <div className="flex items-center gap-2.5">
          <Lock className="w-4 h-4 text-emerald-400" />
          <h3 className="font-semibold text-slate-100 text-sm">Security & Secret Redaction</h3>
        </div>
        <p className="text-xs text-slate-400 leading-relaxed">
          In compliance with project safety guidelines, no credentials, database connection strings, or service tokens are
          ever surfaced to the frontend browser or health telemetry. The predictor service token (<code className="text-slate-300 font-mono">PREDICT_SERVICE_TOKEN</code>)
          is managed strictly server-side inside FastAPI environment memory.
        </p>
      </div>
    </div>
  );
};
