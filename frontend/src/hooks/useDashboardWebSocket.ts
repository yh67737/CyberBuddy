"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { SecurityIncident, AsyncTask } from "@/lib/types";

interface UseDashboardWSOptions {
  onIncident?: (incident: SecurityIncident) => void;
  onTaskUpdate?: (task: AsyncTask) => void;
}

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export function useDashboardWebSocket({
  onIncident,
  onTaskUpdate,
}: UseDashboardWSOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  const connect = useCallback(() => {
    const ws = new WebSocket(`${WS_BASE_URL}/api/v1/dashboard/ws`);

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);
    ws.onerror = () => setIsConnected(false);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case "new_incident":
            onIncident?.(data.incident as SecurityIncident);
            break;
          case "task_update":
            onTaskUpdate?.(data.task as AsyncTask);
            break;
          case "pong":
            break;
        }
      } catch (e) {
        console.error("Dashboard WebSocket parse error:", e);
      }
    };

    wsRef.current = ws;
  }, [onIncident, onTaskUpdate]);

  useEffect(() => {
    connect();

    // Ping every 30s to keep alive
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      wsRef.current?.close();
    };
  }, [connect]);

  return { isConnected };
}
