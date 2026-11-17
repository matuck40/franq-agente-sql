from pathlib import Path

import pytest

from src.db import DB_PATH
from src.prompts import build_system_prompt


@pytest.fixture(scope="module")
def prompt():
    if not Path(DB_PATH).exists():
        pytest.skip("banco do desafio ausente em data/")
    return build_system_prompt(DB_PATH)


def test_define_media_por_cliente_entre_compradores_da_categoria(prompt):
    assert "média por cliente" in prompt.lower()
    assert "clientes distintos que compraram naquela categoria" in prompt
