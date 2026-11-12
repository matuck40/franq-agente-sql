import re
import sqlite3
from contextlib import closing

MAX_CATEGORIAS = 20
PERSONAL_COLUMNS = {("clientes", "nome"), ("clientes", "email")}
DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _descrever_coluna(conn, tabela, nome, tipo):
    coluna = {"nome": nome, "tipo": tipo}
    if (tabela, nome) in PERSONAL_COLUMNS:
        return coluna

    minimo, maximo, distintos = conn.execute(
        f'SELECT MIN("{nome}"), MAX("{nome}"), COUNT(DISTINCT "{nome}") FROM "{tabela}"'
    ).fetchone()

    if (
        tipo == "TEXT"
        and isinstance(minimo, str)
        and isinstance(maximo, str)
        and DATA_ISO.match(minimo)
        and DATA_ISO.match(maximo)
    ):
        coluna["intervalo"] = [minimo, maximo]
    elif 0 < distintos <= MAX_CATEGORIAS and tipo in ("TEXT", "INTEGER"):
        linhas = conn.execute(
            f'SELECT DISTINCT "{nome}" FROM "{tabela}" '
            f'WHERE "{nome}" IS NOT NULL ORDER BY "{nome}"'
        )
        coluna["valores"] = [str(linha[0]) for linha in linhas]
    return coluna


def get_schema(caminho):
    uri = f"file:{caminho}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        tabelas = [
            linha[0]
            for linha in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]

        schema = {}
        for tabela in tabelas:
            infos = conn.execute(f'PRAGMA table_info("{tabela}")').fetchall()
            schema[tabela] = [
                _descrever_coluna(conn, tabela, nome, tipo) for _, nome, tipo, *_ in infos
            ]

    return schema


def format_schema(schema):
    blocos = []
    for tabela, colunas in schema.items():
        linhas = [f"Tabela {tabela}:"]
        for c in colunas:
            linha = f"- {c['nome']} ({c['tipo']})"
            if "valores" in c:
                linha += f": valores = {', '.join(c['valores'])}"
            elif "intervalo" in c:
                linha += f": datas de {c['intervalo'][0]} a {c['intervalo'][1]}"
            linhas.append(linha)
        blocos.append("\n".join(linhas))
    return "\n\n".join(blocos)
