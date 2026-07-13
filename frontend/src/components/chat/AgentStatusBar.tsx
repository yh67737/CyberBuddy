"use client";

import { AgentState } from "@/lib/types";

interface AgentStatusBarProps {
  agentState: AgentState | null;
  isSecurityMode: boolean;
}

/** Human-readable status text for each agent */
const agentStatusText: Record<string, string> = {
  MemoryAgent: "加载用户上下文...",
  SupervisorAgent: "分析意图 & 路由决策...",
  ITSupportAgent: "生成回复...",
  KnowledgeAgent: "检索知识库文档...",
  SecurityGuardian: "威胁评估 & 熔断判断...",
  SecOpsAgent: "生成安全工单 & 事件报告...",
};

const agentIcons: Record<string, string> = {
  MemoryAgent: "🧠",
  SupervisorAgent: "🧭",
  ITSupportAgent: "💬",
  KnowledgeAgent: "📚",
  SecurityGuardian: "🛡️",
  SecOpsAgent: "📋",
};

export function AgentStatusBar({ agentState, isSecurityMode }: AgentStatusBarProps) {
  const agentName = agentState?.agent || "";
  const statusDescription = agentState?.isActive
    ? agentStatusText[agentName] || agentState?.status || "处理中..."
    : null;

  return (
    <div
      className={`px-4 py-2 border-b text-sm flex items-center gap-3 transition-colors duration-300 ${
        isSecurityMode
          ? "bg-red-950/40 border-red-800 text-red-200"
          : "bg-slate-900/80 border-slate-800 text-slate-300"
      }`}
    >
      {/* Status indicator */}
      <div className="flex items-center gap-2 shrink-0">
        <span
          className={`w-2.5 h-2.5 rounded-full transition-colors ${
            agentState?.isActive
              ? isSecurityMode
                ? "bg-red-400 animate-pulse"
                : "bg-green-400 animate-pulse"
              : "bg-slate-600"
          }`}
        />
        <span className="text-xs font-medium whitespace-nowrap">
          {isSecurityMode ? "🔴 安全模式" : agentState?.isActive ? "🟢 处理中" : "⚪ 就绪"}
        </span>
      </div>

      {/* Divider */}
      <span className="text-slate-700">|</span>

      {/* Agent pipeline visualization */}
      <div className="flex items-center gap-1.5 text-[11px] overflow-x-auto">
        {[
          "MemoryAgent",
          "SupervisorAgent",
          "ITSupportAgent",
          "KnowledgeAgent",
          "SecurityGuardian",
          "SecOpsAgent",
        ].map((agent, i) => {
          const isCurrent = agentState?.agent === agent;
          const isActive = agentState?.isActive && isCurrent;
          return (
            <div key={agent} className="flex items-center gap-1 shrink-0">
              {i > 0 && <span className="text-slate-600">→</span>}
              <span
                className={`px-1.5 py-0.5 rounded transition-colors duration-300 whitespace-nowrap ${
                  isCurrent
                    ? isSecurityMode
                      ? "bg-red-600/30 text-red-200 font-medium"
                      : "bg-blue-600/30 text-blue-200 font-medium"
                    : "text-slate-500"
                }`}
                title={agent}
              >
                {agentIcons[agent] || ""} {agent}
              </span>
            </div>
          );
        })}
      </div>

      {/* Current agent status description */}
      {statusDescription && (
        <>
          <span className="text-slate-700">|</span>
          <span className="text-xs text-slate-400 truncate animate-pulse">
            {statusDescription}
          </span>
        </>
      )}
    </div>
  );
}
