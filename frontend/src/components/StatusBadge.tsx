import React from 'react';

interface StatusBadgeProps {
  status: string;
  label?: string;
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, size = 'sm' }) => {
  const norm = status.toLowerCase();
  let colorStyles = 'bg-slate-800 text-slate-300 border-slate-700';

  if (norm === 'success' || norm === 'submitted' || norm === 'active' || norm === 'healthy' || norm === 'ok') {
    colorStyles = 'bg-emerald-950/70 text-emerald-300 border-emerald-500/30';
  } else if (norm === 'pending' || norm === 'degraded' || norm === 'partial') {
    colorStyles = 'bg-amber-950/70 text-amber-300 border-amber-500/30';
  } else if (norm === 'failed' || norm === 'infeasible' || norm === 'inactive' || norm === 'unhealthy') {
    colorStyles = 'bg-rose-950/70 text-rose-300 border-rose-500/30';
  } else if (norm === 'simulation') {
    colorStyles = 'bg-sky-950/70 text-sky-300 border-sky-500/30';
  } else if (norm === 'observed') {
    colorStyles = 'bg-purple-950/70 text-purple-300 border-purple-500/30';
  }

  const padding = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm';

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium rounded-full border ${padding} ${colorStyles}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" />
      {label || status.toUpperCase()}
    </span>
  );
};
