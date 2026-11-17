"""Compare the agent's final data with a reference result (used by scripts/run_examples.py)."""
import numbers
from collections import Counter
from itertools import permutations

import pandas as pd


def _normalizar(valor: object) -> object:
    """Numbers rounded to 2 decimals (int and float compare equal); text stripped."""
    if isinstance(valor, numbers.Number) and not isinstance(valor, bool):
        return round(float(valor), 2)
    return str(valor).strip()


def _linhas(df: pd.DataFrame, colunas) -> Counter:
    return Counter(
        tuple(_normalizar(v) for v in linha)
        for linha in df[list(colunas)].itertuples(index=False, name=None)
    )


def mesmos_dados(
    agente: pd.DataFrame | None,
    referencia: pd.DataFrame,
    colunas: list[str],
    minimo: int | None = None,
) -> bool:
    """True if the agent's data holds the reference rows on the given columns.

    Agent column names do not matter: any choice of agent columns whose values
    match counts, and extra agent columns are ignored. Without `minimo`, the
    rows must be the same (as a multiset). With `minimo`, the agent may return a
    subset of the reference with at least `minimo` rows (for top-N with ties,
    where the reference lists every tied row).
    """
    if agente is None or agente.empty or len(agente.columns) < len(colunas):
        return False
    esperado = _linhas(referencia, colunas)
    for escolha in permutations(agente.columns, len(colunas)):
        obtido = _linhas(agente, escolha)
        if minimo is None:
            if obtido == esperado:
                return True
        elif len(agente) >= minimo and all(n <= esperado[k] for k, n in obtido.items()):
            return True
    return False
