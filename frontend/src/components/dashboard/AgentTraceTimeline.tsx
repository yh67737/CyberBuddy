"use client";

import { useEffect, useState, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface TraceMessage {
  id: string;
  role: string;
  content: string;
  agent_role?: string;
  route_type?: string;
  created_at: string;
}

interface AgentTrace {
  id: string;
  route_type: string;
  agent_trace: string[];
  agent_durations: Record<string, number>;
  total_latency_ms: number;
  status: string;
  created_at: string;
}

interface SessionTrace {
  session_id: string;
  user_id: string;
  messages: TraceMessage[];
  agent_traces: AgentTrace[];
}

interface AgentTraceTimelineProps {
  sessionId: string | null;
  userId?: string;
  onClose: () => void;
}

const agentColors: Record<string, string> = {
  MemoryAgent: "#8b5cf6",
  SupervisorAgent: "#f59e0b",
  ITSupportAgent: "#3b82f6",
  KnowledgeAgent: "#22c55e",
  SecurityGuardian: "#ef4444",
  SecOpsAgent: "#f97316",
};

export function AgentTraceTimeline({ sessionId, userId = "default-user", onClose }: AgentTraceTimelineProps) {
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchTrace = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/dashboard/users/${userId}/sessions/${sessionId}/trace`
      );
      if (!res.ok) return;
      const data = await res.json();
      setTrace(data);
    } catch {
      // API unavailable
    } finally {
      setLoading(false);
    }
  }, [sessionId, userId]);

  useEffect(() => {
    fetchTrace();
  }, [fetchTrace]);

  if (!sessionId) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-start justify-center pt-20">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <div>
            <h3 className="font-semibold">🔬 Agent 链路追踪</h3>
            <p className="text-xs text-slate-500 mt-0.5 font-mono">
              会话 {sessionId.slice(0, 12)}...
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-white text-lg leading-none p-1"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {loading ? (
            <div className="flex justify-center py-8">
              <div className="w-5 h-5 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
            </div>
          ) : trace ? (
            <>
              {/* Agent pipeline traces */}
              {trace.agent_traces.map((at, ti) => (
                <div key={at.id}>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-xs bg-slate-800 px-2 py-0.5 rounded text-slate-400">
                      第 {ti + 1} 轮
                    </span>
                    <span className="text-xs text-slate-500">
                      {new Date(at.created_at).toLocaleTimeString("zh-CN")}
                    </span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ml-auto ${
                      at.route_type === "RISK" ? "bg-red-900/40 text-red-400" :
                      at.route_type === "CONSULT" ? "bg-green-900/40 text-green-400" :
                      "bg-slate-800 text-slate-400"
                    }`}>
                      {at.route_type}
                    </span>
                  </div>

                  {/* Agent execution timeline */}
                  <div className="relative ml-4">
                    {at.agent_trace.map((agent, ai) => {
                      const duration = at.agent_durations?.[agent];
                      const totalMs = at.total_latency_ms || 1;
                      const pct = duration ? (duration / totalMs) * 100 : 0;

                      return (
                        <div key={`${agent}-${ai}`} className="relative flex items-start pb-3">
                          {/* Timeline line */}
                          {ai < at.agent_trace.length - 1 && (
                            <div className="absolute left-[7px] top-6 bottom-0 w-0.5 bg-slate-700" />
                          )}

                          {/* Dot */}
                          <div
                            className="w-3.5 h-3.5 rounded-full shrink-0 mt-1 mr-3 z-10"
                            style={{ backgroundColor: agentColors[agent] || "#64748b" }}
                          />

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between">
                              <span className="text-sm font-medium text-slate-200">{agent}</span>
                              {duration != null && (
                                <span className="text-xs text-slate-500 font-mono">
                                  {duration.toFixed(0)}ms
                                </span>
                              )}
                            </div>

                            {/* Duration bar */}
                            {duration != null && (
                              <div className="mt-1 w-full bg-slate-800 rounded-full h-1.5">
                                <div
                                  className="h-1.5 rounded-full transition-all duration-500"
                                  style={{
                                    width: `${Math.max(pct, 2)}%`,
                                    backgroundColor: agentColors[agent] || "#64748b",
                                  }}
                                />
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}

                    {/* Total latency */}
                    <div className="ml-[22px] text-xs text-slate-500 mt-1">
                      总延迟: <span className="font-mono text-slate-400">{at.total_latency_ms?.toFixed(0)}ms</span>
                      {at.status !== "success" && (
                        <span className="text-red-400 ml-2">⚠️ {at.status}</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {/* Messages */}
              {trace.messages.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-slate-300 mb-3">💬 对话内容</h4>
                  <div className="space-y-2">
                    {trace.messages.map((m) => (
                      <div
                        key={m.id}
                        className={`p-3 rounded-lg text-sm ${
                          m.role === "user"
                            ? "bg-blue-900/20 border border-blue-800/30"
                            : m.role === "system"
                              ? "bg-red-900/20 border border-red-800/30"
                              : "bg-slate-800/50 border border-slate-700/50"
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${
                            m.role === "user" ? "bg-blue-800/40 text-blue-300" :
                            m.role === "system" ? "bg-red-800/40 text-red-300" :
                            "bg-slate-700 text-slate-400"
                          }`}>
                            {m.role === "user" ? "用户" : m.role === "system" ? "系统" : m.agent_role || "Agent"}
                          </span>
                          {m.route_type && (
                            <span className="text-xs text-slate-500">{m.route_type}</span>
                          )}
                        </div>
                        <p className="text-slate-300 whitespace-pre-wrap break-words line-clamp-3">
                          {m.content}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-8 text-slate-500">
              <p>无法加载链路数据</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
