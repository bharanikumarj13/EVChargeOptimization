import React from 'react';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  trend?: string;
  trendPositive?: boolean;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  icon,
  trend,
  trendPositive,
}) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm hover:border-slate-700 transition-colors">
      <div className="flex items-center justify-between text-slate-400 mb-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">{title}</span>
        {icon && <div className="text-emerald-400">{icon}</div>}
      </div>
      <div className="text-2xl font-bold text-slate-100">{value}</div>
      {(subtitle || trend) && (
        <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
          {subtitle && <span>{subtitle}</span>}
          {trend && (
            <span className={trendPositive ? 'text-emerald-400 font-medium' : 'text-amber-400 font-medium'}>
              {trend}
            </span>
          )}
        </div>
      )}
    </div>
  );
};
