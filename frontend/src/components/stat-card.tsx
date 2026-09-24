import type { ReactNode } from "react";

export function StatCard({
  label,
  value,
  trend,
  trendUp = true,
  icon,
}: {
  label: string;
  value: string;
  trend?: string;
  trendUp?: boolean;
  icon?: ReactNode;
}) {
  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium text-slate-400">{label}</span>
        {icon && (
          <div className="w-10 h-10 rounded-xl bg-primary-500/20 flex items-center justify-center text-primary-400">
            {icon}
          </div>
        )}
      </div>
      <div className="text-3xl font-black text-white mb-2">{value}</div>
      {trend && (
        <div className={`flex items-center gap-1 text-sm ${trendUp ? "text-green-400" : "text-slate-500"}`}>
          <span className="font-medium">{trendUp ? "↑" : "—"}</span>
          <span>{trend}</span>
        </div>
      )}
    </div>
  );
}