"use client";

import { Message } from "@/lib/types";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

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
  CHAT: "💬 普通咨询",
  CONSULT: "🟢 排障诊断",
  RISK: "🔴 安全事件",
};

/** Custom Markdown renderers for agent messages */
const markdownComponents: Partial<Components> = {
  // Code blocks — with copy button
  pre: ({ children }) => (
    <div className="relative group my-3">
      <pre className="bg-slate-900 border border-slate-700 rounded-lg p-4 overflow-x-auto text-sm leading-relaxed">
        {children}
      </pre>
      <button
        onClick={(e) => {
          const text = (e.currentTarget.previousElementSibling as HTMLElement)?.textContent || "";
          navigator.clipboard.writeText(text);
        }}
        className="absolute top-2 right-2 px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded opacity-0 group-hover:opacity-100 transition-opacity"
      >
        📋 复制
      </button>
    </div>
  ),
  code: ({ className, children, ...props }) => {
    // Inline code vs block code
    const isInline = !className;
    if (isInline) {
      return (
        <code
          className="bg-slate-700/50 text-blue-300 px-1.5 py-0.5 rounded text-xs font-mono"
          {...props}
        >
          {children}
        </code>
      );
    }
    return (
      <code className={`${className || ""} text-sm font-mono`} {...props}>
        {children}
      </code>
    );
  },
  // Styled tables
  table: ({ children }) => (
    <div className="overflow-x-auto my-3">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-slate-800">{children}</thead>
  ),
  th: ({ children }) => (
    <th className="border border-slate-700 px-3 py-2 text-left font-medium text-slate-300">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-slate-700 px-3 py-2 text-slate-400">{children}</td>
  ),
  // External links open in new tab
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-400 underline hover:text-blue-300"
    >
      {children}
    </a>
  ),
  // Blockquote for tips/warnings
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-blue-500 pl-4 my-2 text-slate-400 italic">
      {children}
    </blockquote>
  ),
  // Lists
  ul: ({ children }) => <ul className="list-disc list-inside my-2 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal list-inside my-2 space-y-1">{children}</ol>,
};

export function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const borderColor = message.routeType ? routeColors[message.routeType] || "" : "";

  return (
    <div className={`message-enter flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-blue-600 text-white rounded-br-md"
            : isSystem
              ? "bg-red-900/60 border border-red-500/40 text-red-100 rounded-bl-md"
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
              <span className="text-xs text-slate-400">
                {routeLabels[message.routeType] || message.routeType}
              </span>
            )}
          </div>
        )}

        {/* Content */}
        {isUser ? (
          // User messages — plain text (no markdown for safety)
          <div className="text-sm leading-relaxed whitespace-pre-wrap break-words">
            {message.content}
          </div>
        ) : isSystem ? (
          // System alerts — plain text with icon
          <div className="text-sm leading-relaxed whitespace-pre-wrap break-words">
            {message.content}
          </div>
        ) : (
          // Agent messages — full Markdown rendering
          <div className="text-sm leading-relaxed prose prose-invert max-w-none [&_p]:my-1.5 break-words">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* Attachments (future: image display) */}
        {message.attachments && message.attachments.length > 0 && (
          <div className="flex gap-2 mt-2 flex-wrap">
            {message.attachments.map((url, i) => (
              <img
                key={i}
                src={url}
                alt={`attachment-${i}`}
                className="max-w-[200px] max-h-[200px] rounded-lg object-cover border border-slate-600"
              />
            ))}
          </div>
        )}

        {/* Timestamp */}
        <div className="text-xs text-slate-500 mt-2 text-right">
          {message.timestamp.toLocaleTimeString("zh-CN", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </div>
      </div>
    </div>
  );
}
