"use client";

import { AsyncTask } from "@/lib/types";

interface TaskStatusPanelProps {
  tasks: AsyncTask[];
}

const statusStyles: Record<string, string> = {
  pending: "text-yellow-400",
  running: "text-blue-400",
  completed: "text-green-400",
  failed: "text-red-400",
  dead_letter: "text-orange-400 line-through",
};

const statusLabels: Record<string, string> = {
  pending: "⏳ 等待中",
  running: "🔄 执行中",
  completed: "✅ 已完成",
  failed: "❌ 失败",
  dead_letter: "💀 死信",
};

export function TaskStatusPanel({ tasks }: TaskStatusPanelProps) {
  if (tasks.length === 0) {
    return (
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-8 text-center text-slate-500">
        <div className="text-3xl mb-2">📋</div>
        <p className="text-sm">暂无异步任务</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {tasks.map((task) => (
        <div
          key={task.id}
          className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3 text-sm"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium text-slate-200">{task.toolName}</span>
            <span className={`text-xs ${statusStyles[task.status] || ""}`}>
              {statusLabels[task.status] || task.status}
            </span>
          </div>
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>重试: {task.retryCount} 次</span>
            <span>{new Date(task.createdAt).toLocaleTimeString("zh-CN")}</span>
          </div>
          {task.errorMessage && (
            <p className="text-xs text-red-400 mt-1 truncate">{task.errorMessage}</p>
          )}
        </div>
      ))}
    </div>
  );
}
