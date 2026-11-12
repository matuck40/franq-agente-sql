"""Decide what the UI renders, validating the LLM's chart request against real data."""

import pandas as pd

_CHARTS = {"barra", "linha"}


def _result(tipo: str, x: str | None = None, y: str | None = None) -> dict:
    return {"tipo": tipo, "x": x, "y": y}


def escolher_visualizacao(
    df: pd.DataFrame | None, pedido: str, x: str | None, y: str | None
) -> dict:
    """Return {"tipo", "x", "y"} for what should actually be rendered."""
    if df is None:
        return _result("texto")
    if df.shape == (1, 1):
        return _result("numero")
    if (
        pedido in _CHARTS
        and len(df) > 1
        and x != y
        and x in df.columns
        and y in df.columns
        and pd.api.types.is_numeric_dtype(df[y])
    ):
        return _result(pedido, x, y)
    return _result("tabela")
