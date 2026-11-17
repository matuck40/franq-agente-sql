from pathlib import Path

import pytest

from src.db import DB_PATH
from src.prompts import _meses_parciais, build_system_prompt


@pytest.fixture(scope="module")
def prompt():
    if not Path(DB_PATH).exists():
        pytest.skip("banco do desafio ausente em data/")
    return build_system_prompt(DB_PATH)


def test_define_media_por_cliente_entre_compradores_da_categoria(prompt):
    assert "média por cliente" in prompt.lower()
    assert "clientes distintos que compraram naquela categoria" in prompt


@pytest.mark.parametrize(
    "inicio, fim, esperado",
    [
        ("2024-07-22", "2025-07-22", ["2024-07", "2025-07"]),
        ("2024-07-01", "2025-06-30", []),
        ("2024-07-01", "2025-07-22", ["2025-07"]),
        ("2024-02-10", "2024-02-29", ["2024-02"]),  # same month, leap year
        (None, None, []),
    ],
)
def test_meses_parciais(inicio, fim, esperado):
    assert _meses_parciais(inicio, fim) == esperado


def test_avisa_meses_parciais(prompt):
    assert "2024-07, 2025-07" in prompt
    assert "incompletos" in prompt


def test_avisa_empate_no_corte_do_top_n(prompt):
    assert "empate" in prompt
    assert "cite todos os empatados" in prompt


def test_pede_linguagem_de_negocio_sem_nomes_de_coluna(prompt):
    assert "linguagem de negócio" in prompt
    assert "sem nomes de colunas" in prompt
    assert "Como cheguei aqui" in prompt


def test_sql_final_do_top_n_traz_so_o_corte_e_os_empatados(prompt):
    assert "nunca a lista completa" in prompt
    assert "OFFSET" in prompt  # example of the cut-off query


def test_descricao_do_sql_final_pede_so_os_dados_da_resposta():
    from src.agent import final_answer_tool

    props = final_answer_tool.args_schema.model_json_schema()["properties"]
    descricao = props["sql"]["description"]
    assert "exatamente" in descricao
    assert "exploratória" in descricao


def test_define_reclamacao_como_tipo_de_contato(prompt):
    assert "tipo_contato = 'Reclamação'" in prompt
    assert "não todos os contatos de suporte" in prompt
