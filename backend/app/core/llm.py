"""LLM factory — provides configured ChatOpenAI instances for all agents.

Centralizes LLM configuration so every agent doesn't repeat the same wiring.
Supports temperature tuning and streaming mode. Raises clear errors if the
API key is missing.
"""

from langchain_openai import ChatOpenAI

from app.core.config import settings


def get_llm(
    temperature: float = 0.3,
    streaming: bool = False,
    model: str | None = None,
) -> ChatOpenAI:
    """Return a configured ChatOpenAI instance.

    Args:
        temperature: 0.0 = deterministic, 1.0 = creative. Default 0.3 is a
                     good balance for enterprise IT support.
        streaming:   If True, the LLM yields tokens as they are generated.
                     Required for the WebSocket token-streaming path.
        model:       Override the model name from settings.LLM_MODEL.

    Raises:
        RuntimeError: If LLM_API_KEY is not configured.
    """
    api_key = settings.LLM_API_KEY
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY is not set. Please configure it in backend/.env "
            "or set the OPENAI_API_KEY environment variable.\n"
            "Tip: You can also use a local model via Ollama by setting "
            "LLM_BASE_URL=http://localhost:11434/v1 and "
            "LLM_MODEL=llama3 (or any other ollama model)."
        )

    return ChatOpenAI(
        model=model or settings.LLM_MODEL,
        temperature=temperature,
        streaming=streaming,
        api_key=api_key,
        base_url=settings.LLM_BASE_URL or None,
    )
