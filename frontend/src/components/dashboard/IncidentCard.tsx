"use client";

import { useState } from "react";
import { SecurityIncident } from "@/lib/types";

interface IncidentCardProps {
  incident: SecurityIncident;
}

const severityStyles: Record<string, string> = {
  low: "border-slate-600 bg-slate-800/30",
  medium: "border-yellow-600/50 bg-yellow-900/10",
  high: "border-orange-600/50 bg-orange-900/10",
  critical: "border-red-600/50 bg-red-900/20 shadow-lg shadow-red-900/10",
};

const severityBadge: Record<string, string> = {
  low: "bg-slate-700 text-slate-300",
  medium: "bg-yellow-900/50 text-yellow-400",
  high: "bg-orange-900/50 text-orange-400",
  critical: "bg-red-900/50 text-red-200 animate-pulse",
};

const severityLabels: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

const statusFlow: Array<{ key: string; label: string; icon: string }> = [
  { key: "open", label: "待处理", icon: "🔴" },
  { key: "investigating", label: "调查中", icon: "🔍" },
  { key: "contained", label: "已遏制", icon: "🛡️" },
  { key: "closed", label: "已关闭", icon: "✅" },
];

export function IncidentCard({ incident }: IncidentCardProps) {
  const [expanded, setExpanded] = useState(false);
  const currentStep = statusFlow.findIndex((s) => s.key === incident.status);

  return (
    <div
      className={`border rounded-xl p-4 transition-all cursor-pointer ${
        severityStyles[incident.severity] || severityStyles.low
      } ${incident.severity === "critical" ? "animate-pulse" : ""}`}
      onClick={() => setExpanded(!expanded)}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-bold px-2 py-0.5 rounded ${severityBadge[incident.severity]}`}>
            {severityLabels[incident.severity]} · {incident.severity.toUpperCase()}
          </span>
          <span className="text-xs text-slate-500 font-mono">{incident.id.slice(0, 8)}</span>
        </div>
        <span className="text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
          {statusFlow.find((s) => s.key === incident.status)?.label || incident.status}
        </span>
      </div>

      {/* Title + Description */}
      <h3 className="font-semibold text-white mb-1">{incident.title}</h3>
      <p className={`text-sm text-slate-400 ${expanded ? "" : "line-clamp-2"}`}>
        {incident.description}
      </p>

      {/* Status flow indicator */}
      <div className="flex items-center gap-1 mt-3 mb-2">
        {statusFlow.map((step, i) => (
          <div key={step.key} className="flex items-center gap-1 flex-1">
            <div
              className={`flex-1 h-1 rounded-full ${
                i <= currentStep
                  ? i < currentStep ? "bg-green-500" : "bg-blue-400"
                  : "bg-slate-700"
              }`}
            />
            <span className="text-[10px]" title={step.label}>
              {i <= currentStep ? step.icon : "·"}
            </span>
          </div>
        ))}
      </div>

      {/* Expandable details */}
      {expanded && (
        <div className="mt-3 space-y-3 border-t border-slate-700/50 pt-3">
          {/* Agent Summary */}
          {incident.agentSummary && (
            <div className="bg-slate-900/80 border border-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-slate-500 mb-1">🤖 SecOpsAgent 安全摘要</p>
              <p className="text-sm text-slate-300 whitespace-pre-wrap">{incident.agentSummary}</p>
            </div>
          )}

          {/* Entities */}
          {Object.keys(incident.entities).length > 0 && (
            <div>
              <p className="text-xs text-slate-500 mb-1">🏷️ 关键实体</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(incident.entities).map(([key, value]) => (
                  <span key={key} className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded font-mono">
                    <span className="text-slate-500">{key}</span>={value}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Actions — placeholder for future incident management */}
          <div className="flex gap-2">
            <button
              className="text-xs px-3 py-1 bg-blue-600/20 border border-blue-600/40 text-blue-300 rounded-lg hover:bg-blue-600/30"
              onClick={(e) => e.stopPropagation()}
            >
              🔍 调查
            </button>
            <button
              className="text-xs px-3 py-1 bg-green-600/20 border border-green-600/40 text-green-300 rounded-lg hover:bg-green-600/30"
              onClick={(e) => e.stopPropagation()}
            >
              🛡️ 遏制
            </button>
            <button
              className="text-xs px-3 py-1 bg-slate-600/20 border border-slate-600/40 text-slate-400 rounded-lg hover:bg-slate-600/30"
              onClick={(e) => e.stopPropagation()}
            >
              ✅ 关闭
            </button>
          </div>
        </div>
      )}

      {/* Timestamp + expand hint */}
      <div className="flex items-center justify-between text-xs text-slate-600 mt-3">
        <span>{new Date(incident.createdAt).toLocaleString("zh-CN")}</span>
        <span>{expanded ? "收起 ▲" : "展开 ▼"}</span>
      </div>
    </div>
  );
}
