"use client";

import { useState, useEffect, useCallback } from "react";
import { useDashboardWebSocket } from "@/hooks/useDashboardWebSocket";
import { IncidentCard } from "@/components/dashboard/IncidentCard";
import { TaskStatusPanel } from "@/components/dashboard/TaskStatusPanel";
import { StatsOverview } from "@/components/dashboard/StatsOverview";
import { UsageLogTable } from "@/components/dashboard/UsageLogTable";
import { AgentTraceTimeline } from "@/components/dashboard/AgentTraceTimeline";
import { UserActivityPanel } from "@/components/dashboard/UserActivityPanel";
import { SecurityIncident, AsyncTask } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type TabKey = "monitoring" | "audit" | "stats";

const tabs: { key: TabKey; label: string; icon: string }[] = [
  { key: "monitoring", label: "安全监控", icon: "🔴" },
  { key: "audit", label: "用户审计", icon: "🔍" },
  { key: "stats", label: "运营统计", icon: "📊" },
];

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("monitoring");
  const [incidents, setIncidents] = useState<SecurityIncident[]>([]);
  const [tasks, setTasks] = useState<AsyncTask[]>([]);
  const [alert, setAlert] = useState<string | null>(null);
  const [onlineUsers, setOnlineUsers] = useState(0);
  const [traceSessionId, setTraceSessionId] = useState<string | null>(null);

  // ── Initial fetch on mount ──────────────────────────────────────
  useEffect(() => {
    fetchIncidents();
    fetchTasks();
  }, []);

  const fetchIncidents = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/dashboard/incidents?limit=50`);
      if (!res.ok) return;
      const data = await res.json();
      setIncidents(
        data.map((i: Record<string, unknown>) => ({
          id: i.id as string,
          severity: (i.severity as SecurityIncident["severity"]) || "low",
          title: (i.title as string) || "",
          description: (i.description as string) || "",
          entities: (i.entities as Record<string, string>) || {},
          agentSummary: (i.agent_summary as string) || "",
          status: (i.status as SecurityIncident["status"]) || "open",
          createdAt: (i.created_at as string) || new Date().toISOString(),
        }))
      );
    } catch {
      // DB unavailable — will populate via WebSocket
    }
  }, []);

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/dashboard/tasks?limit=50`);
      if (!res.ok) return;
      const data = await res.json();
      setTasks(
        data.map((t: Record<string, unknown>) => ({
          id: t.id as string,
          toolName: (t.tool_name as string) || "",
          status: (t.status as AsyncTask["status"]) || "pending",
          createdAt: (t.created_at as string) || new Date().toISOString(),
          completedAt: t.completed_at as string | undefined,
          retryCount: (t.retry_count as number) || 0,
          errorMessage: t.error_message as string | undefined,
        }))
      );
    } catch {
      // DB unavailable
    }
  }, []);

  // ── Real-time WebSocket updates ─────────────────────────────────
  const { isConnected } = useDashboardWebSocket({
    onIncident: (incident: SecurityIncident) => {
      setIncidents((prev) => [incident, ...prev]);
      setAlert(`🚨 新安全事件: ${incident.title}`);
      setTimeout(() => setAlert(null), 5000);
    },
    onIncidentUpdate: () => {
      fetchIncidents();
    },
    onTaskUpdate: (task: AsyncTask) => {
      setTasks((prev) => {
        const idx = prev.findIndex((t) => t.id === task.id);
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = task;
          return updated;
        }
        return [task, ...prev];
      });
    },
    onOnlineCount: (count: number) => {
      setOnlineUsers(count);
    },
  });

  // ── Computed stats for monitoring tab ──────────────────────────
  const openIncidents = incidents.filter((i) => i.status === "open").length;
  const criticalIncidents = incidents.filter((i) => i.severity === "critical").length;
  const deadLetterTasks = tasks.filter((t) => t.status === "dead_letter").length;

  return (
    <div className="flex-1 p-6 max-w-7xl mx-auto w-full space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">安全运维工作台</h1>
          <p className="text-sm text-slate-400 mt-1">
            SecOps Dashboard — 实时安全监控与工单管理
          </p>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-slate-400">🟢 在线: {onlineUsers}</span>
          <div
            className={`flex items-center gap-2 ${isConnected ? "text-green-400" : "text-red-400"}`}
          >
            <span
              className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-400 animate-pulse" : "bg-red-400"}`}
            />
            {isConnected ? "WebSocket 已连接" : "WebSocket 断开"}
          </div>
        </div>
      </div>

      {/* Alert Banner */}
      {alert && (
        <div className="bg-red-900/50 border border-red-500/50 rounded-lg px-4 py-3 text-red-200 animate-pulse flex items-center gap-2">
          <span>🚨</span>
          {alert}
          <button onClick={() => setAlert(null)} className="ml-auto text-red-400 hover:text-red-300">✕</button>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-1 bg-slate-800/50 rounded-xl p-1 w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? "bg-blue-600 text-white shadow"
                : "text-slate-400 hover:text-white hover:bg-slate-700/50"
            }`}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* ── Tab: 安全监控 ──────────────────────────────────────── */}
      {activeTab === "monitoring" && (
        <div className="space-y-6">
          {/* Stats Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
            <StatCard label="待处理事件" value={openIncidents} color="text-yellow-400" />
            <StatCard label="严重事件" value={criticalIncidents} color="text-red-400" />
            <StatCard label="死信任务" value={deadLetterTasks} color="text-orange-400" />
            <StatCard label="总事件数" value={incidents.length} color="text-blue-400" />
            <StatCard label="在线用户" value={onlineUsers} color="text-green-400" />
          </div>

          {/* Main Content */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Incidents Panel */}
            <div className="lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">安全事件列表</h2>
                <button
                  onClick={fetchIncidents}
                  className="text-xs text-slate-500 hover:text-white px-2 py-1 rounded bg-slate-800"
                >
                  🔄 刷新
                </button>
              </div>
              {incidents.length === 0 ? (
                <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-12 text-center text-slate-500">
                  <div className="text-4xl mb-3">✅</div>
                  <p>暂无安全事件</p>
                  <p className="text-sm mt-1">系统运行正常</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {incidents.map((incident) => (
                    <IncidentCard key={incident.id} incident={incident} />
                  ))}
                </div>
              )}
            </div>

            {/* Task Status Panel */}
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">异步任务状态</h2>
              <TaskStatusPanel tasks={tasks} />
            </div>
          </div>
        </div>
      )}

      {/* ── Tab: 用户审计 ──────────────────────────────────────── */}
      {activeTab === "audit" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Usage Logs */}
          <div className="lg:col-span-2">
            <UsageLogTable
              onSelectTrace={(log) => setTraceSessionId(log.session_id)}
            />
          </div>

          {/* User Activity */}
          <div className="lg:col-span-2">
            <UserActivityPanel
              onSelectTrace={(sessionId) => setTraceSessionId(sessionId)}
            />
          </div>
        </div>
      )}

      {/* ── Tab: 运营统计 ──────────────────────────────────────── */}
      {activeTab === "stats" && <StatsOverview />}

      {/* Agent Trace Modal */}
      {traceSessionId && (
        <AgentTraceTimeline
          sessionId={traceSessionId}
          onClose={() => setTraceSessionId(null)}
        />
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4 hover:bg-slate-800/70 transition-colors">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
    </div>
  );
}
