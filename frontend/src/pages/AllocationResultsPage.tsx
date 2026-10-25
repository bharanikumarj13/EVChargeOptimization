import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { AllocationRunResponse, AllocationRunSummary } from '../types/api';
import { StatusBadge } from '../components/StatusBadge';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import {
  BarChart3,
  CheckCircle2,
  AlertCircle,
  Repeat,
  RefreshCw,
  TrendingUp,
} from 'lucide-react';

export const AllocationResultsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const allocationIdParam = searchParams.get('id');

  const [allocation, setAllocation] = useState<AllocationRunResponse | null>(null);
  const [recentRuns, setRecentRuns] = useState<AllocationRunSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [submittingFeedback, setSubmittingFeedback] = useState<boolean>(false);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string | null>(null);

  const loadRunsAndAllocation = async (targetId?: string) => {
    try {
      setLoading(true);
      setError(null);
      const runs = await api.getRecentAllocations(30);
      setRecentRuns(runs);

      const idToFetch = targetId || allocationIdParam || (runs.length > 0 ? runs[0].allocation_id : null);
      if (idToFetch) {
        const data = await api.getAllocation(idToFetch);
        setAllocation(data);
        setSearchParams({ id: idToFetch });
      } else {
        setAllocation(null);
      }
    } catch (err: any) {
      setError(err.message || 'Failed loading allocation results');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRunsAndAllocation(allocationIdParam || undefined);
  }, [allocationIdParam]);

  const handleSubmitFeedback = async () => {
    if (!allocation) return;
    try {
      setSubmittingFeedback(true);
      setError(null);
      const resp = await api.submitFeedback(allocation.allocation_id, { deferred_fraction: 0.70 });
      setFeedbackSuccess(
        `Feedback ${resp.feedback_id} submitted! Next operational adjustment created: ${resp.operational_adjustment_id || 'Ready'}`
      );
      // Wait a moment then navigate to feedback loop page
      setTimeout(() => {
        navigate('/feedback');
      }, 1200);
    } catch (err: any) {
      setError(err.message || 'Failed to submit feedback.');
    } finally {
      setSubmittingFeedback(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
        <RefreshCw className="w-7 h-7 animate-spin text-emerald-400" />
        <p className="text-sm font-medium">Loading allocation outcomes and constraint telemetry...</p>
      </div>
    );
  }

  if (!allocation) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center space-y-4">
        <BarChart3 className="w-10 h-10 text-slate-500 mx-auto" />
        <h3 className="text-base font-semibold text-slate-200">No Allocation Selected</h3>
        <p className="text-xs text-slate-400 max-w-sm mx-auto">
          Please run an optimization first or select an existing allocation from history.
        </p>
        <button
          onClick={() => navigate('/optimize')}
          className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold rounded-lg text-xs"
        >
          Execute New Optimization
        </button>
      </div>
    );
  }

  // Chart data
  const servedVsUnservedData = allocation.results.map((r) => ({
    stationId: r.station_id,
    served: r.estimated_served,
    unserved: r.estimated_unserved,
    powerAllocated: r.allocated_power_kw,
    utilization: r.charger_utilization_pct,
  }));

  const totalDemand = allocation.results.reduce((acc, r) => acc + r.predicted_arrivals, 0);
  const totalServed = allocation.results.reduce((acc, r) => acc + r.estimated_served, 0);
  const totalPower = allocation.results.reduce((acc, r) => acc + r.allocated_power_kw, 0);

  return (
    <div className="space-y-6">
      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-500/40 rounded-xl text-xs text-rose-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-400" />
          {error}
        </div>
      )}
      {/* Header with Switcher and Feedback Action */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold text-slate-100 tracking-tight">Allocation Decisions & Impact</h2>
            <StatusBadge status={allocation.status} />
            <StatusBadge status={allocation.outcome_kind} label="Simulated Estimates" />
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Persisted optimization run: <span className="font-mono text-slate-200">{allocation.allocation_id}</span> |
            Planning Interval:{' '}
            <span className="text-slate-300">
              {new Date(allocation.interval_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
              {new Date(allocation.interval_end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Allocation Selector */}
          <select
            value={allocation.allocation_id}
            onChange={(e) => {
              setSearchParams({ id: e.target.value });
              loadRunsAndAllocation(e.target.value);
            }}
            className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
          >
            {recentRuns.map((r) => (
              <option key={r.allocation_id} value={r.allocation_id}>
                {r.allocation_id} ({r.scenario_id}) - {r.total_served}/{r.total_arrivals} veh
              </option>
            ))}
          </select>

          {/* Submit Feedback Action */}
          <button
            onClick={handleSubmitFeedback}
            disabled={submittingFeedback}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-800 disabled:text-slate-500 text-slate-950 font-bold rounded-lg text-xs shadow transition-colors cursor-pointer"
          >
            {submittingFeedback ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Repeat className="w-3.5 h-3.5" />
            )}
            Submit Feedback to Predictor
          </button>
        </div>
      </div>

      {feedbackSuccess && (
        <div className="p-3 bg-emerald-950/60 border border-emerald-500/40 rounded-xl text-xs text-emerald-300 flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          {feedbackSuccess}
        </div>
      )}

      {/* Metadata Pill Box */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 p-4 bg-slate-900 border border-slate-800 rounded-xl text-xs">
        <div>
          <span className="text-[10px] uppercase text-slate-400">Scenario</span>
          <p className="font-mono font-medium text-slate-200 mt-0.5">{allocation.scenario_id}</p>
        </div>
        <div>
          <span className="text-[10px] uppercase text-slate-400">Forecast Reference</span>
          <p className="font-mono font-medium text-slate-200 mt-0.5">{allocation.forecast_id}</p>
        </div>
        <div>
          <span className="text-[10px] uppercase text-slate-400">Demand Basis</span>
          <p className="font-medium text-slate-200 mt-0.5">
            {allocation.operational_adjustment_id ? (
              <span className="text-amber-400 font-mono">Adjusted ({allocation.operational_adjustment_id})</span>
            ) : (
              <span className="text-sky-400">Baseline Forecast</span>
            )}
          </p>
        </div>
        <div>
          <span className="text-[10px] uppercase text-slate-400">Hard Constraints</span>
          <p className="font-semibold text-emerald-400 mt-0.5">
            {allocation.constraint_validation_passed ? 'Satisfied All Constraints' : 'Violations Detected'}
          </p>
        </div>
        <div>
          <span className="text-[10px] uppercase text-slate-400">Total Demand Served</span>
          <p className="font-semibold text-slate-100 mt-0.5">
            <span className="text-emerald-400">{totalServed.toFixed(1)}</span> / {totalDemand.toFixed(1)} veh
          </p>
        </div>
        <div>
          <span className="text-[10px] uppercase text-slate-400">Aggregate Power</span>
          <p className="font-semibold text-slate-100 mt-0.5">{totalPower.toFixed(1)} kW</p>
        </div>
      </div>

      {/* Objective and Policy Banner */}
      <div className="p-3.5 bg-slate-950 border border-slate-800/80 rounded-lg text-xs text-slate-400 flex items-start gap-2.5">
        <TrendingUp className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-slate-300">Optimization Policy: </span>
          {allocation.objective_description}
        </div>
      </div>

      {/* Visual Charts: Served vs Unserved & Power per Station */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
          <h3 className="font-semibold text-slate-100 text-sm mb-1">Served vs Unserved Demand (Vehicles)</h3>
          <p className="text-xs text-slate-400 mb-4">Simulated vehicle turnover capacity per station for this interval</p>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={servedVsUnservedData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                <XAxis dataKey="stationId" stroke="#94a3b8" fontSize={11} />
                <YAxis stroke="#94a3b8" fontSize={11} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px' }}
                  labelStyle={{ color: '#f8fafc', fontWeight: 'bold' }}
                />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Bar dataKey="served" name="Estimated Served" stackId="a" fill="#10b981" />
                <Bar dataKey="unserved" name="Estimated Unserved" stackId="a" fill="#f43f5e" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
          <h3 className="font-semibold text-slate-100 text-sm mb-1">Allocated Power Output (kW)</h3>
          <p className="text-xs text-slate-400 mb-4">Power allocated under substation & charger physical limits</p>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={servedVsUnservedData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                <XAxis dataKey="stationId" stroke="#94a3b8" fontSize={11} />
                <YAxis stroke="#94a3b8" fontSize={11} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px' }}
                  labelStyle={{ color: '#f8fafc', fontWeight: 'bold' }}
                />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Bar dataKey="powerAllocated" name="Allocated Power (kW)" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Station-wise Results Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-slate-100 text-sm">Station-wise Allocation Breakdown</h3>
            <p className="text-xs text-slate-400">
              Arrivals, energy, power, simulated queue wait time, and charger utilization
            </p>
          </div>
          <span className="text-xs text-slate-400">{allocation.results.length} Stations Evaluated</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-800/60 uppercase text-[10px] text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-2.5 px-3">Station ID</th>
                <th className="py-2.5 px-3">Predicted Demand</th>
                <th className="py-2.5 px-3">Estimated Served</th>
                <th className="py-2.5 px-3">Estimated Unserved</th>
                <th className="py-2.5 px-3">Allocated Power</th>
                <th className="py-2.5 px-3">Served Energy</th>
                <th className="py-2.5 px-3">Estimated Wait</th>
                <th className="py-2.5 px-3">Utilization</th>
                <th className="py-2.5 px-3">Warnings</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {allocation.results.map((res) => (
                <tr key={res.station_id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-3 px-3 font-mono font-medium text-slate-200">{res.station_id}</td>
                  <td className="py-3 px-3">
                    <span className="font-semibold text-slate-100">{res.predicted_arrivals} veh</span>
                    <span className="text-[10px] text-slate-400 block">{res.predicted_energy_kwh} kWh</span>
                  </td>
                  <td className="py-3 px-3 font-semibold text-emerald-400">{res.estimated_served} veh</td>
                  <td className="py-3 px-3 font-semibold text-rose-400">{res.estimated_unserved} veh</td>
                  <td className="py-3 px-3 font-semibold text-sky-400">{res.allocated_power_kw} kW</td>
                  <td className="py-3 px-3 text-slate-300">{res.estimated_served_energy_kwh} kWh</td>
                  <td className="py-3 px-3 text-slate-300">
                    {res.estimated_wait_minutes != null ? `${res.estimated_wait_minutes} min` : 'N/A'}
                  </td>
                  <td className="py-3 px-3">
                    <span
                      className={`font-medium ${
                        res.charger_utilization_pct > 90
                          ? 'text-amber-400'
                          : res.charger_utilization_pct > 0
                          ? 'text-emerald-400'
                          : 'text-slate-500'
                      }`}
                    >
                      {res.charger_utilization_pct}%
                    </span>
                  </td>
                  <td className="py-3 px-3">
                    {res.warnings && res.warnings.length > 0 ? (
                      <span className="text-amber-400 text-[11px]">{res.warnings[0]}</span>
                    ) : (
                      <span className="text-emerald-400/80 text-[11px]">Normal</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
