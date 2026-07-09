# CyberBuddy 智能体

> 企业级 IT 安全合规与故障响应平台

面向企业员工的 L1/L2 级智能 IT 服务与安全预警中枢。基于前后端分离架构，通过 Web 端提供沉浸式对话体验；后端基于 LangGraph 组织多 Agent 协作，实现意图动态路由、标准排障流程的自动化闭环，并在发生高风险安全事件时实现毫秒级熔断预警。

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | Next.js 14+, TypeScript, TailwindCSS, WebSocket |
| **后端** | Python 3.11+, FastAPI, LangGraph, ChromaDB, SQLAlchemy |
| **基础设施** | Docker, MySQL/SQLite, Redis |

## 快速开始

```bash
# 1. 克隆仓库
git clone <repo-url>
cd CyberBuddy

# 2. 启动后端
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# 3. 启动前端
cd frontend
npm install
npm run dev
```

## 项目结构

```
CyberBuddy/
├── backend/           # Python FastAPI 后端
│   ├── app/
│   │   ├── api/       # RESTful API + WebSocket
│   │   ├── agents/    # 6 类专业 Agent
│   │   ├── core/      # 配置、中间件
│   │   ├── db/        # 数据库模型
│   │   ├── orchestration/  # LangGraph 编排
│   │   ├── rag/       # ChromaDB 向量检索
│   │   ├── skills/    # 高危熔断预案
│   │   └── mcp/       # MCP 工具 + DLQ
│   └── tests/         # 自动化测试
├── frontend/          # Next.js 前端
│   └── src/
│       ├── app/       # 页面路由
│       ├── components/# UI 组件
│       └── hooks/     # 自定义 Hooks
└── docs/              # 文档
```

## 六类 Agent

| Agent | 职责 |
|-------|------|
| MemoryAgent | 上下文与画像维持 |
| SupervisorAgent | 意图路由大脑 (CHAT/CONSULT/RISK) |
| ITSupportAgent | 普通 IT 问询响应 |
| KnowledgeAgent | 知识库 RAG 检索 |
| SecurityGuardian | 高危安全拦截与熔断 |
| SecOpsAgent | 安全事件交接与通报 |
