/** Core type definitions for CyberBuddy frontend. */

export interface Message {
  id: string;
  role: "user" | "agent" | "system";
  content: string;
  agentRole?: string;
  routeType?: string; // CHAT | CONSULT | RISK
  attachments?: string[];
  timestamp: Date;
}

export interface AgentState {
  agent: string;
  status: string;
  isActive: boolean;
}

export interface SecurityIncident {
  id: string;
  severity: "low" | "medium" | "high" | "critical";
  title: string;
  description: string;
  entities: Record<string, string>;
  agentSummary: string;
  status: "open" | "investigating" | "contained" | "closed";
  createdAt: string;
}

export interface AsyncTask {
  id: string;
  toolName: string;
  status: "pending" | "running" | "completed" | "failed" | "dead_letter";
  createdAt: string;
  completedAt?: string;
  retryCount: number;
  errorMessage?: string;
}

export interface Session {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  routeType?: string;
  isActive: boolean;
}

/** WebSocket message types */
export type WSClientMessage =
  | { type: "chat"; content: string; attachments?: string[] }
  | { type: "ping" };

export type WSServerMessage =
  | { type: "connected"; session_id: string; message: string }
  | { type: "agent_state"; agent: string; status: string }
  | { type: "token"; content: string }
  | { type: "message_complete"; route_type: string }
  | { type: "security_alert"; level: string; message: string }
  | { type: "error"; message: string };
