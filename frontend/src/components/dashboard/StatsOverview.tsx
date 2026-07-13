"use client";

import { useEffect, useState, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend,
} from "recharts";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface StatsData {
  window_hours: number;
  total_calls: number;
  total_tokens: number;
  avg_latency_ms: number;
  error_count: number;
  route_distribution: Record<string, number>;
  active_users: number;
  hourly_breakdown: Array<{
    hour: string;
    calls: number;
    tokens: number;
    errors: number;
    avg_latency_ms: number;
  }>;
}

export function StatsOverview() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async (h: number) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/dashboard/stats?hours=${h}`);
      if (!res.ok) return;
      const data = await res.json();
      setStats(data);
    } catch {
      // API unavailable
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats(hours);
  }, [hours, fetchStats]);

  const routeData = stats
    ? Object.entries(stats.route_distribution).map(([name, value]) => ({
        name: name === "CHAT" ? "💬 普通咨询" : name === "CONSULT" ? "🟢 排障" : name === "RISK" ? "🔴 安全" : name,
        value,
        fill: name === "CHAT" ? "#94a3b8" : name === "CONSULT" ? "#22c55e" : "#ef4444",
      }))
    : [];

  const errorRate = stats ? (stats.total_calls > 0 ? ((stats.error_count / stats.total_calls) * 100).toFixed(1) : "0.0") : "0.0";

  return (
    <div className="space-y-6">
      {/* Time window selector */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">📊 平台运营统计</h2>
        <div className="flex gap-2">
          {[1, 6, 24, 72, 168].map((h) => (
            <button
              key={h}
              onClick={() => setHours(h)}
              className={`px-3 py-1 text-xs rounded-lg transition-colors ${
                hours === h
                  ? "bg-blue-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:bg-slate-700"
              }`}
            >
              {h >= 24 ? `${h / 24}d` : `${h}h`}
            </button>
          ))}
        </div>
      </div>

      {/* Stats cards */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="w-6 h-6 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
        </div>
      ) : stats ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MiniCard label="API 总调用" value={stats.total_calls.toLocaleString()} color="text-blue-400" />
            <MiniCard label="Token 总消耗" value={stats.total_tokens.toLocaleString()} color="text-purple-400" />
            <MiniCard label="平均延迟" value={`${stats.avg_latency_ms.toFixed(0)}ms`} color="text-yellow-400" />
            <MiniCard label="错误率" value={`${errorRate}%`} color={parseFloat(errorRate) > 5 ? "text-red-400" : "text-green-400"} />
          </div>

          {/* Hourly call volume */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
            <h3 className="text-sm font-medium text-slate-300 mb-4">📈 每小时 API 调用量</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={stats.hourly_breakdown}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="hour" tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <Tooltip
                  contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", fontSize: "12px" }}
                  labelStyle={{ color: "#e2e8f0" }}
                />
                <Bar dataKey="calls" fill="#3b82f6" radius={[3, 3, 0, 0]} name="调用次数" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Latency + Error trend */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
            <h3 className="text-sm font-medium text-slate-300 mb-4">📉 延迟 & 错误趋势</h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={stats.hourly_breakdown}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="hour" tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <YAxis yAxisId="left" tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <Tooltip
                  contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", fontSize: "12px" }}
                />
                <Legend wrapperStyle={{ fontSize: "12px" }} />
                <Line yAxisId="left" type="monotone" dataKey="avg_latency_ms" stroke="#eab308" name="平均延迟(ms)" strokeWidth={2} dot={false} />
                <Line yAxisId="right" type="monotone" dataKey="errors" stroke="#ef4444" name="错误数" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Route distribution */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
            <h3 className="text-sm font-medium text-slate-300 mb-4">🎯 路由分布</h3>
            <div className="flex gap-6 items-center">
              <div className="flex-1 space-y-3">
                {routeData.map((r) => (
                  <div key={r.name}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-slate-300">{r.name}</span>
                      <span className="text-slate-400">{r.value} 次</span>
                    </div>
                    <div className="w-full bg-slate-700 rounded-full h-2">
                      <div
                        className="h-2 rounded-full transition-all duration-500"
                        style={{
                          width: `${stats.total_calls > 0 ? (r.value / stats.total_calls) * 100 : 0}%`,
                          backgroundColor: r.fill,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <div className="w-32 h-32 relative shrink-0">
                {/* Simple donut */}
                <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
                  {routeData.map((r, i) => {
                    const total = routeData.reduce((s, d) => s + d.value, 0);
                    const pct = total > 0 ? (r.value / total) * 100 : 0;
                    const offset = routeData.slice(0, i).reduce((s, d) => (total > 0 ? (d.value / total) * 100 : 0), 0);
                    const circumference = 2 * Math.PI * 40;
                    return (
                      <circle
                        key={r.name}
                        cx="50" cy="50" r="40"
                        fill="none"
                        stroke={r.fill}
                        strokeWidth="12"
                        strokeDasharray={`${(pct / 100) * circumference} ${circumference}`}
                        strokeDashoffset={-((offset / 100) * circumference)}
                        className="transition-all duration-700"
                      />
                    );
                  })}
                </svg>
                <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-400">
                  {stats.total_calls}
                </div>
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="text-center py-12 text-slate-500">
          <p>暂无统计数据</p>
          <p className="text-xs mt-1">API 调用后将自动生成</p>
        </div>
      )}
    </div>
  );
}

function MiniCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
    </div>
  );
}
