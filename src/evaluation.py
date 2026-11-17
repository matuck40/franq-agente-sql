"""Compare the agent's final data with a reference result (used by scripts/run_examples.py)."""
import math
import numbers
from collections import Counter
from itertools import permutations

import pandas as pd


def _normalizar(valor: object) -> object:
    """Numbers rounded to 2 decimals (int and float compare equal); text stripped.
    Missing values (None, NaN) all become the same marker, so they match each other."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "<vazio>"
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
    where the reference lists every tied row). The last column in `colunas` is the
    ranking value: every reference row above the tied value at the cut (the value
    of the last reference row) is required.
    """
    if agente is None or agente.empty or len(agente.columns) < len(colunas):
        return False
    esperado = _linhas(referencia, colunas)
    if minimo is not None:
        corte = _normalizar(referencia[colunas[-1]].iloc[-1])
        obrigatorias = Counter({k: n for k, n in esperado.items() if k[-1] != corte})
    for escolha in permutations(agente.columns, len(colunas)):
        obtido = _linhas(agente, escolha)
        if minimo is None:
            if obtido == esperado:
                return True
        elif (
            len(agente) >= minimo
            and all(n <= esperado[k] for k, n in obtido.items())
            and all(obtido[k] >= n for k, n in obrigatorias.items())
        ):
            return True
    return False
