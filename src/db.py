"""Safe, read-only, time- and row-bounded SQL execution, plus CSV text for the LLM."""
import sqlite3
import time
from contextlib import closing

import pandas as pd

from src.schema import PERSONAL_COLUMNS

DB_PATH = "data/anexo_desafio_1.db"

_PERMITIDOS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}

# How many SQLite VM instructions run between two deadline checks.
_PASSOS_ENTRE_CHECAGENS = 1000


class SQLError(Exception):
    """SQL error; its message is shown to the LLM so it can fix the query."""


_PESSOAIS = {(t.lower(), c.lower()) for t, c in PERSONAL_COLUMNS}

_MSG_PESSOAIS = (
    "Acesso negado a dados pessoais ({detalhe}): as colunas clientes.nome e "
    "clientes.email não podem ser lidas. Se usou SELECT *, liste só as colunas "
    "de que precisa."
)


def _autorizador(acao: int, tabela: object, coluna: object, *_: object) -> int:
    """Allow only reads; every other action (writes, ATTACH, PRAGMA...) is denied.

    Reading a personal column (clientes.nome, clientes.email) is denied too, so no
    query can return those values, whatever the prompt or the LLM does.
    """
    if acao not in _PERMITIDOS:
        return sqlite3.SQLITE_DENY
    if (
        acao == sqlite3.SQLITE_READ
        and isinstance(tabela, str)
        and isinstance(coluna, str)
        and (tabela.lower(), coluna.lower()) in _PESSOAIS
    ):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _verificar_instrucao_unica(sql: str) -> None:
    """Raise SQLError if sql holds more than one statement."""
    # complete_statement understands quotes, so a ';' inside a string does not count.
    for i, c in enumerate(sql):
        if c == ";" and sqlite3.complete_statement(sql[: i + 1]):
            if sql[i + 1 :].strip():
                raise SQLError("Apenas uma instrução SQL por vez é permitida.")
            return


def run_query(
    sql: str, caminho: str, timeout_s: float = 10.0, max_linhas: int = 10_000
) -> pd.DataFrame:
    """Run one read-only query; stop after timeout_s and keep at most max_linhas rows.

    If the query had more rows, the DataFrame has attrs["truncado"] = True.
    """
    _verificar_instrucao_unica(sql)
    uri = f"file:{caminho}?mode=ro"
    prazo = time.monotonic() + timeout_s
    estourou = False

    def _checar_prazo() -> int:
        nonlocal estourou
        if time.monotonic() > prazo:
            estourou = True
            return 1  # nonzero interrupts the running statement
        return 0

    try:
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.set_authorizer(_autorizador)
            conn.set_progress_handler(_checar_prazo, _PASSOS_ENTRE_CHECAGENS)
            with closing(conn.execute(sql)) as cur:
                linhas = cur.fetchmany(max_linhas + 1)
                colunas = [d[0] for d in cur.description or []]
    except (sqlite3.Error, sqlite3.Warning) as e:
        if estourou:
            raise SQLError(
                f"A consulta demorou mais de {timeout_s:g} s e foi interrompida; "
                "simplifique a consulta ou adicione filtros."
            ) from e
        if "prohibited" in str(e):  # SQLite: "access to clientes.nome is prohibited"
            raise SQLError(_MSG_PESSOAIS.format(detalhe=e)) from e
        raise SQLError(str(e)) from e

    truncado = len(linhas) > max_linhas
    df = pd.DataFrame.from_records(linhas[:max_linhas], columns=colunas, coerce_float=True)
    df.attrs["truncado"] = truncado
    return df


def to_llm_text(df: pd.DataFrame, max_linhas: int = 200) -> str:
    """CSV of the first max_linhas rows, with a note when rows were left out."""
    total = len(df)
    texto = df.head(max_linhas).to_csv(index=False).rstrip("\n")
    if total > max_linhas:
        texto += f"\n(... {total} linhas no total, mostrando {max_linhas})"
    if df.attrs.get("truncado"):
        texto += (
            f"\n(resultado truncado: a consulta tinha mais de {total} linhas e só as "
            f"primeiras {total} foram lidas)"
        )
    return texto
