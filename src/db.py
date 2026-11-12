import sqlite3
from contextlib import closing

import pandas as pd

DB_PATH = "data/anexo_desafio_1.db"

_PERMITIDOS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


class SQLError(Exception):
    """Erro de SQL; a mensagem e mostrada ao LLM para ele corrigir a consulta."""


def _autorizador(acao, *_):
    return sqlite3.SQLITE_OK if acao in _PERMITIDOS else sqlite3.SQLITE_DENY


def _verificar_instrucao_unica(sql):
    # complete_statement entende aspas, entao ';' dentro de string nao conta.
    for i, c in enumerate(sql):
        if c == ";" and sqlite3.complete_statement(sql[: i + 1]):
            if sql[i + 1 :].strip():
                raise SQLError("Apenas uma instrucao SQL por vez e permitida.")
            return


def run_query(sql, caminho):
    _verificar_instrucao_unica(sql)
    uri = f"file:{caminho}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.set_authorizer(_autorizador)
            return pd.read_sql_query(sql, conn)
    except (sqlite3.Error, sqlite3.Warning, pd.errors.DatabaseError) as e:
        # pandas embrulha o erro original; a mensagem original e preservada.
        raise SQLError(str(e)) from e


def to_llm_text(df, max_linhas=200):
    total = len(df)
    texto = df.head(max_linhas).to_csv(index=False).rstrip("\n")
    if total > max_linhas:
        texto += f"\n(... {total} linhas no total, mostrando {max_linhas})"
    return texto
