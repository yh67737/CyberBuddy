"use client";

import { SecurityIncident } from "@/lib/types";

interface IncidentCardProps {
  incident: SecurityIncident;
}

const severityStyles: Record<string, string> = {
  low: "border-slate-600 bg-slate-800/30",
  medium: "border-yellow-600/50 bg-yellow-900/10",
  high: "border-orange-600/50 bg-orange-900/10",
  critical: "border-red-600/50 bg-red-900/20 animate-pulse",
};

const severityLabels: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

const statusLabels: Record<string, string> = {
  open: "待处理",
  investigating: "调查中",
  contained: "已遏制",
  closed: "已关闭",
};

export function IncidentCard({ incident }: IncidentCardProps) {
  return (
    <div
      className={`border rounded-xl p-4 ${severityStyles[incident.severity] || severityStyles.low}`}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-bold px-2 py-0.5 rounded ${
              incident.severity === "critical"
                ? "bg-red-600 text-white"
                : "bg-slate-700 text-slate-300"
            }`}
          >
            {severityLabels[incident.severity]} · {incident.severity.toUpperCase()}
          </span>
          <span className="text-xs text-slate-500">{incident.id.slice(0, 8)}</span>
        </div>
        <span className="text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
          {statusLabels[incident.status] || incident.status}
        </span>
      </div>

      <h3 className="font-semibold text-white mb-1">{incident.title}</h3>
      <p className="text-sm text-slate-400 mb-3">{incident.description}</p>

      {/* Agent Summary */}
      {incident.agentSummary && (
        <div className="bg-slate-900/80 border border-slate-700/50 rounded-lg p-3 mb-3">
          <p className="text-xs text-slate-500 mb-1">🤖 SecOpsAgent 安全摘要</p>
          <p className="text-sm text-slate-300">{incident.agentSummary}</p>
        </div>
      )}

      {/* Entities */}
      {Object.keys(incident.entities).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(incident.entities).map(([key, value]) => (
            <span key={key} className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
              {key}: {value}
            </span>
          ))}
        </div>
      )}

      <div className="text-xs text-slate-600 mt-3">
        {new Date(incident.createdAt).toLocaleString("zh-CN")}
      </div>
    </div>
  );
}
