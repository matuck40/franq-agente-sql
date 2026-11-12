"""Test doubles for chat models."""
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakeToolLLM(BaseChatModel):
    """Returns the given AIMessages unchanged, in order, and records inputs."""

    respostas: list[AIMessage]
    recebidas: list[list[BaseMessage]] = []
    _i: int = 0

    def __init__(self, respostas: list[AIMessage], **kwargs: Any):
        super().__init__(respostas=respostas, recebidas=[], **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeToolLLM":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.recebidas.append(list(messages))
        msg = self.respostas[self._i]
        self._i += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @property
    def _llm_type(self) -> str:
        return "fake-tool-llm"
