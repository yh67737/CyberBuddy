"use client";

import { useRef, useState, useEffect } from "react";
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
  const [isConnected, setIsConnected] = useState(false);

  // Keep the latest callbacks in refs so the connection effect runs once on
  // mount instead of tearing down + reconnecting on every parent render.
  const onIncidentRef = useRef(onIncident);
  const onIncidentUpdateRef = useRef(onIncidentUpdate);
  const onTaskUpdateRef = useRef(onTaskUpdate);
  const onOnlineCountRef = useRef(onOnlineCount);
  onIncidentRef.current = onIncident;
  onIncidentUpdateRef.current = onIncidentUpdate;
  onTaskUpdateRef.current = onTaskUpdate;
  onOnlineCountRef.current = onOnlineCount;

  useEffect(() => {
    let disposed = false;
    let ws: WebSocket | null = null;

    const connect = () => {
      if (disposed) return;
      if (ws?.readyState === WebSocket.OPEN) return;

      ws = new WebSocket(`${WS_BASE_URL}/api/v1/dashboard/ws`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!disposed) {
          setIsConnected(true);
          reconnectDelayRef.current = RECONNECT_DELAY_MS;
        }
      };

      ws.onclose = () => {
        if (disposed) return;
        setIsConnected(false);
        wsRef.current = null;
        const delay = reconnectDelayRef.current;
        reconnectTimerRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS);
          connect();
        }, delay);
      };

      ws.onerror = () => ws?.close();

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          switch (data.type) {
            case "new_incident":
              onIncidentRef.current?.({
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
              onIncidentUpdateRef.current?.(data);
              break;
            case "task_update":
              onTaskUpdateRef.current?.({
                id: data.task_id || crypto.randomUUID(),
                toolName: data.tool_name || "",
                status: data.status || "pending",
                createdAt: data.timestamp || new Date().toISOString(),
                retryCount: data.retry_count || 0,
              });
              break;
            case "user_online_count":
              onOnlineCountRef.current?.(data.count || 0);
              break;
            case "pong":
              break;
          }
        } catch (e) {
          console.error("Dashboard WebSocket parse error:", e);
        }
      };
    };

    connect();

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
  }, []);

  return { isConnected };
}
