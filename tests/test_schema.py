import hashlib
from pathlib import Path

import pytest

from src.schema import get_schema

DB_PATH = Path("data/anexo_desafio_1.db")
TABELAS_ESPERADAS = {"clientes", "compras", "suporte", "campanhas_marketing"}


@pytest.fixture(scope="module")
def schema():
    if not DB_PATH.exists():
        pytest.skip("banco do desafio ausente em data/")
    return get_schema(str(DB_PATH))


def coluna(schema, tabela, nome):
    return next(c for c in schema[tabela] if c["nome"] == nome)


def test_devolve_as_quatro_tabelas_sem_internas(schema):
    assert set(schema) == TABELAS_ESPERADAS


def test_colunas_trazem_nome_e_tipo(schema):
    assert coluna(schema, "clientes", "estado")["tipo"] == "TEXT"
    assert coluna(schema, "clientes", "idade")["tipo"] == "INTEGER"


def test_exemplos_so_nas_colunas_de_texto(schema):
    assert "São Paulo" in coluna(schema, "clientes", "estado")["exemplos"]
    assert "exemplos" not in coluna(schema, "clientes", "idade")


def test_no_maximo_cinco_exemplos(schema):
    for colunas in schema.values():
        for c in colunas:
            assert len(c.get("exemplos", [])) <= 5


def test_nao_altera_o_banco():
    if not DB_PATH.exists():
        pytest.skip("banco do desafio ausente em data/")
    antes = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
    get_schema(str(DB_PATH))
    depois = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
    assert antes == depois


def test_banco_inexistente_da_erro_e_nao_cria_arquivo(tmp_path):
    caminho = tmp_path / "nao_existe.db"
    with pytest.raises(Exception):
        get_schema(str(caminho))
    assert not caminho.exists()
