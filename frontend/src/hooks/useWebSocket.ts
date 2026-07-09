"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { WSClientMessage, WSServerMessage, AgentState } from "@/lib/types";

interface UseWebSocketOptions {
  sessionId: string;
  onAgentState?: (state: AgentState) => void;
  onToken?: (token: string) => void;
  onMessageComplete?: (routeType: string) => void;
  onSecurityAlert?: (alert: { level: string; message: string }) => void;
}

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export function useWebSocket({
  sessionId,
  onAgentState,
  onToken,
  onMessageComplete,
  onSecurityAlert,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  const connect = useCallback(() => {
    const ws = new WebSocket(`${WS_BASE_URL}/api/v1/chat/ws/${sessionId}`);

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);
    ws.onerror = () => setIsConnected(false);

    ws.onmessage = (event) => {
      try {
        const data: WSServerMessage = JSON.parse(event.data);

        switch (data.type) {
          case "connected":
            break;
          case "agent_state":
            onAgentState?.({ agent: data.agent, status: data.status, isActive: true });
            break;
          case "token":
            onToken?.(data.content);
            break;
          case "message_complete":
            onMessageComplete?.(data.route_type);
            break;
          case "security_alert":
            onSecurityAlert?.({ level: data.level, message: data.message });
            break;
          case "error":
            console.error("WebSocket error:", data.message);
            break;
        }
      } catch (e) {
        console.error("Failed to parse WebSocket message:", e);
      }
    };

    wsRef.current = ws;
  }, [sessionId, onAgentState, onToken, onMessageComplete, onSecurityAlert]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((message: WSClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  return { sendMessage, isConnected };
}
