import time
from pathlib import Path

import pytest

from src.db import DB_PATH, SQLError, run_query, to_llm_text

if not Path(DB_PATH).exists():
    pytest.skip("banco do desafio ausente em data/", allow_module_level=True)


def test_select_devolve_dataframe():
    df = run_query("SELECT canal, COUNT(*) AS n FROM compras GROUP BY canal", DB_PATH)
    assert list(df.columns) == ["canal", "n"] and df["n"].sum() == 946


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM clientes",
        "DROP TABLE clientes",
        "ATTACH DATABASE 'x.db' AS x",
        "SELECT 1; DELETE FROM clientes",
        "PRAGMA writable_schema = 1",
    ],
)
def test_bloqueia_escrita(sql):
    with pytest.raises(SQLError):
        run_query(sql, DB_PATH)
    assert run_query("SELECT COUNT(*) AS n FROM clientes", DB_PATH)["n"][0] == 100


def test_sql_invalido_vira_sqlerror_com_mensagem():
    with pytest.raises(SQLError, match="no such column"):
        run_query("SELECT coluna_inexistente FROM clientes", DB_PATH)


def test_to_llm_text_trunca():
    df = run_query("SELECT * FROM compras", DB_PATH)
    texto = to_llm_text(df)
    assert texto.count("\n") <= 202 and "946 linhas no total" in texto


def test_permite_cte_recursiva_e_ponto_e_virgula_final():
    df = run_query(
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x<3) "
        "SELECT x FROM c;",
        DB_PATH,
    )
    assert list(df["x"]) == [1, 2, 3]


def test_ponto_e_virgula_dentro_de_string_nao_conta():
    df = run_query("SELECT 'a;b' AS t", DB_PATH)
    assert df["t"][0] == "a;b"


def test_autorizador_bloqueia_antes_do_modo_somente_leitura():
    # mode=ro alone would say "attempt to write a readonly database"; this message
    # can only come from the authorizer, so the authorizer layer works on its own.
    with pytest.raises(SQLError, match="not authorized"):
        run_query("DELETE FROM clientes", DB_PATH)


def test_cte_infinita_e_interrompida_pelo_timeout():
    sql = (
        "WITH RECURSIVE c(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM c) "
        "SELECT COUNT(*) FROM c"
    )
    inicio = time.monotonic()
    with pytest.raises(SQLError, match="demorou mais de 0.5 s"):
        run_query(sql, DB_PATH, timeout_s=0.5)
    assert time.monotonic() - inicio < 3


def test_limite_de_linhas_marca_truncado():
    df = run_query("SELECT * FROM compras", DB_PATH, max_linhas=10)
    assert len(df) == 10 and df.attrs["truncado"] is True
    assert "resultado truncado" in to_llm_text(df)


def test_resultado_completo_nao_e_truncado():
    df = run_query("SELECT * FROM compras", DB_PATH)
    assert len(df) == 946 and df.attrs["truncado"] is False
    assert "resultado truncado" not in to_llm_text(df)
