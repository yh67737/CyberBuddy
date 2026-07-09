import Link from "next/link";

export default function Home() {
  return (
    <div className="flex-1 flex items-center justify-center px-4">
      <div className="max-w-2xl w-full text-center space-y-8">
        {/* Hero */}
        <div className="space-y-4">
          <div className="text-6xl">🛡️</div>
          <h1 className="text-4xl font-bold tracking-tight">
            <span className="text-blue-400">CyberBuddy</span> 智能体
          </h1>
          <p className="text-lg text-slate-400 max-w-lg mx-auto">
            企业级 IT 安全合规与故障响应平台 — 基于多 Agent 协作的 L1/L2
            智能服务中枢
          </p>
        </div>

        {/* Feature cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-left">
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-5 space-y-2">
            <span className="text-2xl">💬</span>
            <h3 className="font-semibold text-white">智能 IT 助手</h3>
            <p className="text-sm text-slate-400">
              流式对话界面，支持 Markdown 渲染、多模态输入，实时显示 Agent 处理状态
            </p>
          </div>
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-5 space-y-2">
            <span className="text-2xl">🧠</span>
            <h3 className="font-semibold text-white">多 Agent 协作</h3>
            <p className="text-sm text-slate-400">
              6 类专业 Agent：Memory → Supervisor → ITSupport / Knowledge /
              SecurityGuardian → SecOps
            </p>
          </div>
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-5 space-y-2">
            <span className="text-2xl">🔴</span>
            <h3 className="font-semibold text-white">实时安全监控</h3>
            <p className="text-sm text-slate-400">
              高危事件毫秒级熔断预警，SecOps Dashboard 可视化接管
            </p>
          </div>
        </div>

        {/* CTA Buttons */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/chat"
            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-500 rounded-lg font-medium transition-colors"
          >
            💬 进入用户门户
          </Link>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 px-6 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg font-medium transition-colors"
          >
            📊 运维工作台
          </Link>
        </div>
      </div>
    </div>
  );
}
