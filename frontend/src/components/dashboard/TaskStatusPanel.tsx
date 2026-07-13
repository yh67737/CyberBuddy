"use client";

import { AsyncTask } from "@/lib/types";

interface TaskStatusPanelProps {
  tasks: AsyncTask[];
}

const statusStyles: Record<string, string> = {
  pending: "text-yellow-400",
  running: "text-blue-400 animate-pulse",
  completed: "text-green-400",
  failed: "text-red-400",
  dead_letter: "text-orange-400",
};

const statusLabels: Record<string, string> = {
  pending: "⏳ 等待中",
  running: "🔄 执行中",
  completed: "✅ 已完成",
  failed: "❌ 失败",
  dead_letter: "💀 死信",
};

const statusBarColor: Record<string, string> = {
  pending: "bg-yellow-600",
  running: "bg-blue-500",
  completed: "bg-green-500",
  failed: "bg-red-500",
  dead_letter: "bg-orange-600",
};

export function TaskStatusPanel({ tasks }: TaskStatusPanelProps) {
  if (tasks.length === 0) {
    return (
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-8 text-center text-slate-500">
        <div className="text-3xl mb-2">📋</div>
        <p className="text-sm">暂无异步任务</p>
        <p className="text-xs mt-1 text-slate-600">MCP 工具调用后将在此显示</p>
      </div>
    );
  }

  // Count by status
  const counts = tasks.reduce(
    (acc, t) => {
      acc[t.status] = (acc[t.status] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );

  return (
    <div className="space-y-3">
      {/* Summary bar */}
      <div className="flex gap-1 h-1.5 rounded-full overflow-hidden">
        {(Object.keys(statusLabels) as Array<keyof typeof statusLabels>).map((s) => {
          const count = counts[s] || 0;
          if (count === 0) return null;
          return (
            <div
              key={s}
              className={`h-full ${statusBarColor[s]}`}
              style={{ width: `${(count / tasks.length) * 100}%` }}
              title={`${statusLabels[s]}: ${count}`}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-3 text-xs text-slate-500">
        {Object.entries(counts).map(([status, count]) => (
          <span key={status}>
            {statusLabels[status]}: <span className="text-slate-300 font-medium">{count}</span>
          </span>
        ))}
      </div>

      {/* Task list */}
      <div className="space-y-2">
        {tasks.slice(0, 20).map((task) => (
          <div
            key={task.id}
            className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3 text-sm hover:bg-slate-800/80 transition-colors"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-200 text-xs">{task.toolName}</span>
                <span className="text-[10px] text-slate-600 font-mono">{task.id.slice(0, 8)}</span>
              </div>
              <span className={`text-xs font-medium ${statusStyles[task.status] || ""}`}>
                {statusLabels[task.status] || task.status}
              </span>
            </div>

            {/* Timing */}
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span>
                创建: {new Date(task.createdAt).toLocaleTimeString("zh-CN")}
              </span>
              {task.completedAt && (
                <span>
                  完成: {new Date(task.completedAt).toLocaleTimeString("zh-CN")}
                </span>
              )}
            </div>

            {/* Retry info */}
            <div className="text-xs text-slate-500">
              重试: <span className={task.retryCount > 0 ? "text-yellow-400" : "text-slate-500"}>
                {task.retryCount} 次
              </span>
            </div>

            {/* Error message */}
            {task.errorMessage && (
              <div className="mt-2 bg-red-950/40 border border-red-900/50 rounded-lg p-2 text-xs text-red-300 font-mono break-all">
                {task.errorMessage}
              </div>
            )}
          </div>
        ))}
        {tasks.length > 20 && (
          <p className="text-xs text-slate-600 text-center py-2">
            还有 {tasks.length - 20} 条任务...
          </p>
        )}
      </div>
    </div>
  );
}
