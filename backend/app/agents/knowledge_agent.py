"""KnowledgeAgent — RAG-augmented IT troubleshooting agent.

Activated by the CONSULT route from SupervisorAgent. Retrieves relevant
documents from the Milvus knowledge base and generates a detailed,
step-by-step troubleshooting response grounded in those documents.

When Milvus is unavailable or no documents match, degrades gracefully to
a general-purpose response without RAG context.
"""

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from loguru import logger

from app.agents.base import BaseAgent, AgentState
from app.core.config import settings
from app.core.llm import get_llm
from app.core.embeddings import get_embedding_service

# ---------------------------------------------------------------------------
# RAG prompt template
# ---------------------------------------------------------------------------

_RAG_SYSTEM_PROMPT = """你是 CyberBuddy，企业 IT 智能助手。你的职责是根据企业知识库内容，为员工提供精确的排障步骤和操作指导。

## 工作方式
你会收到从知识库检索到的相关文档片段。请严格基于这些文档回答用户问题：
- 如果文档中有明确的排障步骤，请按步骤列出
- 如果文档中的信息不足以解决问题，请如实说明，并给出建议
- 不要在文档内容之外编造信息
- 引用文档来源时，注明来源（如 StackExchange、IBM TechQA、企业手册等）

## 数据时效性判断
每条检索结果会标注来源日期。请根据问题类型判断信息是否可能过时：
- **系统配置/命令/API**: 超过 2 年的内容需提醒用户"可能已过时，建议验证"
- **概念原理/安全实践**: 时间敏感度低，可直接使用
- 如果信息可能过时，请在回复末尾注明数据来源日期，让用户自行判断

## 回复格式
1. 先简要确认用户的问题
2. 给出排障步骤或操作指导（基于文档内容）
3. 如有必要，补充注意事项或后续步骤建议

## 适配技术水平
根据用户 tech_level 调整回复深度：
- beginner: 给出详细步骤，避免专业术语
- intermediate: 正常技术用词
- advanced: 可以直接用技术术语，简洁高效"""

_NO_DOCS_PROMPT = """你是 CyberBuddy，企业 IT 智能助手。

知识库中暂未找到与该问题直接相关的文档。请基于你的通用 IT 知识提供建议，但需要明确告知用户：
1. 以下建议基于通用知识，非企业标准流程
2. 建议联系 IT 支持团队获取针对企业环境的确切指导

请对用户问题给出有帮助的通用建议。"""


class KnowledgeAgent(BaseAgent):
    """RAG-augmented agent for IT troubleshooting and compliance questions."""

    name: str = "KnowledgeAgent"
    description: str = "知识库 RAG 检索 — 从企业 IT 手册提取精确排障步骤"

    def __init__(self) -> None:
        super().__init__()
        self._llm = get_llm(temperature=0.3, streaming=True)

    async def run(self, state: AgentState) -> AgentState:
        """Retrieve relevant docs and generate a RAG response.

        Args:
            state: AgentState with user_input and conversation_history.

        Returns:
            Updated state with rag_context and final_response set.
        """
        user_input = state.user_input

        # Step 1: Retrieve relevant documents from Milvus
        docs = await self._retrieve_docs(user_input)
        state.rag_context = docs

        # Step 2: Build prompt and call LLM
        messages = self._build_messages(state, docs)
        state.final_response = await self._generate(messages)

        logger.info(
            f"KnowledgeAgent: responded to '{user_input[:30]}...' "
            f"({len(docs)} docs, {len(state.final_response)} chars)"
        )
        return state

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def _retrieve_docs(
        self, query: str, top_k: int = 5, min_score: float | None = None
    ) -> list[dict]:
        """Embed the query and search both Milvus collections.

        Searches the document-chunk collection (``it_knowledge``) and the
        QA-pair collection (``qa_pairs``) in parallel, merges results by
        similarity score, and returns the top-k above ``min_score``.

        Returns a list of dicts with keys: ``text``, ``score``, ``metadata``.
        The ``text`` field holds the content (document chunk or Q+A pair);
        ``metadata`` includes source, date, tags etc. for freshness checking.
        """
        if min_score is None:
            min_score = settings.MILVUS_MIN_SCORE

        try:
            svc = get_embedding_service()
            query_vec = await svc.embed_query(query)

            from app.rag.vector_store import search_knowledge_base, search_qa_pairs

            # Search both collections concurrently
            import asyncio
            docs_task = asyncio.create_task(
                search_knowledge_base(query_vec, top_k=top_k * 2, min_score=min_score)
            )
            qa_task = asyncio.create_task(
                search_qa_pairs(query_vec, top_k=top_k * 2, min_score=min_score)
            )

            doc_results = await docs_task
            qa_results = await qa_task

            # Normalize QA results to same format as doc results
            qa_normalized = []
            for qa in qa_results:
                qa_normalized.append({
                    "text": qa.get("qa_text", ""),
                    "score": qa.get("score", 0.0),
                    "metadata": {
                        "question": qa.get("question", ""),
                        "answer": qa.get("answer", ""),
                        "source": qa.get("source", ""),
                        "source_date": qa.get("date", ""),
                        "tags": qa.get("tags", ""),
                        "site": qa.get("site", ""),
                        "url": qa.get("url", ""),
                        "type": "qa_pair",
                    },
                })

            # Merge and re-rank by score (descending)
            merged = doc_results + qa_normalized
            merged.sort(key=lambda r: r.get("score", 0.0), reverse=True)

            top = merged[:top_k]

            if top:
                qa_count = sum(1 for r in top if r.get("metadata", {}).get("type") == "qa_pair")
                doc_count = len(top) - qa_count
                logger.debug(
                    f"KnowledgeAgent: retrieved {len(top)} results "
                    f"({doc_count} docs, {qa_count} QA pairs)"
                )
            else:
                logger.info("KnowledgeAgent: no matching results in any collection")

            return top

        except Exception as exc:
            logger.warning(f"KnowledgeAgent: retrieval failed, continuing without RAG — {exc}")
            return []

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def _generate(self, messages: list) -> str:
        """Call the LLM and return the response text."""
        try:
            response = await self._llm.ainvoke(messages)
            return response.content
        except Exception as exc:
            logger.error(f"KnowledgeAgent: LLM call failed — {exc}")
            return (
                "抱歉，我暂时无法完成知识库检索。请稍后再试，"
                "或直接联系 IT 支持团队获取帮助。"
            )

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    def _build_messages(self, state: AgentState, docs: list[dict]) -> list:
        """Build the RAG prompt: system + history + retrieved docs + query.

        Each doc is a dict with ``text``, ``score``, and ``metadata``.
        Metadata includes ``source``, ``source_date``, ``tags``, ``type``
        so the LLM can judge data freshness.
        """
        tech = state.user_profile.get("tech_level", "intermediate")

        if docs:
            system = SystemMessage(content=_RAG_SYSTEM_PROMPT)
            # Inject retrieved documents with metadata for freshness
            parts = []
            for i, d in enumerate(docs):
                meta = d.get("metadata", {})
                header = f"[文档 {i+1}]"
                header += f" | 来源: {meta.get('source', '未知')}"
                if meta.get("source_date"):
                    header += f" | 日期: {meta['source_date']}"
                if meta.get("score"):
                    header += f" | 相关度: {d['score']:.2f}"
                parts.append(f"{header}\n{d.get('text', '')}")

            docs_block = "\n\n---\n\n".join(parts)
            messages = [
                system,
                HumanMessage(content=f"## 知识库检索结果\n\n{docs_block}"),
            ]
        else:
            messages = [SystemMessage(content=_NO_DOCS_PROMPT)]

        # Conversation history
        for msg in state.conversation_history[-6:]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role in ("agent", "assistant"):
                messages.append(AIMessage(content=content))

        # Current query
        messages.append(
            HumanMessage(content=f"[用户技术水平: {tech}]\n{state.user_input}")
        )

        return messages
