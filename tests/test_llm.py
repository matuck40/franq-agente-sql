import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tests.fakes import FakeToolLLM


def test_get_llm_requires_api_key(monkeypatch):
    from src import llm

    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm.get_llm()


def test_fake_returns_messages_in_order_and_records_inputs():
    fake = FakeToolLLM([AIMessage("a"), AIMessage("b")])
    assert fake.bind_tools([]) is fake
    assert fake.invoke([HumanMessage("x")]).content == "a"
    assert fake.invoke([HumanMessage("y")]).content == "b"
    assert len(fake.recebidas) == 2
    assert fake.recebidas[1][0].content == "y"


def test_fake_preserves_tool_calls():
    msg = AIMessage(content="", tool_calls=[{"name": "run_sql", "args": {"sql": "SELECT 1"}, "id": "1"}])
    out = FakeToolLLM([msg]).invoke([HumanMessage("q")])
    assert out.tool_calls[0]["name"] == "run_sql"


def test_get_llm_sets_timeout_and_retries(monkeypatch):
    from src import llm

    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    modelo = llm.get_llm()  # builds the client only; no request is sent
    assert modelo.model_name == "gpt-5-mini"
    assert modelo.request_timeout == 60 and modelo.max_retries == 2
