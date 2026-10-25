import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { FeedbackResponse, OperationalAdjustmentResponse } from '../types/api';
import { StatusBadge } from '../components/StatusBadge';
import {
  ArrowRight,
  ShieldCheck,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';

export const FeedbackLoopPage: React.FC = () => {
  const navigate = useNavigate();

  const [feedbacks, setFeedbacks] = useState<FeedbackResponse[]>([]);
  const [adjustments, setAdjustments] = useState<OperationalAdjustmentResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [fbList, adjList] = await Promise.all([
        api.getRecentFeedback(25),
        api.getRecentOperationalAdjustments(25),
      ]);
      setFeedbacks(fbList);
      setAdjustments(adjList);
    } catch (err: any) {
      setError(err.message || 'Failed loading feedback data.');
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
        <p className="text-sm font-medium">Loading feedback loop history and adjustment lineage...</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h2 className="text-2xl font-bold text-slate-100 tracking-tight">Feedback Loop & Lineage Trace</h2>
          <p className="text-sm text-slate-400 mt-1">
            Demonstrating operational coupling with EVCharge-Predict, unserved demand deferral, and subsequent allocation execution.
          </p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-2 px-3 py-2 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-xs font-semibold text-slate-300 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh Lineage
        </button>
      </div>

      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-500/40 rounded-xl text-xs text-rose-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-400" />
          {error}
        </div>
      )}

      {/* Visual Architectural Sequence Diagram */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm space-y-4">
        <h3 className="font-semibold text-slate-100 text-sm">Feedback Loop Architecture</h3>
        <p className="text-xs text-slate-400">
          Traceable multi-step dataflow connecting predictor demand, allocation constraints, feedback delivery, and next-interval operational demand.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-6 gap-2 pt-2">
          <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-center relative">
            <span className="text-[10px] font-mono text-emerald-400">STEP 1</span>
            <div className="text-xs font-bold text-slate-200 mt-1">Baseline Forecast</div>
            <p className="text-[10px] text-slate-400 mt-1">Immutable prediction from model</p>
          </div>
          <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-center relative">
            <span className="text-[10px] font-mono text-emerald-400">STEP 2</span>
            <div className="text-xs font-bold text-slate-200 mt-1">Allocation Run</div>
            <p className="text-[10px] text-slate-400 mt-1">Hardware & grid constraints</p>
          </div>
          <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-center relative">
            <span className="text-[10px] font-mono text-emerald-400">STEP 3</span>
            <div className="text-xs font-bold text-slate-200 mt-1">Impact Simulation</div>
            <p className="text-[10px] text-slate-400 mt-1">Served, unserved & wait times</p>
          </div>
          <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-center relative">
            <span className="text-[10px] font-mono text-emerald-400">STEP 4</span>
            <div className="text-xs font-bold text-slate-200 mt-1">Feedback Record</div>
            <p className="text-[10px] text-slate-400 mt-1">Submitted to predictor adapter</p>
          </div>
          <div className="p-3 bg-slate-950 border border-emerald-500/30 bg-emerald-950/10 rounded-lg text-center relative">
            <span className="text-[10px] font-mono text-emerald-400">STEP 5</span>
            <div className="text-xs font-bold text-emerald-300 mt-1">Operational Adjustment</div>
            <p className="text-[10px] text-slate-400 mt-1">Derived deferred demand</p>
          </div>
          <div className="p-3 bg-slate-950 border border-sky-500/30 bg-sky-950/10 rounded-lg text-center relative">
            <span className="text-[10px] font-mono text-sky-400">STEP 6</span>
            <div className="text-xs font-bold text-sky-300 mt-1">Next Allocation</div>
            <p className="text-[10px] text-slate-400 mt-1">Optimizes adjusted demand</p>
          </div>
        </div>
      </div>

      {/* Baseline Immutability Guarantee Banner */}
      <div className="bg-emerald-950/20 border border-emerald-500/30 rounded-xl p-4 flex items-start gap-3">
        <ShieldCheck className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-slate-300 space-y-1">
          <div className="font-semibold text-emerald-300 text-sm">Baseline Immutability & Deduplication Guarantee</div>
          <p>
            The original baseline forecast produced by EVCharge-Predict is stored as an immutable snapshot and is never overwritten or mutated.
            Feedback-adjusted operational demand is stored as a traceable separate entity (<code className="font-mono text-emerald-400">OperationalAdjustment</code>)
            derived from unserved queue deferral. Demand is strictly conserved and never double-counted.
          </p>
        </div>
      </div>

      {/* Submitted Feedback Records Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-slate-100 text-sm">Submitted Feedback Records</h3>
            <p className="text-xs text-slate-400">Outcomes submitted to EVCharge-Predict with deferred fractions</p>
          </div>
          <span className="text-xs text-slate-400">{feedbacks.length} Feedback Records</span>
        </div>

        {feedbacks.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-800/60 uppercase text-[10px] text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">Feedback ID</th>
                  <th className="py-2.5 px-3">Source Allocation</th>
                  <th className="py-2.5 px-3">Forecast</th>
                  <th className="py-2.5 px-3">Deferred Fraction</th>
                  <th className="py-2.5 px-3">Idempotency Key</th>
                  <th className="py-2.5 px-3">Submission Status</th>
                  <th className="py-2.5 px-3">Adjustment Linked</th>
                  <th className="py-2.5 px-3 text-right">Created At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {feedbacks.map((fb) => (
                  <tr key={fb.feedback_id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-3 font-mono font-medium text-slate-200">{fb.feedback_id}</td>
                    <td className="py-3 px-3 font-mono text-emerald-400">{fb.allocation_id}</td>
                    <td className="py-3 px-3 font-mono text-slate-400">{fb.forecast_id}</td>
                    <td className="py-3 px-3 font-semibold text-slate-300">{(fb.deferred_fraction * 100).toFixed(0)}%</td>
                    <td className="py-3 px-3 font-mono text-[10px] text-slate-400">{fb.idempotency_key}</td>
                    <td className="py-3 px-3">
                      <StatusBadge status={fb.submission_status} />
                    </td>
                    <td className="py-3 px-3 font-mono text-sky-400">
                      {fb.operational_adjustment_id || 'None'}
                    </td>
                    <td className="py-3 px-3 text-right text-slate-400 font-mono text-[11px]">
                      {new Date(fb.created_at).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-8 text-center text-slate-500 text-xs">
            No feedback submitted yet. Run an allocation and click "Submit Feedback".
          </div>
        )}
      </div>

      {/* Operational Adjustments Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-slate-100 text-sm">Operational Demand Adjustments</h3>
            <p className="text-xs text-slate-400">
              Downstream adjusted demand for subsequent intervals reflecting deferred unserved vehicles
            </p>
          </div>
          <span className="text-xs text-slate-400">{adjustments.length} Adjustments Available</span>
        </div>

        {adjustments.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-800/60 uppercase text-[10px] text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">Adjustment ID</th>
                  <th className="py-2.5 px-3">Source Feedback</th>
                  <th className="py-2.5 px-3">Parent Forecast</th>
                  <th className="py-2.5 px-3">Target Interval</th>
                  <th className="py-2.5 px-3">Deferred Vehicles Added</th>
                  <th className="py-2.5 px-3">Adjusted Demand Total</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {adjustments.map((adj) => {
                  const totalDeferredVeh = adj.station_adjustments.reduce(
                    (acc, s) => acc + s.deferred_vehicles_added,
                    0
                  );
                  const totalAdjustedVeh = adj.station_adjustments.reduce(
                    (acc, s) => acc + s.adjusted_predicted_arrivals,
                    0
                  );

                  return (
                    <tr key={adj.operational_adjustment_id} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-3 px-3 font-mono font-medium text-amber-400">
                        {adj.operational_adjustment_id}
                      </td>
                      <td className="py-3 px-3 font-mono text-slate-400">{adj.source_feedback_id}</td>
                      <td className="py-3 px-3 font-mono text-slate-400">{adj.parent_forecast_id}</td>
                      <td className="py-3 px-3 text-slate-400">
                        {new Date(adj.target_interval_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
                        {new Date(adj.target_interval_end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </td>
                      <td className="py-3 px-3 font-semibold text-amber-400">+{totalDeferredVeh.toFixed(1)} veh</td>
                      <td className="py-3 px-3 font-semibold text-emerald-400">{totalAdjustedVeh.toFixed(1)} veh</td>
                      <td className="py-3 px-3 text-right">
                        <button
                          onClick={() => navigate('/optimize')}
                          className="px-3 py-1 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 rounded text-xs transition-colors font-medium inline-flex items-center gap-1"
                        >
                          Optimize
                          <ArrowRight className="w-3 h-3" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-8 text-center text-slate-500 text-xs">
            No operational adjustments generated yet.
          </div>
        )}
      </div>
    </div>
  );
};
