"use client";

import { useState } from "react";

interface Session {
  id: string;
  title: string;
  updatedAt: string;
  routeType?: string;
}

export function Sidebar() {
  const [sessions] = useState<Session[]>([
    { id: "1", title: "VPN 连接报错排查", updatedAt: "10:30", routeType: "CONSULT" },
    { id: "2", title: "申请新显示器", updatedAt: "昨天", routeType: "CHAT" },
    { id: "3", title: "可疑邮件检查", updatedAt: "昨天", routeType: "RISK" },
  ]);

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-900/50 flex flex-col hidden md:flex">
      {/* New session button */}
      <div className="p-3">
        <button className="w-full px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-sm text-left transition-colors">
          ＋ 新会话
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        {sessions.map((s) => (
          <button
            key={s.id}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-800 transition-colors group"
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
        会话历史 · 本地存储
      </div>
    </aside>
  );
}
