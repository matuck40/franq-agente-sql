from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from src.agent import ask
from src.db import DB_PATH
from src.prompts import build_system_prompt
from tests.fakes import FakeToolLLM

if not Path(DB_PATH).exists():
    pytest.skip("banco do desafio ausente em data/", allow_module_level=True)

SQL_CANAL = "SELECT canal, COUNT(*) n FROM compras GROUP BY canal"


def _run_sql(sql, id_):
    return AIMessage(
        content="", tool_calls=[{"name": "run_sql", "args": {"sql": sql}, "id": id_}]
    )


def _final(id_, **args):
    return AIMessage(
        content="", tool_calls=[{"name": "final_answer", "args": args, "id": id_}]
    )


def test_responde_com_uma_query():
    llm = FakeToolLLM(
        [
            _run_sql(SQL_CANAL, "c1"),
            _final(
                "c2",
                texto="Compras por canal.",
                sql=SQL_CANAL,
                visualizacao="barra",
                x="canal",
                y="n",
            ),
        ]
    )
    r = ask("Quantas compras por canal?", llm)
    assert r["visualizacao"] == "barra"
    assert r["x"] == "canal" and r["y"] == "n"
    assert r["texto"] == "Compras por canal."
    assert r["sql"] == SQL_CANAL
    assert len(r["dados"]) == 3
    assert len(r["passos"]) == 1
    assert r["passos"][0]["erro"] is None
    assert r["passos"][0]["linhas"] == 3


def test_corrige_sql_invalido():
    llm = FakeToolLLM(
        [
            _run_sql("SELECT x FROM compras", "c1"),
            _run_sql(SQL_CANAL, "c2"),
            _final(
                "c3", texto="ok", sql=SQL_CANAL, visualizacao="tabela", x=None, y=None
            ),
        ]
    )
    r = ask("Compras por canal?", llm)
    assert "no such column" in r["passos"][0]["erro"]
    assert r["passos"][0]["linhas"] is None
    assert r["passos"][1]["erro"] is None
    terceira = llm.recebidas[2]
    assert any(
        isinstance(m, ToolMessage) and "ERRO" in m.content for m in terceira
    )
    assert len(r["dados"]) == 3


def test_para_no_limite_de_passos():
    llm = FakeToolLLM([_run_sql("SELECT x FROM compras", f"c{i}") for i in range(10)])
    r = ask("Pergunta difícil", llm, max_passos=3)
    assert len(r["passos"]) == 3
    assert r["visualizacao"] == "texto"
    assert "Não consegui" in r["texto"]
    assert "no such column" in r["texto"]
    assert r["dados"] is None
    assert len(llm.recebidas) == 3


def test_resposta_sem_ferramenta_vira_texto():
    llm = FakeToolLLM([AIMessage(content="Não sei")])
    r = ask("Qual o sentido da vida?", llm)
    assert r["texto"] == "Não sei"
    assert r["dados"] is None
    assert r["visualizacao"] == "texto"
    assert r["passos"] == []


def test_final_answer_com_sql_invalido_vira_fallback():
    llm = FakeToolLLM(
        [
            _run_sql(SQL_CANAL, "c1"),
            _final(
                "c2",
                texto="x",
                sql="SELECT nada FROM compras",
                visualizacao="barra",
                x="canal",
                y="n",
            ),
        ]
    )
    r = ask("Compras por canal?", llm)
    assert "Não consegui" in r["texto"]
    assert r["visualizacao"] == "texto"
    assert r["dados"] is None
    assert len(r["passos"]) == 1


def test_prompt_traz_intervalo_e_regra_de_datas():
    p = build_system_prompt(DB_PATH)
    assert "2025-07-22" in p and "último ano" in p
    assert "2024-07-22" in p
