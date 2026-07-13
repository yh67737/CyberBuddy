"use client";

import { useEffect, useState, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface UsageLog {
  id: string;
  user_id: string;
  session_id: string;
  route_type: string | null;
  agent_trace: string[];
  agent_durations: Record<string, number>;
  llm_tokens: number;
  total_latency_ms: number;
  status: string;
  error_message?: string | null;
  created_at: string;
}

interface UsageLogTableProps {
  onSelectTrace?: (log: UsageLog) => void;
}

const routeBadge: Record<string, string> = {
  CHAT: "bg-slate-600",
  CONSULT: "bg-green-600",
  RISK: "bg-red-600",
};

const routeLabel: Record<string, string> = {
  CHAT: "💬",
  CONSULT: "🟢",
  RISK: "🔴",
};

export function UsageLogTable({ onSelectTrace }: UsageLogTableProps) {
  const [logs, setLogs] = useState<UsageLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterRoute, setFilterRoute] = useState<string>("");
  const [filterUser, setFilterUser] = useState("");

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterRoute) params.set("route_type", filterRoute);
      params.set("limit", "100");
      const res = await fetch(`${API_URL}/api/v1/dashboard/usage?${params}`);
      if (!res.ok) return;
      const data = await res.json();
      setLogs(data);
    } catch {
      // API unavailable
    } finally {
      setLoading(false);
    }
  }, [filterRoute]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Client-side user filter
  const filtered = filterUser
    ? logs.filter((l) => l.user_id.toLowerCase().includes(filterUser.toLowerCase()))
    : logs;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">🔍 对话记录查询</h2>
        <div className="flex gap-2">
          <select
            value={filterRoute}
            onChange={(e) => setFilterRoute(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-300"
          >
            <option value="">全部路由</option>
            <option value="CHAT">💬 CHAT</option>
            <option value="CONSULT">🟢 CONSULT</option>
            <option value="RISK">🔴 RISK</option>
          </select>
          <input
            type="text"
            value={filterUser}
            onChange={(e) => setFilterUser(e.target.value)}
            placeholder="筛选用户..."
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-300 w-32
                       focus:outline-none focus:ring-1 focus:ring-blue-500/50"
          />
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-8">
          <div className="w-5 h-5 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-8 text-center text-slate-500">
          <p>暂无使用记录</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 border-b border-slate-800">
                <th className="pb-2 font-medium">时间</th>
                <th className="pb-2 font-medium">用户</th>
                <th className="pb-2 font-medium">路由</th>
                <th className="pb-2 font-medium">Agent 链路</th>
                <th className="pb-2 font-medium text-right">Token</th>
                <th className="pb-2 font-medium text-right">延迟</th>
                <th className="pb-2 font-medium text-right">状态</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {filtered.map((log) => (
                <tr
                  key={log.id}
                  onClick={() => onSelectTrace?.(log)}
                  className="hover:bg-slate-800/30 cursor-pointer transition-colors group"
                >
                  <td className="py-2 pr-3 text-xs text-slate-400 whitespace-nowrap">
                    {new Date(log.created_at).toLocaleString("zh-CN", {
                      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                    })}
                  </td>
                  <td className="py-2 pr-3 text-xs text-slate-300 font-mono">
                    {log.user_id.slice(0, 8)}
                  </td>
                  <td className="py-2 pr-3">
                    {log.route_type ? (
                      <span className={`text-xs px-1.5 py-0.5 rounded text-white ${routeBadge[log.route_type] || "bg-slate-600"}`}>
                        {routeLabel[log.route_type] || ""} {log.route_type}
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <div className="flex items-center gap-1 flex-wrap">
                      {log.agent_trace?.map((agent, i) => (
                        <span key={i} className="text-[11px] text-slate-500">
                          {agent}
                          {i < (log.agent_trace?.length || 0) - 1 && (
                            <span className="text-slate-600 ml-1">→</span>
                          )}
                        </span>
                      )) || <span className="text-slate-600">—</span>}
                    </div>
                  </td>
                  <td className="py-2 pr-3 text-xs text-purple-400 text-right tabular-nums">
                    {log.llm_tokens?.toLocaleString() || "—"}
                  </td>
                  <td className="py-2 pr-3 text-xs text-slate-400 text-right tabular-nums font-mono">
                    {log.total_latency_ms?.toFixed(0)}ms
                  </td>
                  <td className="py-2 text-right">
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded ${
                        log.status === "success"
                          ? "bg-green-900/40 text-green-400"
                          : "bg-red-900/40 text-red-400"
                      }`}
                    >
                      {log.status === "success" ? "✅" : "❌"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="text-xs text-slate-600 text-right">{filtered.length} 条记录</div>
    </div>
  );
}
