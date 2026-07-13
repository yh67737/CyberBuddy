"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { SecurityIncident, AsyncTask } from "@/lib/types";

interface UseDashboardWSOptions {
  onIncident?: (incident: SecurityIncident) => void;
  onIncidentUpdate?: (update: Record<string, unknown>) => void;
  onTaskUpdate?: (task: AsyncTask) => void;
  onOnlineCount?: (count: number) => void;
}

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
const RECONNECT_DELAY_MS = 2000;
const MAX_RECONNECT_DELAY_MS = 30000;

export function useDashboardWebSocket({
  onIncident,
  onIncidentUpdate,
  onTaskUpdate,
  onOnlineCount,
}: UseDashboardWSOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(RECONNECT_DELAY_MS);
  const mountedRef = useRef(true);
  const [isConnected, setIsConnected] = useState(false);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_BASE_URL}/api/v1/dashboard/ws`);

    ws.onopen = () => {
      if (mountedRef.current) {
        setIsConnected(true);
        reconnectDelayRef.current = RECONNECT_DELAY_MS;
      }
    };

    ws.onclose = () => {
      if (mountedRef.current) {
        setIsConnected(false);
        wsRef.current = null;
        const delay = reconnectDelayRef.current;
        reconnectTimerRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS);
          connect();
        }, delay);
      }
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case "new_incident":
            onIncident?.({
              id: data.session_id || crypto.randomUUID(),
              severity: data.severity || "medium",
              title: data.title || "",
              description: data.description || "",
              entities: {},
              agentSummary: "",
              status: "open",
              createdAt: data.timestamp || new Date().toISOString(),
            });
            break;
          case "incident_update":
            onIncidentUpdate?.(data);
            break;
          case "task_update":
            onTaskUpdate?.({
              id: data.task_id || crypto.randomUUID(),
              toolName: data.tool_name || "",
              status: data.status || "pending",
              createdAt: data.timestamp || new Date().toISOString(),
              retryCount: data.retry_count || 0,
            });
            break;
          case "user_online_count":
            onOnlineCount?.(data.count || 0);
            break;
          case "pong":
            break;
        }
      } catch (e) {
        console.error("Dashboard WebSocket parse error:", e);
      }
    };

    wsRef.current = ws;
  }, [onIncident, onIncidentUpdate, onTaskUpdate, onOnlineCount]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);

    return () => {
      mountedRef.current = false;
      clearInterval(pingInterval);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { isConnected };
}
