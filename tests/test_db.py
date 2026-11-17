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


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT nome FROM clientes",
        "SELECT email FROM clientes WHERE id = 1",
        "SELECT NOME FROM CLIENTES",
        "SELECT c.email FROM clientes c",
        "WITH x AS (SELECT nome FROM clientes) SELECT * FROM x",
        "SELECT estado FROM clientes WHERE email LIKE '%@%'",
        "SELECT COUNT(DISTINCT nome) AS n FROM clientes",
        (
            "SELECT id FROM compras WHERE cliente_id IN "
            "(SELECT id FROM clientes WHERE nome LIKE 'A%')"
        ),
    ],
)
def test_colunas_pessoais_sao_bloqueadas(sql):
    with pytest.raises(SQLError, match="dados pessoais"):
        run_query(sql, DB_PATH)


def test_select_estrela_em_clientes_explica_o_bloqueio():
    with pytest.raises(SQLError, match="liste só as colunas") as erro:
        run_query("SELECT * FROM clientes", DB_PATH)
    assert "clientes.nome" in str(erro.value) or "clientes.email" in str(erro.value)


def test_outras_colunas_de_clientes_continuam_liberadas():
    df = run_query(
        "SELECT c.estado, COUNT(DISTINCT p.cliente_id) AS n "
        "FROM compras p JOIN clientes c ON c.id = p.cliente_id GROUP BY c.estado",
        DB_PATH,
    )
    assert len(df) > 0
    assert run_query("SELECT COUNT(*) AS n FROM clientes", DB_PATH)["n"][0] == 100


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT randomblob(100000000) AS b",  # one 100 MB cell ran in 0.6 s before
        "SELECT zeroblob(2000000) AS b",
        "SELECT printf('%.*c', 5000000, 'x') AS t",  # large text from another function
    ],
)
def test_valor_grande_demais_e_recusado(sql):
    with pytest.raises(SQLError, match="grande demais"):
        run_query(sql, DB_PATH)


def test_texto_para_o_llm_tem_limite_de_caracteres():
    import pandas as pd

    df = pd.DataFrame({"t": ["x" * 1000] * 100})  # ~100k characters in 100 rows
    texto = to_llm_text(df, max_caracteres=5000)
    assert len(texto) < 5300
    assert "texto cortado" in texto


def test_resultado_grande_demais_no_total_e_recusado():
    # Each value is under the 1 MB cap, but 150 of them (~150 MB) ran in 0.013 s.
    sql = (
        "WITH RECURSIVE c(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM c WHERE i < 150) "
        "SELECT zeroblob(999000) AS b FROM c"
    )
    with pytest.raises(SQLError, match="grande demais"):
        run_query(sql, DB_PATH)


def test_erro_de_tabela_com_nome_too_big_nao_vira_valor_grande():
    with pytest.raises(SQLError, match="no such table") as erro:
        run_query('SELECT * FROM "too big"', DB_PATH)
    assert "grande demais" not in str(erro.value)


def test_run_query_aparece_como_passo_no_langsmith():
    from langsmith.run_helpers import is_traceable_function

    assert is_traceable_function(run_query)


def test_resumo_para_o_trace_nao_envia_a_tabela_inteira():
    from src.db import resumo_para_trace

    df = run_query("SELECT * FROM compras", DB_PATH)  # 946 rows
    resumo = resumo_para_trace(df)
    assert resumo["linhas"] == 946
    assert resumo["colunas"] == list(df.columns)
    assert len(resumo["amostra"]) == 5  # first rows only, not the whole table
    assert resumo["truncado"] is False
