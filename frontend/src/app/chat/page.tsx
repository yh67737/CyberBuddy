"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { ChatInput } from "@/components/chat/ChatInput";
import { AgentStatusBar } from "@/components/chat/AgentStatusBar";
import { Sidebar } from "@/components/chat/Sidebar";
import { useWebSocket } from "@/hooks/useWebSocket";
import { Message, AgentState } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ChatPage() {
  const [sessionId, setSessionId] = useState(() => `session-${Date.now()}`);
  const [messages, setMessages] = useState<Message[]>([]);
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [isSecurityMode, setIsSecurityMode] = useState(false);
  const [currentStreaming, setCurrentStreaming] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    sendMessage,
    isConnected,
  } = useWebSocket({
    sessionId,
    onAgentState: (state: AgentState) => setAgentState(state),
    onToken: (token: string) => {
      setCurrentStreaming((prev) => prev + token);
    },
    onMessageComplete: (routeType: string) => {
      if (routeType === "RISK") {
        setIsSecurityMode(true);
      }
      setCurrentStreaming((prev) => {
        if (prev) {
          setMessages((msgs) => [
            ...msgs,
            {
              id: crypto.randomUUID(),
              role: "agent",
              content: prev,
              agentRole: agentState?.agent || "Agent",
              routeType,
              timestamp: new Date(),
            },
          ]);
        }
        return "";
      });
    },
    onSecurityAlert: (alert: { level: string; message: string }) => {
      setIsSecurityMode(true);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          content: `🚨 ${alert.message}`,
          agentRole: "SecurityGuardian",
          routeType: "RISK",
          timestamp: new Date(),
        },
      ]);
    },
  });

  // ── Load messages when selecting an existing session ────────────
  const loadSessionMessages = useCallback(async (sid: string) => {
    setLoadingHistory(true);
    setMessages([]);
    setCurrentStreaming("");
    try {
      const res = await fetch(`${API_URL}/api/v1/sessions/${sid}/messages`);
      if (!res.ok) return;
      const data = await res.json();
      const loaded: Message[] = data.map(
        (m: Record<string, unknown>) => ({
          id: m.id as string,
          role: (m.role as Message["role"]) || "agent",
          content: m.content as string,
          agentRole: m.agent_role as string | undefined,
          routeType: m.route_type as string | undefined,
          timestamp: new Date(m.created_at as string),
        })
      );
      setMessages(loaded);

      // Check if any message has RISK route
      if (loaded.some((m) => m.routeType === "RISK")) {
        setIsSecurityMode(true);
      }
    } catch {
      // API unavailable — silent
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentStreaming]);

  const handleSend = (content: string, attachments?: string[]) => {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      attachments,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    sendMessage({ type: "chat", content, attachments });
  };

  const handleNewSession = useCallback(() => {
    setSessionId(`session-${Date.now()}`);
    setMessages([]);
    setCurrentStreaming("");
    setIsSecurityMode(false);
    setAgentState(null);
  }, []);

  const handleSelectSession = useCallback((id: string) => {
    setSessionId(id);
    setIsSecurityMode(false);
    setAgentState(null);
    loadSessionMessages(id);
  }, [loadSessionMessages]);

  return (
    <div className={`flex-1 flex ${isSecurityMode ? "ring-2 ring-red-500 ring-inset security-mode-active" : ""}`}>
      {/* Session Sidebar */}
      <Sidebar
        activeSessionId={sessionId}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Agent Status Bar */}
        <AgentStatusBar agentState={agentState} isSecurityMode={isSecurityMode} />

        {/* Security Mode Banner */}
        {isSecurityMode && (
          <div className="bg-red-950/60 border-b border-red-800 px-4 py-2 flex items-center gap-3 animate-pulse">
            <span className="text-lg">🚨</span>
            <div className="flex-1">
              <p className="text-sm font-semibold text-red-300">安全模式已激活</p>
              <p className="text-xs text-red-400/70">
                检测到安全威胁 — 已自动执行熔断预案，安全团队已收到通知
              </p>
            </div>
            <button
              onClick={() => setIsSecurityMode(false)}
              className="text-xs text-red-400 hover:text-red-300 bg-red-900/40 px-2 py-1 rounded border border-red-700"
            >
              确认解除
            </button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
          {loadingHistory && (
            <div className="flex items-center justify-center py-12">
              <div className="text-center text-slate-500">
                <div className="w-6 h-6 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin mx-auto mb-2" />
                <p className="text-sm">加载历史消息...</p>
              </div>
            </div>
          )}

          {!loadingHistory && messages.length === 0 && !currentStreaming && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-4 text-slate-500">
                <div className="text-6xl">🛡️</div>
                <p className="text-lg font-medium">欢迎使用 CyberBuddy 智能 IT 助手</p>
                <div className="text-sm space-y-1 max-w-md mx-auto">
                  <p>💬 日常 IT 问题咨询 — 直接提问即可</p>
                  <p>🔍 故障排障诊断 — 描述您遇到的具体问题</p>
                  <p>🛡️ 安全威胁检测 — 自动识别并响应安全事件</p>
                </div>
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}

          {/* Streaming message */}
          {currentStreaming && (
            <ChatMessage
              message={{
                id: "streaming",
                role: "agent",
                content: currentStreaming,
                agentRole: agentState?.agent || "Agent",
                timestamp: new Date(),
              }}
              isStreaming
            />
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <ChatInput
          onSend={handleSend}
          disabled={isSecurityMode}
          placeholder={
            isSecurityMode
              ? "🔴 安全模式已激活 — 请等待安全团队接管"
              : "输入您的 IT 问题..."
          }
        />

        {/* Connection status */}
        <div className="px-4 py-1 text-xs text-center text-slate-600">
          {isConnected ? "🟢 已连接" : "🔴 未连接"}
        </div>
      </div>
    </div>
  );
}
