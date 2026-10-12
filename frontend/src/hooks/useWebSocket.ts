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
const RECONNECT_DELAY_MS = 2000;
const MAX_RECONNECT_DELAY_MS = 30000;

export function useWebSocket({
  sessionId,
  onAgentState,
  onToken,
  onMessageComplete,
  onSecurityAlert,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(RECONNECT_DELAY_MS);
  const [isConnected, setIsConnected] = useState(false);

  // Keep the latest callbacks in refs so the connection effect depends only
  // on sessionId — not on the inline callbacks, which are re-created every
  // render and would otherwise tear down + reconnect the socket constantly.
  const onAgentStateRef = useRef(onAgentState);
  const onTokenRef = useRef(onToken);
  const onMessageCompleteRef = useRef(onMessageComplete);
  const onSecurityAlertRef = useRef(onSecurityAlert);
  onAgentStateRef.current = onAgentState;
  onTokenRef.current = onToken;
  onMessageCompleteRef.current = onMessageComplete;
  onSecurityAlertRef.current = onSecurityAlert;

  useEffect(() => {
    let disposed = false;
    let ws: WebSocket | null = null;

    const connect = () => {
      if (disposed) return;
      if (ws?.readyState === WebSocket.OPEN) return;

      ws = new WebSocket(`${WS_BASE_URL}/api/v1/chat/ws/${sessionId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!disposed) {
          setIsConnected(true);
          reconnectDelayRef.current = RECONNECT_DELAY_MS; // reset on success
        }
      };

      ws.onclose = () => {
        if (disposed) return;
        setIsConnected(false);
        wsRef.current = null;
        // Auto-reconnect with exponential backoff
        const delay = reconnectDelayRef.current;
        reconnectTimerRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS);
          connect();
        }, delay);
      };

      ws.onerror = () => {
        ws?.close(); // triggers onclose → reconnect
      };

      ws.onmessage = (event) => {
        try {
          const data: WSServerMessage = JSON.parse(event.data);
          switch (data.type) {
            case "connected":
              break;
            case "agent_state":
              onAgentStateRef.current?.({
                agent: data.agent,
                status: data.status,
                isActive: true,
              });
              break;
            case "token":
              onTokenRef.current?.(data.content);
              break;
            case "message_complete":
              onMessageCompleteRef.current?.(data.route_type);
              break;
            case "security_alert":
              onSecurityAlertRef.current?.({ level: data.level, message: data.message });
              break;
            case "error":
              console.error("WebSocket error:", data.message);
              break;
          }
        } catch (e) {
          console.error("Failed to parse WebSocket message:", e);
        }
      };
    };

    connect();

    // Ping every 30s to keep alive
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);

    return () => {
      disposed = true;
      clearInterval(pingInterval);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
      setIsConnected(false);
    };
  }, [sessionId]);

  const sendMessage = useCallback((message: WSClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  return { sendMessage, isConnected };
}
