"use client";

import { useState, useEffect, useCallback } from "react";
import { useDashboardWebSocket } from "@/hooks/useDashboardWebSocket";
import { IncidentCard } from "@/components/dashboard/IncidentCard";
import { TaskStatusPanel } from "@/components/dashboard/TaskStatusPanel";
import { SecurityIncident, AsyncTask } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function DashboardPage() {
  const [incidents, setIncidents] = useState<SecurityIncident[]>([]);
  const [tasks, setTasks] = useState<AsyncTask[]>([]);
  const [alert, setAlert] = useState<string | null>(null);
  const [onlineUsers, setOnlineUsers] = useState(0);

  // ── Initial fetch from REST API on mount ─────────────────────────
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

  // ── Real-time WebSocket updates ──────────────────────────────────
  const { isConnected } = useDashboardWebSocket({
    onIncident: (incident: SecurityIncident) => {
      setIncidents((prev) => [incident, ...prev]);
      setAlert(`🚨 新安全事件: ${incident.title}`);
      setTimeout(() => setAlert(null), 5000);
    },
    onIncidentUpdate: () => {
      // Refresh the incidents list when an update arrives
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

  // ── Computed stats ──────────────────────────────────────────────
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
        <div className="bg-red-900/50 border border-red-500/50 rounded-lg px-4 py-3 text-red-200 animate-pulse">
          {alert}
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-5 gap-4">
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
          <h2 className="text-lg font-semibold">安全事件列表</h2>
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
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
      <p className="text-sm text-slate-400">{label}</p>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
    </div>
  );
}
