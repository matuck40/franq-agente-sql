"""LLM factory for the app."""
import os

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "gpt-5-mini"


def get_llm() -> BaseChatModel:
    """Build the OpenAI chat model from .env / environment variables."""
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Defina OPENAI_API_KEY no .env")
    # Bounded wait per request so a stuck API call cannot hang the UI forever.
    return ChatOpenAI(model=os.getenv("LLM_MODEL", DEFAULT_MODEL), timeout=60, max_retries=2)
