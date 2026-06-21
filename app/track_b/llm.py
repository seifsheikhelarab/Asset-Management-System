from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import settings

_llm: ChatOpenAI | None = None


def get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        if not settings.llm_api_key:
            raise RuntimeError(
                "LLM not configured. Set LLM_API_KEY and optionally "
                "LLM_BASE_URL / LLM_MODEL in .env"
            )
        _llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=SecretStr(settings.llm_api_key),
            base_url=settings.llm_base_url or None,
            temperature=0,
        )
    return _llm
