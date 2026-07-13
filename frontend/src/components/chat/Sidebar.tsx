"use client";

import { useState, useEffect } from "react";

interface Session {
  id: string;
  title: string;
  updatedAt: string;
  routeType?: string;
}

interface SidebarProps {
  activeSessionId: string;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function Sidebar({ activeSessionId, onNewSession, onSelectSession }: SidebarProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSessions();
  }, []);

  async function fetchSessions() {
    try {
      const res = await fetch(`${API_URL}/api/v1/sessions`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSessions(
        data.map((s: Record<string, unknown>) => ({
          id: s.id as string,
          title: s.title as string,
          updatedAt: new Date(s.updated_at as string).toLocaleDateString("zh-CN"),
          routeType: s.route_type as string | undefined,
        }))
      );
    } catch {
      // DB unavailable — keep empty list
    } finally {
      setLoading(false);
    }
  }

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-900/50 flex flex-col hidden md:flex">
      {/* New session button */}
      <div className="p-3">
        <button
          onClick={onNewSession}
          className="w-full px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-sm text-left transition-colors"
        >
          ＋ 新会话
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        {loading && (
          <p className="text-xs text-slate-500 text-center py-8">加载中...</p>
        )}
        {!loading && sessions.length === 0 && (
          <p className="text-xs text-slate-500 text-center py-8">暂无会话</p>
        )}
        {sessions.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelectSession(s.id)}
            className={`w-full text-left px-3 py-2 rounded-lg transition-colors group ${
              s.id === activeSessionId
                ? "bg-blue-600/20 border border-blue-500/30"
                : "hover:bg-slate-800"
            }`}
          >
            <p className="text-sm text-slate-300 truncate">{s.title}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-slate-500">{s.updatedAt}</span>
              {s.routeType === "RISK" && (
                <span className="text-xs text-red-400 bg-red-400/10 px-1 rounded">🔴</span>
              )}
            </div>
          </button>
        ))}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-slate-800 text-xs text-slate-600 text-center">
        会话历史 · {sessions.length} 条
      </div>
    </aside>
  );
}
