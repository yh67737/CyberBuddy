"use client";

import { useState, useRef, useEffect } from "react";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { ChatInput } from "@/components/chat/ChatInput";
import { AgentStatusBar } from "@/components/chat/AgentStatusBar";
import { Sidebar } from "@/components/chat/Sidebar";
import { useWebSocket } from "@/hooks/useWebSocket";
import { Message, AgentState } from "@/lib/types";

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [isSecurityMode, setIsSecurityMode] = useState(false);
  const [currentStreaming, setCurrentStreaming] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { sendMessage, isConnected } = useWebSocket({
    sessionId: "demo-session",
    onAgentState: (state: AgentState) => setAgentState(state),
    onToken: (token: string) => {
      setCurrentStreaming((prev) => prev + token);
    },
    onMessageComplete: (routeType: string) => {
      if (routeType === "RISK") {
        setIsSecurityMode(true);
      }
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "agent",
          content: currentStreaming,
          agentRole: agentState?.agent || "Agent",
          routeType,
          timestamp: new Date(),
        },
      ]);
      setCurrentStreaming("");
    },
    onSecurityAlert: (alert: { level: string; message: string }) => {
      setIsSecurityMode(true);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          content: `🔴 ${alert.message}`,
          agentRole: "SecurityGuardian",
          routeType: "RISK",
          timestamp: new Date(),
        },
      ]);
    },
  });

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentStreaming]);

  const handleSend = (content: string) => {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    sendMessage({ type: "chat", content });
  };

  return (
    <div
      className={`flex-1 flex ${isSecurityMode ? "security-mode" : ""}`}
    >
      {/* Session Sidebar */}
      <Sidebar />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Agent Status Bar */}
        <AgentStatusBar agentState={agentState} isSecurityMode={isSecurityMode} />

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
          {messages.length === 0 && !currentStreaming && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-3 text-slate-500">
                <div className="text-5xl">🛡️</div>
                <p className="text-lg">欢迎使用 CyberBuddy 智能 IT 助手</p>
                <p className="text-sm">输入您的问题，Agent 将为您提供智能支持</p>
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
