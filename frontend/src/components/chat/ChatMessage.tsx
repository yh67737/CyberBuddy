"use client";

import { Message } from "@/lib/types";

interface ChatMessageProps {
  message: Message;
  isStreaming?: boolean;
}

const routeColors: Record<string, string> = {
  CHAT: "border-slate-600",
  CONSULT: "border-green-600",
  RISK: "border-red-600",
};

const routeLabels: Record<string, string> = {
  CHAT: "💬 普通",
  CONSULT: "🟢 排障",
  RISK: "🔴 安全",
};

export function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const borderColor = message.routeType ? routeColors[message.routeType] || "" : "";

  return (
    <div className={`message-enter flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-blue-600 text-white rounded-br-md"
            : isSystem
              ? "bg-red-900/60 border border-red-500/40 text-red-100"
              : `bg-slate-800/80 border ${borderColor || "border-slate-700/50"} rounded-bl-md`
        } ${isStreaming ? "typing-cursor" : ""}`}
      >
        {/* Agent Role Badge */}
        {message.agentRole && !isUser && (
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-blue-400 bg-blue-400/10 px-2 py-0.5 rounded">
              {message.agentRole}
            </span>
            {message.routeType && (
              <span className="text-xs text-slate-500">
                {routeLabels[message.routeType] || message.routeType}
              </span>
            )}
          </div>
        )}

        {/* Content — basic markdown-style rendering */}
        <div className="text-sm leading-relaxed whitespace-pre-wrap">
          {message.content}
        </div>

        {/* Timestamp */}
        <div className="text-xs text-slate-500 mt-1 text-right">
          {message.timestamp.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
        </div>
      </div>
    </div>
  );
}
