import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Station, GridGroup, StationCreate, GridGroupCreate } from '../types/api';
import { StatusBadge } from '../components/StatusBadge';
import {
  Plus,
  AlertCircle,
  CheckCircle,
  RefreshCw,
  X,
} from 'lucide-react';

export const StationsGridPage: React.FC = () => {
  const [stations, setStations] = useState<Station[]>([]);
  const [gridGroups, setGridGroups] = useState<GridGroup[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Modal states
  const [showAddStation, setShowAddStation] = useState<boolean>(false);
  const [showAddGrid, setShowAddGrid] = useState<boolean>(false);

  // Form states
  const [newStation, setNewStation] = useState<StationCreate>({
    station_id: '',
    station_name: '',
    charger_count: 8,
    available_chargers: 8,
    charger_power_kw_per_charger: 50.0,
    station_power_limit_kw: 350.0,
    avg_session_minutes: 45.0,
    grid_group_id: '',
    is_active: true,
  });

  const [newGridGroup, setNewGridGroup] = useState<GridGroupCreate>({
    grid_group_id: '',
    grid_group_name: '',
    grid_limit_kw: 600.0,
    other_load_kw: 100.0,
  });

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [stnData, gridData] = await Promise.all([api.getStations(), api.getGridGroups()]);
      setStations(stnData);
      setGridGroups(gridData);
      if (gridData.length > 0 && !newStation.grid_group_id) {
        setNewStation((prev) => ({ ...prev, grid_group_id: gridData[0].grid_group_id }));
      }
    } catch (err: any) {
      setError(err.message || 'Failed loading stations/grid data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCreateStation = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setError(null);
      await api.createStation(newStation);
      setSuccessMsg(`Station ${newStation.station_id} created successfully.`);
      setShowAddStation(false);
      setNewStation({
        station_id: '',
        station_name: '',
        charger_count: 8,
        available_chargers: 8,
        charger_power_kw_per_charger: 50.0,
        station_power_limit_kw: 350.0,
        avg_session_minutes: 45.0,
        grid_group_id: gridGroups[0]?.grid_group_id || '',
        is_active: true,
      });
      loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to create station.');
    }
  };

  const handleCreateGridGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setError(null);
      await api.createGridGroup(newGridGroup);
      setSuccessMsg(`Grid group ${newGridGroup.grid_group_id} created successfully.`);
      setShowAddGrid(false);
      setNewGridGroup({
        grid_group_id: '',
        grid_group_name: '',
        grid_limit_kw: 600.0,
        other_load_kw: 100.0,
      });
      loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to create grid group.');
    }
  };

  const handleDeactivateStation = async (stationId: string) => {
    if (!window.confirm(`Are you sure you want to deactivate station ${stationId}?`)) return;
    try {
      setError(null);
      await api.deactivateStation(stationId);
      setSuccessMsg(`Station ${stationId} deactivated.`);
      loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to deactivate station.');
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
        <RefreshCw className="w-7 h-7 animate-spin text-emerald-400" />
        <p className="text-sm font-medium">Loading infrastructure topologies...</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h2 className="text-2xl font-bold text-slate-100 tracking-tight">Charging Stations & Grid Groups</h2>
          <p className="text-sm text-slate-400 mt-1">
            Configure hardware power limits, installed charger counts, and shared substation grid capacities.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowAddGrid(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-xs font-semibold text-slate-200 transition-colors"
          >
            <Plus className="w-3.5 h-3.5 text-emerald-400" />
            Add Grid Group
          </button>
          <button
            onClick={() => setShowAddStation(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-emerald-500 hover:bg-emerald-600 text-slate-950 rounded-lg text-xs font-bold shadow transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Charging Station
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-rose-950/40 border border-rose-800/60 rounded-xl p-4 text-rose-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-rose-200">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {successMsg && (
        <div className="bg-emerald-950/40 border border-emerald-800/60 rounded-xl p-4 text-emerald-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            <span>{successMsg}</span>
          </div>
          <button onClick={() => setSuccessMsg(null)} className="text-emerald-400 hover:text-emerald-200">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Grid Groups Section */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-slate-100 text-sm">Shared Substation Grid Groups</h3>
            <p className="text-xs text-slate-400">
              Residual EV capacity calculation: <code className="text-emerald-400 font-mono">max(0, grid_limit_kw - other_load_kw)</code>
            </p>
          </div>
          <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400">
            {gridGroups.length} Grid Groups
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-800/60 uppercase text-[10px] text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-2.5 px-3">Grid Group ID</th>
                <th className="py-2.5 px-3">Name / Substation</th>
                <th className="py-2.5 px-3">Total Grid Limit</th>
                <th className="py-2.5 px-3">Non-EV Baseline Load</th>
                <th className="py-2.5 px-3">Residual EV Capacity</th>
                <th className="py-2.5 px-3">Connected Stations</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {gridGroups.map((g) => {
                const connectedCount = stations.filter((s) => s.grid_group_id === g.grid_group_id).length;
                return (
                  <tr key={g.grid_group_id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-3 font-mono font-medium text-slate-200">{g.grid_group_id}</td>
                    <td className="py-3 px-3 font-medium text-slate-300">{g.grid_group_name}</td>
                    <td className="py-3 px-3 font-semibold text-slate-200">{g.grid_limit_kw} kW</td>
                    <td className="py-3 px-3 text-amber-400">{g.other_load_kw} kW</td>
                    <td className="py-3 px-3">
                      <span className="text-emerald-400 font-bold">{g.residual_capacity_kw} kW</span>
                    </td>
                    <td className="py-3 px-3 text-slate-400">{connectedCount} stations</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Charging Stations Section */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-slate-100 text-sm">Configured Charging Stations</h3>
            <p className="text-xs text-slate-400">
              Station hardware ratings, charger availability, and associated shared grid groups
            </p>
          </div>
          <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400">
            {stations.length} Configured Stations
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-800/60 uppercase text-[10px] text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-2.5 px-3">Station ID</th>
                <th className="py-2.5 px-3">Name</th>
                <th className="py-2.5 px-3">Chargers (Avail/Total)</th>
                <th className="py-2.5 px-3">Rating / Charger</th>
                <th className="py-2.5 px-3">Station Limit</th>
                <th className="py-2.5 px-3">Avg Session</th>
                <th className="py-2.5 px-3">Grid Group</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {stations.map((s) => (
                <tr key={s.station_id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-3 px-3 font-mono font-medium text-slate-200">{s.station_id}</td>
                  <td className="py-3 px-3 font-medium text-slate-200">{s.station_name}</td>
                  <td className="py-3 px-3">
                    <span className="text-emerald-400 font-semibold">{s.available_chargers}</span> / {s.charger_count}
                  </td>
                  <td className="py-3 px-3 text-slate-300">{s.charger_power_kw_per_charger} kW</td>
                  <td className="py-3 px-3 font-semibold text-slate-200">{s.station_power_limit_kw} kW</td>
                  <td className="py-3 px-3 text-slate-400">{s.avg_session_minutes} min</td>
                  <td className="py-3 px-3 font-mono text-xs text-slate-400">{s.grid_group_id}</td>
                  <td className="py-3 px-3">
                    <StatusBadge status={s.is_active ? 'active' : 'inactive'} />
                  </td>
                  <td className="py-3 px-3 text-right">
                    {s.is_active && (
                      <button
                        onClick={() => handleDeactivateStation(s.station_id)}
                        className="px-2.5 py-1 bg-rose-950/60 hover:bg-rose-900/80 border border-rose-800/60 text-rose-300 rounded text-xs transition-colors"
                        title="Deactivate station safely"
                      >
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Station Modal */}
      {showAddStation && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-lg w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-slate-100 text-sm">Add New Charging Station</h3>
              <button onClick={() => setShowAddStation(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleCreateStation} className="space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Station ID</label>
                  <input
                    type="text"
                    required
                    value={newStation.station_id}
                    onChange={(e) => setNewStation({ ...newStation, station_id: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200 font-mono"
                    placeholder="e.g. STN-06"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Station Name</label>
                  <input
                    type="text"
                    required
                    value={newStation.station_name}
                    onChange={(e) => setNewStation({ ...newStation, station_name: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200"
                    placeholder="e.g. Airport Express Hub"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Installed Chargers</label>
                  <input
                    type="number"
                    min={1}
                    required
                    value={newStation.charger_count}
                    onChange={(e) =>
                      setNewStation({
                        ...newStation,
                        charger_count: parseInt(e.target.value) || 1,
                        available_chargers: Math.min(newStation.available_chargers, parseInt(e.target.value) || 1),
                      })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Available Chargers</label>
                  <input
                    type="number"
                    min={0}
                    max={newStation.charger_count}
                    required
                    value={newStation.available_chargers}
                    onChange={(e) => setNewStation({ ...newStation, available_chargers: parseInt(e.target.value) || 0 })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Rating / Charger (kW)</label>
                  <input
                    type="number"
                    step="0.1"
                    min={1}
                    required
                    value={newStation.charger_power_kw_per_charger}
                    onChange={(e) =>
                      setNewStation({ ...newStation, charger_power_kw_per_charger: parseFloat(e.target.value) || 1 })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Station Power Limit (kW)</label>
                  <input
                    type="number"
                    step="0.1"
                    min={1}
                    required
                    value={newStation.station_power_limit_kw}
                    onChange={(e) =>
                      setNewStation({ ...newStation, station_power_limit_kw: parseFloat(e.target.value) || 1 })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Avg Session (Minutes)</label>
                  <input
                    type="number"
                    step="1"
                    min={5}
                    required
                    value={newStation.avg_session_minutes}
                    onChange={(e) =>
                      setNewStation({ ...newStation, avg_session_minutes: parseFloat(e.target.value) || 5 })
                    }
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Grid Group</label>
                  <select
                    value={newStation.grid_group_id}
                    onChange={(e) => setNewStation({ ...newStation, grid_group_id: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200 font-mono"
                    required
                  >
                    {gridGroups.map((g) => (
                      <option key={g.grid_group_id} value={g.grid_group_id}>
                        {g.grid_group_id} ({g.grid_group_name})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddStation(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-300 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold rounded-lg shadow transition-colors"
                >
                  Save Station
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Grid Group Modal */}
      {showAddGrid && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-slate-100 text-sm">Add New Grid Group</h3>
              <button onClick={() => setShowAddGrid(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleCreateGridGroup} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Grid Group ID</label>
                <input
                  type="text"
                  required
                  value={newGridGroup.grid_group_id}
                  onChange={(e) => setNewGridGroup({ ...newGridGroup, grid_group_id: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200 font-mono"
                  placeholder="e.g. GRID-PORT"
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Grid Group Name</label>
                <input
                  type="text"
                  required
                  value={newGridGroup.grid_group_name}
                  onChange={(e) => setNewGridGroup({ ...newGridGroup, grid_group_name: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200"
                  placeholder="e.g. Harbor Industrial Substation"
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Total Grid Capacity Limit (kW)</label>
                <input
                  type="number"
                  step="0.1"
                  min={1}
                  required
                  value={newGridGroup.grid_limit_kw}
                  onChange={(e) => setNewGridGroup({ ...newGridGroup, grid_limit_kw: parseFloat(e.target.value) || 1 })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200"
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Non-EV Baseline Load (kW)</label>
                <input
                  type="number"
                  step="0.1"
                  min={0}
                  required
                  value={newGridGroup.other_load_kw}
                  onChange={(e) => setNewGridGroup({ ...newGridGroup, other_load_kw: parseFloat(e.target.value) || 0 })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200"
                />
              </div>
              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddGrid(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-300 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold rounded-lg shadow transition-colors"
                >
                  Save Grid Group
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
