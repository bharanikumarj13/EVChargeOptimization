import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import { AllocationRunSummary } from '../types/api';
import { StatusBadge } from '../components/StatusBadge';
import {
  Download,
  Search,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';

export const HistoryReportsPage: React.FC = () => {
  const [runs, setRuns] = useState<AllocationRunSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadRuns = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getRecentAllocations(100);
      setRuns(data);
    } catch (err: any) {
      setError(err.message || 'Failed loading allocation history.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRuns();
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
        <RefreshCw className="w-7 h-7 animate-spin text-emerald-400" />
        <p className="text-sm font-medium">Loading allocation audit history...</p>
      </div>
    );
  }

  const handleDownloadCsv = () => {
    const url = api.getExportCsvUrl();
    window.open(url, '_blank');
  };

  const filteredRuns = runs.filter((r) => {
    const matchesSearch =
      r.allocation_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.scenario_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.forecast_id.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesStatus =
      statusFilter === 'all' || r.status.toLowerCase() === statusFilter.toLowerCase();

    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h2 className="text-2xl font-bold text-slate-100 tracking-tight">Allocation History & Audit Reports</h2>
          <p className="text-sm text-slate-400 mt-1">
            Search, filter, and export persistent optimization records and constraint compliance data.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadRuns}
            className="p-2.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-400 hover:text-slate-200 transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={handleDownloadCsv}
            className="flex items-center gap-2 px-4 py-2.5 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold rounded-lg text-xs shadow transition-colors cursor-pointer"
          >
            <Download className="w-4 h-4" />
            Export Allocations CSV
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-500/40 rounded-xl text-xs text-rose-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-400" />
          {error}
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-500" />
          <input
            type="text"
            placeholder="Search by Allocation ID, Scenario ID, or Forecast ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-10 pr-4 py-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
          />
        </div>
        <div className="sm:w-48">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
          >
            <option value="all">All Outcomes</option>
            <option value="success">Success Only</option>
            <option value="infeasible">Infeasible Only</option>
          </select>
        </div>
      </div>

      {/* History Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">
            Showing {filteredRuns.length} of {runs.length} recorded allocations
          </span>
          <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
            Direct Database Persistence
          </span>
        </div>

        {filteredRuns.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-800/60 uppercase text-[10px] text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">Allocation ID</th>
                  <th className="py-2.5 px-3">Scenario</th>
                  <th className="py-2.5 px-3">Forecast</th>
                  <th className="py-2.5 px-3">Adjustment</th>
                  <th className="py-2.5 px-3">Planning Interval</th>
                  <th className="py-2.5 px-3">Served / Demand</th>
                  <th className="py-2.5 px-3">Power (kW)</th>
                  <th className="py-2.5 px-3">Utilization</th>
                  <th className="py-2.5 px-3">Constraints</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredRuns.map((r) => (
                  <tr key={r.allocation_id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-3 font-mono font-medium text-slate-200">{r.allocation_id}</td>
                    <td className="py-3 px-3 font-mono text-slate-400">{r.scenario_id}</td>
                    <td className="py-3 px-3 font-mono text-slate-400">{r.forecast_id}</td>
                    <td className="py-3 px-3 font-mono text-[11px]">
                      {r.operational_adjustment_id ? (
                        <span className="text-amber-400">{r.operational_adjustment_id}</span>
                      ) : (
                        <span className="text-slate-500">None (Baseline)</span>
                      )}
                    </td>
                    <td className="py-3 px-3 text-slate-400">
                      {new Date(r.interval_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
                      {new Date(r.interval_end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="py-3 px-3 font-medium">
                      <span className="text-emerald-400 font-semibold">{r.total_served}</span> / {r.total_arrivals} veh
                    </td>
                    <td className="py-3 px-3 font-semibold text-slate-200">{r.total_allocated_power_kw} kW</td>
                    <td className="py-3 px-3">{r.avg_utilization_pct}%</td>
                    <td className="py-3 px-3">
                      {r.constraint_validation_passed ? (
                        <span className="text-emerald-400 font-medium">Passed</span>
                      ) : (
                        <span className="text-rose-400 font-medium">Violations</span>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="py-3 px-3 text-right">
                      <Link
                        to={`/results?id=${r.allocation_id}`}
                        className="text-xs px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded transition-colors inline-block"
                      >
                        Inspect
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-12 text-center text-slate-500 text-xs">
            No allocation records match the filter criteria.
          </div>
        )}
      </div>
    </div>
  );
};
