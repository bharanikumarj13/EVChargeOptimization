import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import { SystemSummaryMetrics, AllocationRunSummary, Station } from '../types/api';
import { MetricCard } from '../components/MetricCard';
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
  AreaChart,
  Area,
} from 'recharts';
import {
  Zap,
  PlayCircle,
  BatteryCharging,
  TrendingUp,
  Server,
  ArrowRight,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';

export const OverviewPage: React.FC = () => {
  const [metrics, setMetrics] = useState<SystemSummaryMetrics | null>(null);
  const [recentRuns, setRecentRuns] = useState<AllocationRunSummary[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [summaryData, runsData, stationsData] = await Promise.all([
        api.getSummaryMetrics(),
        api.getRecentAllocations(8),
        api.getStations(),
      ]);
      setMetrics(summaryData);
      setRecentRuns(runsData);
      setStations(stationsData);
    } catch (err: any) {
      setError(err.message || 'Failed to connect to backend.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
        <RefreshCw className="w-7 h-7 animate-spin text-emerald-400" />
        <p className="text-sm font-medium">Loading operational metrics from FastAPI...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-rose-950/40 border border-rose-800/60 rounded-xl p-6 text-rose-300">
        <div className="flex items-center gap-3 font-semibold text-lg">
          <AlertCircle className="w-5 h-5 text-rose-400" />
          Backend Connection Notice
        </div>
        <p className="mt-2 text-sm text-rose-300/80">{error}</p>
        <button
          onClick={loadData}
          className="mt-4 px-4 py-2 bg-rose-900/60 hover:bg-rose-800/80 rounded-lg text-sm font-medium transition-colors"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  // Pre-aggregate chart data from stations
  const stationPowerData = stations.map((s) => ({
    name: s.station_id,
    installedCapKw: s.charger_count * s.charger_power_kw_per_charger,
    powerLimitKw: s.station_power_limit_kw,
    activeChargers: s.available_chargers,
  }));

  return (
    <div className="space-y-6">
      {/* Top Banner / Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h2 className="text-2xl font-bold text-slate-100 tracking-tight">System Operational Overview</h2>
          <p className="text-sm text-slate-400 mt-1">
            Real-time infrastructure capacity, grid constraints, and simulated optimization outcomes.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadData}
            className="p-2.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-400 hover:text-slate-200 transition-colors"
            title="Refresh Data"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <Link
            to="/optimize"
            className="flex items-center gap-2 px-4 py-2.5 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-semibold rounded-lg text-sm shadow-md transition-colors"
          >
            <PlayCircle className="w-4 h-4" />
            Run New Optimization
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Active Stations"
          value={`${metrics?.active_stations ?? 0} / ${metrics?.total_stations ?? 0}`}
          subtitle="Operating under grid groups"
          icon={<Server className="w-5 h-5" />}
        />
        <MetricCard
          title="Charger Availability"
          value={`${metrics?.total_available_chargers ?? 0} / ${metrics?.total_installed_chargers ?? 0}`}
          subtitle="Operational charging plugs"
          icon={<BatteryCharging className="w-5 h-5" />}
        />
        <MetricCard
          title="Residual Grid Capacity"
          value={`${metrics?.total_residual_grid_kw ?? 0} kW`}
          subtitle={`Limit: ${metrics?.total_grid_limit_kw ?? 0} kW`}
          icon={<Zap className="w-5 h-5" />}
        />
        <MetricCard
          title="Vehicles Served (Simulated)"
          value={`${metrics?.total_estimated_served ?? 0}`}
          subtitle={`Unserved backlog: ${metrics?.total_estimated_unserved ?? 0}`}
          icon={<TrendingUp className="w-5 h-5" />}
        />
      </div>

      {/* Grid: Charts & Details */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Chart 1: Station Hardware vs Connection Limits */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold text-slate-100 text-sm">Station Power Limits vs Hardware Capacity</h3>
              <p className="text-xs text-slate-400">Comparing hardware ratings with substation connection limits (kW)</p>
            </div>
            <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">Active Stations</span>
          </div>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stationPowerData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                <XAxis dataKey="name" stroke="#94a3b8" fontSize={11} />
                <YAxis stroke="#94a3b8" fontSize={11} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px' }}
                  labelStyle={{ color: '#f8fafc', fontWeight: 'bold' }}
                />
                <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '8px' }} />
                <Bar dataKey="powerLimitKw" name="Station Power Limit (kW)" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="installedCapKw" name="Hardware Max Rating (kW)" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 2: Recent Optimization Runs - Served vs Unserved */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold text-slate-100 text-sm">Optimization Outcomes Trend</h3>
              <p className="text-xs text-slate-400">Total simulated arrivals served vs unserved across runs</p>
            </div>
            <StatusBadge status="simulation" label="Simulated Estimates" />
          </div>
          <div className="h-64 w-full">
            {recentRuns.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={[...recentRuns].reverse()}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                  <XAxis dataKey="allocation_id" stroke="#94a3b8" fontSize={10} />
                  <YAxis stroke="#94a3b8" fontSize={11} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px' }}
                    labelStyle={{ color: '#f8fafc', fontWeight: 'bold' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '8px' }} />
                  <Area
                    type="monotone"
                    dataKey="total_served"
                    name="Vehicles Served"
                    stroke="#10b981"
                    fill="#10b981"
                    fillOpacity={0.2}
                  />
                  <Area
                    type="monotone"
                    dataKey="total_unserved"
                    name="Vehicles Unserved"
                    stroke="#f43f5e"
                    fill="#f43f5e"
                    fillOpacity={0.2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-slate-500 text-sm">
                No optimization runs executed yet.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Recent Allocations Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-semibold text-slate-100 text-sm">Recent Allocation Executions</h3>
            <p className="text-xs text-slate-400">Prior operational allocation runs and constraint verification</p>
          </div>
          <Link
            to="/history"
            className="text-xs font-medium text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
          >
            View Full History
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {recentRuns.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-800/60 uppercase text-[10px] text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">Allocation ID</th>
                  <th className="py-2.5 px-3">Scenario</th>
                  <th className="py-2.5 px-3">Forecast</th>
                  <th className="py-2.5 px-3">Planning Interval</th>
                  <th className="py-2.5 px-3">Served / Demand</th>
                  <th className="py-2.5 px-3">Power (kW)</th>
                  <th className="py-2.5 px-3">Utilization</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {recentRuns.map((run) => (
                  <tr key={run.allocation_id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-3 font-mono font-medium text-slate-200">{run.allocation_id}</td>
                    <td className="py-3 px-3 font-mono text-slate-400">{run.scenario_id}</td>
                    <td className="py-3 px-3 font-mono text-slate-400">{run.forecast_id}</td>
                    <td className="py-3 px-3 text-slate-400">
                      {new Date(run.interval_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
                      {new Date(run.interval_end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="py-3 px-3">
                      <span className="text-emerald-400 font-semibold">{run.total_served}</span> / {run.total_arrivals}
                    </td>
                    <td className="py-3 px-3 font-semibold text-slate-200">{run.total_allocated_power_kw} kW</td>
                    <td className="py-3 px-3">{run.avg_utilization_pct}%</td>
                    <td className="py-3 px-3">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="py-3 px-3 text-right">
                      <Link
                        to={`/results?id=${run.allocation_id}`}
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
          <div className="py-8 text-center text-slate-500 text-xs">
            No allocations recorded yet. Run your first allocation using the button above.
          </div>
        )}
      </div>
    </div>
  );
};
