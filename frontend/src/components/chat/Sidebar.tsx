"use client";

import { useState, useEffect, useCallback } from "react";

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
  const [search, setSearch] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/sessions`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSessions(
        data.map((s: Record<string, unknown>) => ({
          id: s.id as string,
          title: (s.title as string) || "未命名会话",
          updatedAt: new Date(s.updated_at as string).toLocaleDateString("zh-CN"),
          routeType: s.route_type as string | undefined,
        }))
      );
    } catch {
      // DB unavailable — keep empty list
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Refresh on new message (when activeSessionId changes, refetch)
  useEffect(() => {
    const interval = setInterval(fetchSessions, 10000); // poll every 10s for new sessions
    return () => clearInterval(interval);
  }, [fetchSessions]);

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!confirm("确认删除此会话及其所有消息？")) return;
    setDeleting(sessionId);
    try {
      const res = await fetch(`${API_URL}/api/v1/sessions/${sessionId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      }
    } catch {
      // ignore
    } finally {
      setDeleting(null);
    }
  };

  // Filter sessions by search
  const filtered = search.trim()
    ? sessions.filter((s) => s.title.toLowerCase().includes(search.toLowerCase()))
    : sessions;

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-900/50 flex flex-col hidden md:flex">
      {/* New session button */}
      <div className="p-3">
        <button
          onClick={onNewSession}
          className="w-full px-4 py-2 bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/30 rounded-lg text-sm text-left transition-colors"
        >
          ＋ 新会话
        </button>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索会话..."
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs
                     text-slate-300 placeholder-slate-600
                     focus:outline-none focus:ring-1 focus:ring-blue-500/50"
        />
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <div className="w-4 h-4 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <p className="text-xs text-slate-500 text-center py-8">
            {search.trim() ? "无匹配会话" : "暂无会话"}
          </p>
        )}
        {filtered.map((s) => (
          <div key={s.id} className="relative group">
            <button
              onClick={() => onSelectSession(s.id)}
              disabled={deleting === s.id}
              className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${
                s.id === activeSessionId
                  ? "bg-blue-600/20 border border-blue-500/30"
                  : "hover:bg-slate-800 border border-transparent"
              } ${deleting === s.id ? "opacity-50" : ""}`}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm text-slate-300 truncate flex-1">{s.title}</p>
                {/* Delete button — visible on hover */}
                <span
                  onClick={(e) => handleDelete(e, s.id)}
                  className="shrink-0 text-xs text-slate-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all cursor-pointer"
                  title="删除会话"
                >
                  🗑️
                </span>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs text-slate-500">{s.updatedAt}</span>
                {s.routeType === "RISK" && (
                  <span className="text-xs text-red-400 bg-red-400/10 px-1 rounded">🔴</span>
                )}
                {s.routeType === "CONSULT" && (
                  <span className="text-xs text-green-400 bg-green-400/10 px-1 rounded">🟢</span>
                )}
              </div>
            </button>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-slate-800 text-xs text-slate-600 text-center">
        会话历史 · {sessions.length} 条
      </div>
    </aside>
  );
}
