import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "CyberBuddy — 企业 IT 安全合规与故障响应平台",
  description: "面向企业员工的 L1/L2 级智能 IT 服务与安全预警中枢",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-slate-950 text-slate-100">
        {/* Top Navigation */}
        <nav className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-xl font-bold text-blue-400">🛡️ CyberBuddy</span>
              <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded">L1/L2</span>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <a href="/chat" className="text-slate-300 hover:text-white transition-colors">
                💬 用户门户
              </a>
              <a href="/dashboard" className="text-slate-300 hover:text-white transition-colors">
                📊 运维工作台
              </a>
            </div>
          </div>
        </nav>

        {/* Page Content */}
        <main className="flex-1 flex flex-col">{children}</main>
      </body>
    </html>
  );
}
