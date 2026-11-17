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

# Largest string or blob a query may build (SQLite's default is 1 GB). The deadline
# and the row cap do not bound the size of one value: randomblob(100000000) returned a
# 100 MB cell in 0.6 s. This limit applies to every function (randomblob, zeroblob,
# printf, replace...), not only to a list of known ones.
MAX_BYTES_POR_VALOR = 1_000_000

_MSG_GRANDE = (
    "Valor grande demais: um texto ou blob passou de {limite} bytes. Consulte só os "
    "dados necessários, sem gerar valores grandes."
)

# Largest total size of one result (sum of its values). The per-value cap alone did
# not bound a result: rows times columns times 1 MB.
MAX_BYTES_TOTAL = 20_000_000

_MSG_TOTAL = (
    "Resultado grande demais: passou de {limite} bytes no total. Selecione menos "
    "colunas ou linhas, ou agregue os dados."
)


def _tamanho(valor: object) -> int:
    """Approximate bytes of one value: length for text and blobs, 8 otherwise."""
    return len(valor) if isinstance(valor, (str, bytes)) else 8


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
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_BYTES_POR_VALOR)
            conn.set_progress_handler(_checar_prazo, _PASSOS_ENTRE_CHECAGENS)
            with closing(conn.execute(sql)) as cur:
                colunas = [d[0] for d in cur.description or []]
                # Row by row, so memory stays near MAX_BYTES_TOTAL even when each
                # value is under the per-value cap (150 rows of ~1 MB ran in 0.013 s).
                linhas, total = [], 0
                for linha in cur:
                    linhas.append(linha)
                    total += sum(_tamanho(v) for v in linha)
                    if total > MAX_BYTES_TOTAL:
                        raise SQLError(_MSG_TOTAL.format(limite=MAX_BYTES_TOTAL))
                    if len(linhas) > max_linhas:
                        break
    except (sqlite3.Error, sqlite3.Warning) as e:
        if estourou:
            raise SQLError(
                f"A consulta demorou mais de {timeout_s:g} s e foi interrompida; "
                "simplifique a consulta ou adicione filtros."
            ) from e
        if getattr(e, "sqlite_errorcode", None) == sqlite3.SQLITE_TOOBIG:
            raise SQLError(_MSG_GRANDE.format(limite=MAX_BYTES_POR_VALOR)) from e
        if "prohibited" in str(e):  # SQLite: "access to clientes.nome is prohibited"
            raise SQLError(_MSG_PESSOAIS.format(detalhe=e)) from e
        raise SQLError(str(e)) from e

    truncado = len(linhas) > max_linhas
    df = pd.DataFrame.from_records(linhas[:max_linhas], columns=colunas, coerce_float=True)
    df.attrs["truncado"] = truncado
    return df


def to_llm_text(df: pd.DataFrame, max_linhas: int = 200, max_caracteres: int = 20_000) -> str:
    """CSV of the first max_linhas rows, cut at max_caracteres, with a note when rows
    or text were left out."""
    total = len(df)
    texto = df.head(max_linhas).to_csv(index=False).rstrip("\n")
    if len(texto) > max_caracteres:
        texto = texto[:max_caracteres] + (
            f"\n(texto cortado em {max_caracteres} caracteres: o resultado é largo demais; "
            "selecione menos colunas ou linhas)"
        )
    if total > max_linhas:
        texto += f"\n(... {total} linhas no total, mostrando {max_linhas})"
    if df.attrs.get("truncado"):
        texto += (
            f"\n(resultado truncado: a consulta tinha mais de {total} linhas e só as "
            f"primeiras {total} foram lidas)"
        )
    return texto
