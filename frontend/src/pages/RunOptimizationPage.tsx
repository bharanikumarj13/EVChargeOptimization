import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../services/api';
import { Scenario, ForecastResponse, OperationalAdjustmentResponse, AllocationRunResponse } from '../types/api';
import { StatusBadge } from '../components/StatusBadge';
import {
  Play,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  RefreshCw,
  Sliders,
} from 'lucide-react';

export const RunOptimizationPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('SCN-001');
  const [forecastId, setForecastId] = useState<string>('FC-001');
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [selectedIntervalIndex, setSelectedIntervalIndex] = useState<number>(0);
  const [adjustments, setAdjustments] = useState<OperationalAdjustmentResponse[]>([]);
  const [selectedAdjustmentId, setSelectedAdjustmentId] = useState<string>(() => searchParams.get('adjustment_id') || '');

  const [executing, setExecuting] = useState<boolean>(false);
  const [lastResult, setLastResult] = useState<AllocationRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingInitial, setLoadingInitial] = useState<boolean>(true);

  // Sync adjustment_id from URL query params whenever it changes
  useEffect(() => {
    const queryAdjustmentId = searchParams.get('adjustment_id');
    if (queryAdjustmentId) {
      setSelectedAdjustmentId(queryAdjustmentId);
    }
  }, [searchParams]);

  // Load scenarios and adjustments
  useEffect(() => {
    async function init() {
      try {
        setLoadingInitial(true);
        const [scenariosData, adjustmentsData] = await Promise.all([
          api.getScenarios(),
          api.getRecentOperationalAdjustments(20),
        ]);
        setScenarios(scenariosData);
        if (scenariosData.length > 0) {
          setSelectedScenarioId(scenariosData[0].scenario_id);
          setForecastId(scenariosData[0].selected_forecast_id);
        }
        setAdjustments(adjustmentsData);
      } catch (err: any) {
        setError(err.message || 'Failed loading scenarios');
      } finally {
        setLoadingInitial(false);
      }
    }
    init();
  }, []);

  // Fetch forecast intervals whenever forecastId changes
  useEffect(() => {
    if (!forecastId) return;
    api
      .getForecast(forecastId)
      .then((fc) => {
        setForecast(fc);
        setSelectedIntervalIndex(0);
      })
      .catch((err) => {
        setError(`Unable to load forecast '${forecastId}': ${err.message}`);
      });
  }, [forecastId]);

  // Group unique intervals for distinct planning interval selection
  const uniqueIntervals: { start: string; end: string }[] = useMemo(() => {
    if (!forecast || !forecast.intervals) return [];
    const seen = new Set<string>();
    const distinct: { start: string; end: string }[] = [];
    for (const item of forecast.intervals) {
      if (!seen.has(item.interval_start)) {
        seen.add(item.interval_start);
        distinct.push({ start: item.interval_start, end: item.interval_end });
      }
    }
    return distinct;
  }, [forecast]);

  const handleRunOptimization = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!forecast || uniqueIntervals.length === 0) {
      setError('No valid forecast intervals available to optimize.');
      return;
    }

    try {
      setExecuting(true);
      setError(null);
      setLastResult(null);

      // Selected interval boundaries from distinct interval list
      const selectedInterval = uniqueIntervals[selectedIntervalIndex] || uniqueIntervals[0];
      if (!selectedInterval) {
        setError('No valid planning interval selected.');
        return;
      }

      const payload = {
        scenario_id: selectedScenarioId,
        forecast_id: forecastId,
        interval_start: selectedInterval.start,
        interval_end: selectedInterval.end,
        operational_adjustment_id: selectedAdjustmentId ? selectedAdjustmentId : null,
      };

      const result = await api.runAllocation(payload);
      setLastResult(result);
    } catch (err: any) {
      setError(err.message || 'Optimization execution failed.');
    } finally {
      setExecuting(false);
    }
  };

  if (loadingInitial) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
        <RefreshCw className="w-7 h-7 animate-spin text-emerald-400" />
        <p className="text-sm font-medium">Loading optimization parameters and scenarios...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-slate-100 tracking-tight">Execute Optimization</h2>
        <p className="text-sm text-slate-400 mt-1">
          Calculate feasible charging resource allocations under station hardware limits and shared substation grid capacities.
        </p>
      </div>

      {error && (
        <div className="bg-rose-950/40 border border-rose-800/60 rounded-xl p-4 text-rose-300 text-sm flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Execution Error: </span>
            {error}
          </div>
        </div>
      )}

      {/* Main Execution Form */}
      <form onSubmit={handleRunOptimization} className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Scenario Selection */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
              Scenario Selection
            </label>
            <select
              value={selectedScenarioId}
              onChange={(e) => {
                setSelectedScenarioId(e.target.value);
                const match = scenarios.find((s) => s.scenario_id === e.target.value);
                if (match) setForecastId(match.selected_forecast_id);
              }}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-emerald-500 font-mono"
            >
              {scenarios.map((s) => (
                <option key={s.scenario_id} value={s.scenario_id}>
                  {s.scenario_id} — {s.name}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-slate-400 mt-1.5">
              Select an operational scenario configured in the system.
            </p>
          </div>

          {/* Forecast Selection */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
              Forecast Dataset Identifier
            </label>
            <input
              type="text"
              value={forecastId}
              onChange={(e) => setForecastId(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-emerald-500 font-mono"
              placeholder="e.g. FC-001, FC-002"
              required
            />
            <p className="text-[11px] text-slate-400 mt-1.5">
              Deterministic 6-interval demand forecast served by the forecast provider adapter.
            </p>
          </div>
        </div>

        {/* Planning Interval Selector */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Target Planning Interval
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
            {uniqueIntervals.map((interval, idx) => {
              const startFmt = new Date(interval.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
              const endFmt = new Date(interval.end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
              const isSelected = selectedIntervalIndex === idx;

              return (
                <button
                  type="button"
                  key={interval.start}
                  onClick={() => setSelectedIntervalIndex(idx)}
                  className={`p-3 rounded-lg border text-center transition-all ${
                    isSelected
                      ? 'bg-emerald-500/20 border-emerald-500 text-emerald-300 font-semibold shadow-sm'
                      : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                  }`}
                >
                  <div className="text-[10px] uppercase tracking-wider opacity-70">Interval #{idx + 1}</div>
                  <div className="text-xs font-mono font-medium mt-0.5">
                    {startFmt} - {endFmt}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Demand Basis: Baseline vs Feedback-Adjusted */}
        <div className="p-4 bg-slate-950/80 border border-slate-800/80 rounded-xl space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sliders className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Demand Basis & Lineage Control
              </span>
            </div>
            {selectedAdjustmentId ? (
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">
                Feedback-Adjusted Mode
              </span>
            ) : (
              <span className="text-xs px-2 py-0.5 rounded-full bg-sky-500/20 text-sky-300 border border-sky-500/30">
                Baseline Forecast Mode
              </span>
            )}
          </div>

          <div className="space-y-2">
            <select
              value={selectedAdjustmentId}
              onChange={(e) => setSelectedAdjustmentId(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
            >
              <option value="">Baseline Forecast (No Operational Demand Adjustment)</option>
              {adjustments.map((adj) => (
                <option key={adj.operational_adjustment_id} value={adj.operational_adjustment_id}>
                  Adjustment {adj.operational_adjustment_id} (Source Feedback: {adj.source_feedback_id})
                </option>
              ))}
            </select>
            <p className="text-[11px] text-slate-400">
              {selectedAdjustmentId
                ? 'Applying deferred unserved demand from a previous optimization feedback loop without mutating original forecast.'
                : 'Using raw immutable forecast demand directly from the predictor.'}
            </p>
          </div>
        </div>

        {/* Execute Button */}
        <div className="pt-2">
          <button
            type="submit"
            disabled={executing}
            className="w-full py-3.5 bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-800 disabled:text-slate-500 text-slate-950 font-bold rounded-xl text-sm shadow-lg transition-all flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
          >
            {executing ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Executing Allocation Optimization...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                Run Optimization Engine
              </>
            )}
          </button>
        </div>
      </form>

      {/* Immediate Result Card */}
      {lastResult && (
        <div className="bg-slate-900 border border-emerald-500/40 rounded-xl p-6 shadow-md space-y-4 animate-in fade-in">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <h3 className="font-bold text-slate-100 text-base">Optimization Succeeded</h3>
              <StatusBadge status={lastResult.status} />
            </div>
            <span className="font-mono text-xs text-slate-400">ID: {lastResult.allocation_id}</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-slate-950 rounded-lg text-xs">
            <div>
              <span className="text-slate-400 uppercase text-[10px]">Algorithm</span>
              <p className="font-mono font-medium text-slate-200 mt-0.5">{lastResult.algorithm_version}</p>
            </div>
            <div>
              <span className="text-slate-400 uppercase text-[10px]">Hard Constraints</span>
              <p className="font-semibold text-emerald-400 mt-0.5">
                {lastResult.constraint_validation_passed ? 'Passed All Checks' : 'Violations Reported'}
              </p>
            </div>
            <div>
              <span className="text-slate-400 uppercase text-[10px]">Stations Computed</span>
              <p className="font-semibold text-slate-200 mt-0.5">{lastResult.results.length} Active Stations</p>
            </div>
            <div>
              <span className="text-slate-400 uppercase text-[10px]">Outcome Classification</span>
              <p className="font-semibold text-sky-400 mt-0.5">{lastResult.outcome_kind.toUpperCase()}</p>
            </div>
          </div>

          {lastResult.warnings.length > 0 && (
            <div className="p-3 bg-amber-950/30 border border-amber-800/40 rounded-lg text-xs text-amber-300">
              <span className="font-semibold">Operational Warnings:</span>
              <ul className="list-disc list-inside mt-1 space-y-0.5 text-amber-300/80">
                {lastResult.warnings.map((w, idx) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              onClick={() => navigate(`/results?id=${lastResult.allocation_id}`)}
              className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold rounded-lg text-xs shadow transition-colors flex items-center gap-1.5"
            >
              Inspect Detailed Allocation Results
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
