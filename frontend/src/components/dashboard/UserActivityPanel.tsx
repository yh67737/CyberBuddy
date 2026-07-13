"use client";

import { useEffect, useState, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SessionInfo {
  id: string;
  title: string;
  route_type?: string;
  created_at: string;
  is_active: boolean;
}

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
  created_at: string;
}

interface UserActivity {
  user_id: string;
  sessions: SessionInfo[];
  recent_logs: UsageLog[];
}

interface UserActivityPanelProps {
  onSelectTrace?: (sessionId: string) => void;
}

export function UserActivityPanel({ onSelectTrace }: UserActivityPanelProps) {
  const [userId, setUserId] = useState("default-user");
  const [activity, setActivity] = useState<UserActivity | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchActivity = useCallback(async (uid: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/dashboard/users/${uid}/activity?limit=30`);
      if (!res.ok) return;
      const data = await res.json();
      setActivity(data);
    } catch {
      // API unavailable
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchActivity(userId);
  }, [userId, fetchActivity]);

  const totalTokens = activity?.recent_logs.reduce((s, l) => s + (l.llm_tokens || 0), 0) || 0;
  const avgLatency = activity?.recent_logs.length
    ? (activity.recent_logs.reduce((s, l) => s + (l.total_latency_ms || 0), 0) / activity.recent_logs.length).toFixed(0)
    : "—";
  const routeCounts = activity?.recent_logs.reduce((acc: Record<string, number>, l) => {
    const r = l.route_type || "UNKNOWN";
    acc[r] = (acc[r] || 0) + 1;
    return acc;
  }, {}) || {};

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">👤 用户行为审计</h2>
        <div className="flex gap-2 items-center">
          <input
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="输入用户 ID"
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-300 w-40
                       focus:outline-none focus:ring-1 focus:ring-blue-500/50 font-mono"
          />
          <button
            onClick={() => fetchActivity(userId)}
            className="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-500"
          >
            查询
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-8">
          <div className="w-5 h-5 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
        </div>
      ) : activity ? (
        <>
          {/* User stats cards */}
          <div className="grid grid-cols-4 gap-3">
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-blue-400">{activity.sessions.length}</p>
              <p className="text-xs text-slate-500 mt-1">会话数</p>
            </div>
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-purple-400">{activity.recent_logs.length}</p>
              <p className="text-xs text-slate-500 mt-1">调用次数</p>
            </div>
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-yellow-400">{totalTokens.toLocaleString()}</p>
              <p className="text-xs text-slate-500 mt-1">Token 消耗</p>
            </div>
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-green-400">{avgLatency}ms</p>
              <p className="text-xs text-slate-500 mt-1">平均延迟</p>
            </div>
          </div>

          {/* Route distribution for this user */}
          {Object.keys(routeCounts).length > 0 && (
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
              <h3 className="text-sm font-medium text-slate-300 mb-3">路由偏好</h3>
              <div className="flex gap-4">
                {Object.entries(routeCounts).map(([route, count]) => (
                  <div key={route} className="flex items-center gap-2">
                    <span className={`w-3 h-3 rounded-full ${
                      route === "CHAT" ? "bg-slate-400" :
                      route === "CONSULT" ? "bg-green-400" : "bg-red-400"
                    }`} />
                    <span className="text-sm text-slate-300">{route}</span>
                    <span className="text-sm text-slate-500">×{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sessions list */}
          <div>
            <h3 className="text-sm font-medium text-slate-300 mb-3">📋 用户会话</h3>
            {activity.sessions.length === 0 ? (
              <p className="text-sm text-slate-600">暂无会话记录</p>
            ) : (
              <div className="space-y-2">
                {activity.sessions.map((s) => (
                  <div
                    key={s.id}
                    onClick={() => onSelectTrace?.(s.id)}
                    className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3 flex items-center justify-between cursor-pointer hover:bg-slate-800/80 transition-colors"
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-slate-300 truncate">{s.title}</p>
                      <p className="text-xs text-slate-500 font-mono mt-0.5">
                        {s.id.slice(0, 12)}...
                      </p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      {s.route_type && (
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          s.route_type === "RISK" ? "bg-red-900/40 text-red-400" :
                          s.route_type === "CONSULT" ? "bg-green-900/40 text-green-400" :
                          "bg-slate-700 text-slate-400"
                        }`}>
                          {s.route_type}
                        </span>
                      )}
                      <span className="text-xs text-slate-500">
                        {new Date(s.created_at).toLocaleDateString("zh-CN")}
                      </span>
                      <span className="text-slate-500 text-sm">→</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent usage logs */}
          <div>
            <h3 className="text-sm font-medium text-slate-300 mb-3">📊 最近使用记录</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b border-slate-800">
                    <th className="pb-2 font-medium">时间</th>
                    <th className="pb-2 font-medium">路由</th>
                    <th className="pb-2 font-medium text-right">Token</th>
                    <th className="pb-2 font-medium text-right">延迟</th>
                    <th className="pb-2 font-medium">状态</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {activity.recent_logs.slice(0, 15).map((log) => (
                    <tr key={log.id}>
                      <td className="py-2 pr-3 text-xs text-slate-400 whitespace-nowrap">
                        {new Date(log.created_at).toLocaleString("zh-CN", {
                          month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                        })}
                      </td>
                      <td className="py-2 pr-3">
                        <span className="text-xs text-slate-500">{log.route_type || "—"}</span>
                      </td>
                      <td className="py-2 pr-3 text-xs text-purple-400 text-right tabular-nums">
                        {log.llm_tokens?.toLocaleString() || "—"}
                      </td>
                      <td className="py-2 pr-3 text-xs text-slate-400 text-right font-mono tabular-nums">
                        {log.total_latency_ms?.toFixed(0)}ms
                      </td>
                      <td className="py-2">
                        <span className={`text-xs ${
                          log.status === "success" ? "text-green-400" : "text-red-400"
                        }`}>
                          {log.status === "success" ? "✅" : "❌"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <div className="text-center py-12 text-slate-500">
          <p className="text-4xl mb-3">👤</p>
          <p>输入用户 ID 查看行为数据</p>
        </div>
      )}
    </div>
  );
}
