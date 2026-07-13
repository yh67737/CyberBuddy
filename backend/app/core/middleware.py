"""HTTP middleware — input sanitization and request logging.

Applied globally to all routes. Strips dangerous content from user input
before it reaches any agent or database.
"""

import re
import unicodedata

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from loguru import logger

# ---------------------------------------------------------------------------
# Sanitization patterns
# ---------------------------------------------------------------------------

# Strip common XSS vectors: <script>, javascript:, onerror=, etc.
_XSS_PATTERN = re.compile(
    r"<script[^>]*>.*?</script>|"
    r"javascript\s*:|"
    r"on\w+\s*=\s*[\"'].*?[\"']|"
    r"<iframe[^>]*>|"
    r"<embed[^>]*>|"
    r"<object[^>]*>",
    re.IGNORECASE | re.DOTALL,
)

# SQL comment injection patterns (defense-in-depth — SQLAlchemy parameterizes
# queries, but it doesn't hurt to strip these from log output too)
_SQL_COMMENT_PATTERN = re.compile(r"/\*.*?\*/|--\s|;\s*DROP\s|\bOR\s+1\s*=\s*1", re.IGNORECASE)

# Unicode homoglyph / confusable character normalization
# (e.g. fullwidth latin → ascii)
_HOMOGLYPH_MAP = str.maketrans(
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    "０１２３４５６７８９",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789",
)

# Max input length to prevent resource exhaustion
_MAX_INPUT_LENGTH = 16_384  # 16 KB


def sanitize_text(text: str) -> str:
    """Clean user-supplied text.

    Returns a sanitized copy. The original is not mutated.
    Logs a warning when dangerous content is stripped.
    """
    if not isinstance(text, str):
        return text

    original = text

    # Truncate overlong input
    if len(text) > _MAX_INPUT_LENGTH:
        text = text[:_MAX_INPUT_LENGTH]
        logger.warning(f"Input truncated from {len(original)} to {_MAX_INPUT_LENGTH} chars")

    # Normalize unicode (NFC) + strip control chars (except common whitespace)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

    # Convert fullwidth/homoglyph characters
    text = text.translate(_HOMOGLYPH_MAP)

    # Strip XSS patterns
    text, xss_count = _XSS_PATTERN.subn("", text)
    if xss_count:
        logger.warning(f"Stripped {xss_count} XSS pattern(s) from input")

    # Strip SQL injection patterns (defense-in-depth)
    text, sql_count = _SQL_COMMENT_PATTERN.subn("", text)
    if sql_count:
        logger.warning(f"Stripped {sql_count} SQL-injection-like pattern(s) from input")

    return text.strip()


# ---------------------------------------------------------------------------
# FastAPI middleware
# ---------------------------------------------------------------------------

class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """Middleware that sanitizes JSON body fields before they reach endpoints.

    Applied globally. Looks for common field names like 'content', 'message',
    'user_input', 'description', and 'title' in JSON request bodies and
    runs them through `sanitize_text`.
    """

    # Fields that are considered user-supplied free-text and should be sanitized
    _TEXT_FIELDS = {"content", "message", "user_input", "description", "title", "summary", "text"}

    async def dispatch(self, request: Request, call_next) -> Response:
        # Only process JSON requests
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
                sanitized = self._sanitize_dict(body)
                # Replace the request body with sanitized version
                # (FastAPI/Starlette doesn't support body mutation natively,
                # so we store it in request.state for endpoints to use)
                request.state.raw_body = body
                request.state.sanitized_body = sanitized
            except Exception:
                # Malformed JSON — let the endpoint handle the error
                pass

        return await call_next(request)

    @classmethod
    def _sanitize_dict(cls, obj):
        """Recursively walk a JSON object and sanitize text fields."""
        if isinstance(obj, dict):
            return {
                k: (
                    sanitize_text(v) if k.lower() in cls._TEXT_FIELDS and isinstance(v, str)
                    else cls._sanitize_dict(v)
                )
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [cls._sanitize_dict(item) for item in obj]
        return obj


# ---------------------------------------------------------------------------
# Convenience: sanitize an entire dict before passing to AgentState
# ---------------------------------------------------------------------------

def sanitize_agent_input(data: dict) -> dict:
    """Sanitize a dict that will become part of an AgentState.

    Call this in WebSocket or REST handlers before constructing AgentState
    to ensure no malicious input reaches the LLM or database.
    """
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_text(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_agent_input(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_agent_input(item) if isinstance(item, dict)
                else sanitize_text(item) if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized
