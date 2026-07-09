"use client";

import { useState, useEffect } from "react";
import { useDashboardWebSocket } from "@/hooks/useDashboardWebSocket";
import { IncidentCard } from "@/components/dashboard/IncidentCard";
import { TaskStatusPanel } from "@/components/dashboard/TaskStatusPanel";
import { SecurityIncident, AsyncTask } from "@/lib/types";

export default function DashboardPage() {
  const [incidents, setIncidents] = useState<SecurityIncident[]>([]);
  const [tasks, setTasks] = useState<AsyncTask[]>([]);
  const [alert, setAlert] = useState<string | null>(null);

  const { isConnected } = useDashboardWebSocket({
    onIncident: (incident: SecurityIncident) => {
      setIncidents((prev) => [incident, ...prev]);
      setAlert(`🚨 新安全事件: ${incident.title}`);
      setTimeout(() => setAlert(null), 5000);
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
  });

  // Stats
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
        <div
          className={`flex items-center gap-2 text-sm ${isConnected ? "text-green-400" : "text-red-400"}`}
        >
          <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-400 animate-pulse" : "bg-red-400"}`} />
          {isConnected ? "WebSocket 已连接" : "WebSocket 断开"}
        </div>
      </div>

      {/* Alert Banner */}
      {alert && (
        <div className="bg-red-900/50 border border-red-500/50 rounded-lg px-4 py-3 text-red-200 animate-pulse">
          {alert}
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <StatCard label="待处理事件" value={openIncidents} color="text-yellow-400" />
        <StatCard label="严重事件" value={criticalIncidents} color="text-red-400" />
        <StatCard label="死信任务" value={deadLetterTasks} color="text-orange-400" />
        <StatCard label="总事件数" value={incidents.length} color="text-blue-400" />
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
