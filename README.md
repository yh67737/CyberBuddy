# CyberBuddy

**An AI assistant for IT troubleshooting and security incident triage.**

CyberBuddy helps employees ask IT questions, find troubleshooting guidance, and report security concerns in one chat interface. A LangGraph workflow routes each message to a general assistant, a knowledge retrieval agent, or a security response workflow. A separate dashboard helps security operators review incidents, notification tasks, and agent execution logs.

This project explores practical agent development: shared state, intent routing, retrieval-augmented generation (RAG), external tool integration, and failure handling.

[How it works](#how-it-works) · [Run locally](#run-locally) · [Tests and evaluation](#tests-and-evaluation) · [Code guide](#code-guide)

## What it does

| Employee request | System behavior |
| --- | --- |
| “What can you help me with?” | Answers directly using recent conversation history. |
| “My VPN will not connect. What should I check?” | Searches IT documents and Q&A records, then generates troubleshooting guidance. |
| “I clicked a suspicious link and entered my work password.” | Extracts incident details, provides predefined response instructions, and attempts to notify the security team. |

- **Context-aware conversations:** loads recent messages and a user profile to adjust the depth of explanations.
- **Knowledge-backed answers:** retrieves relevant passages from Milvus and includes source metadata in the generation prompt.
- **Security handoff:** prepares incident details and a structured summary for security operations.
- **Operational visibility:** records agent execution paths, per-agent duration, request latency, and errors.
- **Notification recovery:** persists failed Feishu/Lark notifications for bounded background retries and dead-letter tracking.

## How it works

```mermaid
flowchart TD
    Input[Employee message] --> Memory[MemoryAgent: load profile and history]
    Memory --> Supervisor[SupervisorAgent: classify intent]
    Supervisor -->|CHAT| Support[ITSupportAgent: direct answer]
    Supervisor -->|CONSULT| Knowledge[KnowledgeAgent: retrieve and answer]
    Supervisor -->|RISK| Guardian[SecurityGuardian: analyze incident]
    Guardian --> SecOps[SecOpsAgent: prepare handoff]
    Guardian --> Alerts[Incident storage, dashboard events, and Feishu alerts]
    Support --> Output[Chat response and execution log]
    Knowledge --> Output
    SecOps --> Output
```

Each request carries an [`AgentState`](backend/app/agents/base.py) containing the input, profile, history, route, retrieved context, incident metadata, response, and execution trace. The [graph](backend/app/orchestration/graph.py) runs only the branch selected for that request.

| Component | Responsibility |
| --- | --- |
| [MemoryAgent](backend/app/agents/memory_agent.py) | Loads the user profile and the latest ten conversation messages from PostgreSQL. |
| [SupervisorAgent](backend/app/agents/supervisor_agent.py) | Uses an LLM to return a validated route, confidence score, and explanation. |
| [ITSupportAgent](backend/app/agents/it_support_agent.py) | Generates a direct response without knowledge retrieval. |
| [KnowledgeAgent](backend/app/agents/knowledge_agent.py) | Retrieves supporting documents and generates an answer with that context. |
| [SecurityGuardian](backend/app/agents/security_guardian.py) | Retrieves related violations, extracts threat details, and initiates guidance and alerts. |
| [SecOpsAgent](backend/app/agents/secops_agent.py) | Formats extracted incident details into a predefined handoff summary. |

The workflow combines LLM-based decisions with deterministic Python steps. Memory loading and handoff formatting do not require separate model calls.

### Retrieval and data

The ingestion scripts split handbook content by headings and paragraphs, or combine a question with its answer, before generating local BGE embeddings. Milvus stores three collections:

- `it_knowledge`: handbook and policy document chunks.
- `qa_pairs`: IT support question-answer records.
- `security_violations`: example reports mapped to named violations and severity levels.

For consultation requests, the agent searches the document and Q&A collections, filters candidates by cosine similarity, and selects the top five merged results. Source and date metadata are passed to the model. If retrieval is unavailable or returns no matches, the prompt switches to general guidance and asks the model to disclose that it is not an organization-specific procedure.

Source material includes the [GitLab Handbook](https://handbook.gitlab.com/), [IBM TechQA](https://github.com/IBM/techqa), IEEE IT Support, and StackExchange Q&A. See the [data catalog](docs/DATA_CATALOG.md) for provenance and attribution details. These public sources provide demonstration knowledge, not a particular employer's internal policies.

### Application and events

The [chat WebSocket](backend/app/api/endpoints/chat.py) sends node updates and response chunks to the frontend. The [dashboard API](backend/app/api/endpoints/dashboard.py) serves stored records and forwards events from an in-process event bus. Failed external notifications are stored as tasks for the [retry worker](backend/app/mcp/dead_letter_queue.py).

## Tech stack

| Layer | Technologies |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS, Recharts |
| Backend | Python 3.12, FastAPI, WebSocket |
| Agent workflow | LangGraph, LangChain, OpenAI-compatible model API |
| Retrieval | BGE embeddings, Sentence Transformers, Milvus |
| Persistence | PostgreSQL, SQLAlchemy async ORM, asyncpg |
| Local infrastructure | Docker Compose, etcd and MinIO for Milvus |

## Run locally

Prerequisites: Python 3.12, Node.js 22, Docker Compose, Git, and credentials for an OpenAI-compatible model provider. Embedding model downloads and handbook ingestion require internet access.

### 1. Clone and install

```bash
git clone https://github.com/yh67737/CyberBuddy.git
cd CyberBuddy
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install langchain-huggingface
```

The additional package supplies the embedding adapter imported by the backend; it is currently missing from `requirements.txt`.

### 2. Configure the backend

Create `backend/.env` using this template. Replace the placeholder values with your own configuration; `.env` files are ignored by Git.

```dotenv
SECRET_KEY=replace-with-a-random-secret
DEBUG=false
LLM_API_KEY=your-provider-api-key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=your-available-chat-model
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/cyberbuddy
MILVUS_HOST=localhost
MILVUS_PORT=19530
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
```

Optionally set `FEISHU_WEBHOOK_URL` to enable external notifications. Provider credentials are required even for local graph initialization. The embedding model is downloaded on first use and runs locally on CPU by default.

### 3. Start infrastructure and backend

From the repository root, start the database services:

```bash
docker compose up -d postgres etcd minio milvus
```

Then start the backend in the same terminal:

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Tables are created at startup. Vector collections start empty until knowledge is imported.

### 4. Start the frontend

In another terminal, from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open the [chat](http://localhost:3000/chat), [security dashboard](http://localhost:3000/dashboard), or [interactive API documentation](http://localhost:8000/docs). These links work after starting the app locally; no hosted demo is linked here.

### 5. Add knowledge (optional)

From the repository root with the virtual environment active:

```bash
python scripts/import_handbook.py --limit 500
```

This downloads public handbook content, embeds up to 500 chunks, and indexes them in local Milvus. Additional scripts import [Q&A records](scripts/import_to_milvus.py) and [security violations](scripts/import_violations.py) after their input JSON files are supplied.

The `data/` directory is excluded from version control. Downloaded datasets, generated violation records, and local evaluation JSON files are not included in a fresh clone.

## Tests and evaluation

[Backend tests](backend/tests/) cover health endpoints, graph structure, and example CHAT, CONSULT, and RISK flows. The [routing evaluator](scripts/eval_router.py) reports accuracy before and after confidence fallback, a confusion matrix, and misclassified examples. The [retrieval evaluator](scripts/eval_rag.py) reports HitRate@1/3/5 and mean reciprocal rank (MRR) for each collection.

Run from `backend/` with the virtual environment active and backend configuration set:

```bash
# Checks that do not make model calls
pytest -m "not integration"

# Integration flows; calls the configured model and may send configured alerts
pytest -m integration

# Supply labeled JSON files; see each script for the expected fields
python ../scripts/eval_router.py --testset /path/to/router_queries.json
python ../scripts/eval_rag.py --testset /path/to/rag_queries.json
```

Retrieval evaluation requires populated Milvus collections. Its relevance checks use keywords or matching severity labels, so it is a preliminary retrieval check rather than an evaluation of final answer correctness. Verified benchmark reports are not included; planning targets should not be read as measured results.

## Code guide

| Area | Entry point |
| --- | --- |
| Application startup | [`backend/app/main.py`](backend/app/main.py) |
| Shared state and agent interface | [`backend/app/agents/base.py`](backend/app/agents/base.py) |
| Workflow and conditional edges | [`backend/app/orchestration/graph.py`](backend/app/orchestration/graph.py) |
| Vector search | [`backend/app/rag/vector_store.py`](backend/app/rag/vector_store.py) |
| Database models | [`backend/app/db/models.py`](backend/app/db/models.py) |
| External notifications | [`backend/app/mcp/tools.py`](backend/app/mcp/tools.py) |
| Employee chat | [`frontend/src/app/chat/page.tsx`](frontend/src/app/chat/page.tsx) |
| Security dashboard | [`frontend/src/app/dashboard/page.tsx`](frontend/src/app/dashboard/page.tsx) |
| Data preparation and evaluation | [`scripts/`](scripts/) |
