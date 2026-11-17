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
