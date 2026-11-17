from pathlib import Path

import pandas as pd
import streamlit
from streamlit.testing.v1 import AppTest

import src.agent
import src.llm

APP = str(Path(__file__).parent.parent / "app.py")
TEXTO = "Resposta fixa de teste."


def _resultado(**kw):
    base = {
        "texto": TEXTO,
        "sql": "SELECT 1",
        "dados": pd.DataFrame({"canal": ["a", "b"], "n": [1, 2]}),
        "visualizacao": "barra",
        "x": "canal",
        "y": "n",
        "passos": [
            {"sql": "SELECT 1", "linhas": 2, "erro": None},
            {"sql": "SELEC 2", "linhas": None, "erro": "syntax error"},
        ],
    }
    base.update(kw)
    return base


def _run(monkeypatch, resultado=None, get_llm=None):
    monkeypatch.setattr(src.agent, "ask", lambda q, llm, **kw: resultado or _resultado())
    monkeypatch.setattr(src.llm, "get_llm", get_llm or (lambda: object()))
    at = AppTest.from_file(APP, default_timeout=10).run()
    at.chat_input[0].set_value("Pergunta?").run()
    return at


def test_answer_chart_and_reasoning(monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception
    assert TEXTO in [m.value for m in at.markdown]
    assert any(e.label == "Como cheguei aqui" for e in at.expander)
    assert len(at.session_state["historico"]) == 1


def test_table_and_empty_table(monkeypatch):
    at = _run(monkeypatch, _resultado(visualizacao="tabela", x=None, y=None))
    assert not at.exception and len(at.dataframe) == 1
    vazio = _resultado(dados=pd.DataFrame({"a": []}), visualizacao="tabela", x=None, y=None)
    at = _run(monkeypatch, vazio)
    assert not at.exception
    assert any("não retornou linhas" in i.value for i in at.info)


def test_missing_key_shows_error(monkeypatch):
    def boom():
        raise RuntimeError("Defina OPENAI_API_KEY no .env")

    at = _run(monkeypatch, get_llm=boom)
    assert not at.exception
    assert any("OPENAI_API_KEY" in e.value for e in at.error)


def test_example_button_asks(monkeypatch):
    monkeypatch.setattr(src.agent, "ask", lambda q, llm, **kw: _resultado())
    monkeypatch.setattr(src.llm, "get_llm", lambda: object())
    at = AppTest.from_file(APP, default_timeout=10).run()
    assert len(at.sidebar.button) == 5
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert len(at.session_state["historico"]) == 1


def test_multi_series_line_chart(monkeypatch):
    longo = pd.DataFrame(
        {
            "mes": ["2025-01", "2025-01", "2025-02", "2025-02"],
            "canal": ["Chat", "Telefone", "Chat", "Telefone"],
            "n": [3, 5, 4, 2],
        }
    )
    desenhados = []
    monkeypatch.setattr(streamlit, "line_chart", lambda dados, **kw: desenhados.append(dados))
    res = _resultado(dados=longo, visualizacao="linha", x="mes", y="n", serie="canal")
    at = _run(monkeypatch, res)
    assert not at.exception
    assert len(at.dataframe) == 0  # drawn as a chart, not a table
    # One column (line) per channel, indexed by month.
    assert list(desenhados[0].columns) == ["Chat", "Telefone"]
    assert list(desenhados[0].index) == ["2025-01", "2025-02"]
    assert desenhados[0].loc["2025-01", "Telefone"] == 5
