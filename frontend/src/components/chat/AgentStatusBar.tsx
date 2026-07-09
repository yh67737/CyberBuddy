"use client";

import { AgentState } from "@/lib/types";

interface AgentStatusBarProps {
  agentState: AgentState | null;
  isSecurityMode: boolean;
}

export function AgentStatusBar({ agentState, isSecurityMode }: AgentStatusBarProps) {
  return (
    <div
      className={`px-4 py-2 border-b text-sm flex items-center gap-3 ${
        isSecurityMode
          ? "bg-red-950/40 border-red-800 text-red-200"
          : "bg-slate-900/80 border-slate-800 text-slate-300"
      }`}
    >
      {/* Status indicator */}
      <div className="flex items-center gap-2">
        <span
          className={`w-2 h-2 rounded-full ${
            agentState?.isActive
              ? isSecurityMode
                ? "bg-red-400 animate-pulse"
                : "bg-green-400 animate-pulse"
              : "bg-slate-600"
          }`}
        />
        <span className="text-xs font-medium">
          {isSecurityMode ? "🔴 安全模式" : "🟢 在线"}
        </span>
      </div>

      {/* Agent pipeline visualization */}
      <div className="flex items-center gap-2 text-xs">
        {["Memory", "Supervisor", "ITSupport", "Knowledge", "SecurityGuardian", "SecOps"].map(
          (agent, i) => (
            <div key={agent} className="flex items-center gap-1">
              {i > 0 && <span className="text-slate-600">→</span>}
              <span
                className={`px-1.5 py-0.5 rounded ${
                  agentState?.agent === agent
                    ? isSecurityMode
                      ? "bg-red-600/30 text-red-200 font-medium"
                      : "bg-blue-600/30 text-blue-200 font-medium"
                    : "text-slate-500"
                }`}
              >
                {agent}
              </span>
            </div>
          )
        )}
      </div>

      {/* Current agent status text */}
      {agentState?.isActive && (
        <span className="text-xs text-slate-400 ml-auto truncate max-w-xs">
          {agentState.agent} {agentState.status}
        </span>
      )}
    </div>
  );
}
