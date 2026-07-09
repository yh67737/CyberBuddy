# CyberBuddy 智能体 - 项目实施计划

> 基于 PRD v1.0 | 企业级 IT 安全合规与故障响应平台

---

## 项目架构总览

```
CyberBuddy/
├── backend/                    # Python FastAPI 后端
│   ├── app/
│   │   ├── api/               # RESTful API + WebSocket 端点
│   │   ├── agents/            # 6 类专业 Agent
│   │   ├── core/              # 配置、中间件、安全
│   │   ├── db/                # SQLAlchemy 模型 + 数据库
│   │   ├── orchestration/     # LangGraph 编排
│   │   ├── rag/               # ChromaDB 向量检索
│   │   ├── skills/            # 高危熔断预案
│   │   ├── mcp/               # MCP 工具生态 + DLQ
│   │   └── main.py            # 应用入口
│   ├── tests/                 # 自动化测试
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   # Next.js + TailwindCSS 前端
│   ├── src/
│   │   ├── app/               # App Router 页面
│   │   ├── components/        # 组件库
│   │   ├── hooks/             # 自定义 Hooks (WebSocket等)
│   │   └── lib/               # 工具函数
│   ├── tailwind.config.ts
│   ├── next.config.js
│   └── Dockerfile
├── docs/                       # 文档
├── docker-compose.yml          # 本地开发编排
├── .gitignore
└── README.md
```

---

## 第一阶段：工程基建与项目初始化

### 1.1 项目仓库与目录结构搭建
- 初始化 Git 仓库，建立 monorepo 结构
- 创建 `backend/`（Python + FastAPI）和 `frontend/`（Next.js + TailwindCSS）
- 配置 `.gitignore`、`README.md`

### 1.2 开发环境配置
- **后端**：Python 3.11+ 虚拟环境, FastAPI, LangGraph, ChromaDB, SQLAlchemy, WebSocket 库
- **前端**：Next.js 脚手架, TailwindCSS, WebSocket 客户端
- **基础设施**：Docker Compose 编排 ChromaDB、MySQL 等依赖服务

---

## 第二阶段：后端逻辑层（Backend Agent Harness）

### 2.1 数据库模型与持久化层
- SQLAlchemy 数据模型：用户表、会话历史表（Memory）、异步任务记录表、安全事件表
- 配置 SQLite（开发）/ MySQL（生产）
- Alembic 数据库迁移

### 2.2 FastAPI 基础框架
- RESTful API 路由设计（用户管理、会话管理、工单查询）
- WebSocket / SSE 端点（流式对话输出 + Agent 状态实时透传）
- 中间件：输入脱敏、Session 解析、CORS

### 2.3 Agent Runtime Harness（统一封装层）
- 封装 Agent 基类与注册机制
- Agent 间通信协议定义（消息格式、状态传递）
- 统一异常处理与日志记录

### 2.4 六类专业 Agent 实现

| 序号 | Agent | 核心职责 | 关键逻辑 |
|------|-------|---------|---------|
| 2.4a | **MemoryAgent** | 上下文与画像维持 | 读取员工画像 → 解析历史会话 → 决定回复深浅 |
| 2.4b | **SupervisorAgent** | 意图路由大脑 | 分发至 CHAT / CONSULT / RISK 三条路由 |
| 2.4c | **ITSupportAgent** | 普通问询响应 | 处理低风险基础 IT 对话，无需强制 RAG |
| 2.4d | **KnowledgeAgent** | 文档检索增强 | 对接 ChromaDB，提取精确排障步骤 |
| 2.4e | **SecurityGuardian** | 高危安全拦截 | 嗅探异常特征，触发即刻熔断 |
| 2.4f | **SecOpsAgent** | 专家交接与通报 | 生成标准工单 → WebSocket 推送 Dashboard |

### 2.5 LangGraph 编排层
- 构建状态机路由图：Supervisor → 下游 Agent
- RISK 路由最高优先级打断机制
- 流式状态透传（Agent 思考过程实时推送前端）

### 2.6 RAG 检索增强系统
- ChromaDB 本地向量数据库搭建
- 企业 IT 手册与安全合规制度文档导入（Embedding + 分块策略）
- KnowledgeAgent 检索 + 生成链路

### 2.7 高危熔断预案（Skill 沉淀）

| Skill | 名称 | 触发条件 | 行为 |
|-------|------|---------|------|
| Skill 1 | `breach_containment_plan` | 嗅探到 RISK | 前台 UI 强制切换红色安全模式 → 输出物理隔离/断网指令 |
| Skill 2 | `secops_handoff_summary` | 安全事件确认 | 收集关键实体 → 格式化摘要 → WebSocket 推送 Dashboard |

### 2.8 MCP 工具生态与死信队列（DLQ）
- 封装 MCP 工具：`create_jira_ticket`、`query_ad_status` 等
- 异步任务队列（Celery / ARQ）
- 死信队列：失败重试机制，不阻塞前端流式对话

---

## 第三阶段：前端呈现层（Frontend）

### 3.1 前端项目初始化
- Next.js 14+ (App Router) + TypeScript + TailwindCSS
- WebSocket 客户端封装（自定义 Hook）
- 页面路由：`/chat`（用户门户）、`/dashboard`（运维工作台）

### 3.2 用户侧门户（User Portal）

| 功能 | 说明 |
|------|------|
| 流式对话界面 | Markdown 渲染（代码块、排障步骤）、打字机流式输出效果 |
| Agent 状态可视化 | 顶部实时显示当前接管 Agent 角色与状态描述 |
| 历史会话管理 | 会话列表、切换、删除、搜索 |
| 多模态输入 | 支持上传报错截图，对接后端 Vision/OCR 解析 |
| 安全模式 UI | RISK 触发时界面强制切换红色主题，锁定非安全交互 |

### 3.3 安全运维工作台（SecOps Dashboard）

| 功能 | 说明 |
|------|------|
| 实时监控大屏 | 高危 Incident 列表 + 实时 WebSocket 弹窗告警 |
| 安全交接摘要 | Agent 生成的格式化摘要卡片展示 |
| 工单状态看板 | 异步工单执行状态流转可视化（待处理 → 处理中 → 已完成） |

---

## 第四阶段：联调与测试

### 4.1 端到端联调
- 前端 ↔ 后端 WebSocket/SSE 流式通信验证
- Agent 状态实时透传验证
- 安全事件全链路测试（用户输入 → RISK → 熔断 → Dashboard 告警）

### 4.2 自动化测试脚本

| 测试项 | 方法 | 目标 |
|--------|------|------|
| RAG 召回能力 | 150 条模拟 IT 排障 query | HitRate ≥ 0.96, MRR ≥ 0.90 |
| 路由准确率 | CHAT / CONSULT / RISK 边界分类 | 准确率 ≥ 97% |
| 前端长链接压测 | 模拟并发 WebSocket 连接 | Agent 响应延迟在可接受范围 |

---

## 第五阶段：部署上线

### 5.1 容器化
- 前端 Dockerfile（Next.js standalone 模式）
- 后端 Dockerfile（FastAPI + Uvicorn）

### 5.2 编排与部署
- Docker Compose 生产配置
- CI/CD 流水线（GitHub Actions / GitLab CI）
- 环境变量与密钥管理

---

## 推荐开发顺序

```
Step 1  → 项目骨架搭建（git + 目录 + 依赖）
Step 2  → 后端 FastAPI 骨架 + 数据库模型
Step 3  → Agent 基类 + SupervisorAgent 路由
Step 4  → 其余 5 个 Agent + LangGraph 编排
Step 5  → RAG 系统（ChromaDB + KnowledgeAgent）
Step 6  → WebSocket/SSE 实时通信
Step 7  → 高危熔断 Skill + MCP 工具 + DLQ
Step 8  → 前端用户门户（聊天界面）
Step 9  → 前端运维工作台（Dashboard）
Step 10 → 联调测试 + 压测 + 部署
```

---

> **文档版本**: v1.0  
> **创建日期**: 2026-07-09  
> **状态**: 第一步进行中
