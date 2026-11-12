import sqlite3
from contextlib import closing

MAX_EXEMPLOS = 5


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
            colunas = []
            for _, nome, tipo, *_ in conn.execute(f'PRAGMA table_info("{tabela}")'):
                coluna = {"nome": nome, "tipo": tipo}
                if tipo == "TEXT":
                    linhas = conn.execute(
                        f'SELECT DISTINCT "{nome}" FROM "{tabela}" '
                        f'WHERE "{nome}" IS NOT NULL LIMIT {MAX_EXEMPLOS}'
                    )
                    coluna["exemplos"] = [linha[0] for linha in linhas]
                colunas.append(coluna)
            schema[tabela] = colunas

    return schema
