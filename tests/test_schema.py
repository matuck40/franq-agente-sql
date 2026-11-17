import hashlib
import sqlite3
from pathlib import Path

import pytest

from src.schema import format_schema, get_schema

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


def test_categoricas_listam_todos_os_valores(schema):
    assert sorted(coluna(schema, "compras", "canal")["valores"]) == ["App", "Loja Física", "Site"]


def test_colunas_pessoais_nao_expoem_valores(schema):
    for nome in ("nome", "email"):
        c = coluna(schema, "clientes", nome)
        assert "valores" not in c and "intervalo" not in c


def test_datas_trazem_intervalo(schema):
    assert coluna(schema, "compras", "data_compra")["intervalo"] == ["2024-07-22", "2025-07-22"]


def test_format_schema_texto(schema):
    texto = format_schema(schema)
    assert "compras" in texto and "Loja Física" in texto and "2025-07-22" in texto
    assert "@example" not in texto and "sqlite_sequence" not in texto


def test_nao_altera_o_banco():
    if not DB_PATH.exists():
        pytest.skip("banco do desafio ausente em data/")
    antes = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
    get_schema(str(DB_PATH))
    depois = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
    assert antes == depois


def test_banco_inexistente_da_erro_e_nao_cria_arquivo(tmp_path):
    caminho = tmp_path / "nao_existe.db"
    with pytest.raises(sqlite3.OperationalError):
        get_schema(str(caminho))
    assert not caminho.exists()


def test_booleanos_mostram_zero_e_um(schema):
    assert coluna(schema, "suporte", "resolvido")["valores"] == ["0", "1"]


def test_guarda_pessoal_vale_mesmo_com_poucos_valores_e_datas(tmp_path):
    caminho = tmp_path / "mini.db"
    conn = sqlite3.connect(caminho)
    conn.execute("CREATE TABLE clientes (id INTEGER, nome TEXT, email TEXT)")
    conn.executemany(
        "INSERT INTO clientes VALUES (?, ?, ?)",
        [(1, "Ana", "2024-01-01"), (2, "Bia", "2024-02-02"), (3, "Ana", "2024-03-03")],
    )
    conn.commit()
    conn.close()
    mini = get_schema(str(caminho))
    for nome in ("nome", "email"):
        c = coluna(mini, "clientes", nome)
        assert "valores" not in c and "intervalo" not in c
