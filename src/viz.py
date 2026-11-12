"""Decide what the UI renders, validating the LLM's chart request against real data."""

import pandas as pd

_CHARTS = {"barra", "linha"}


def _result(
    tipo: str, x: str | None = None, y: str | None = None, serie: str | None = None
) -> dict:
    return {"tipo": tipo, "x": x, "y": y, "serie": serie}


def _escolher_serie(df: pd.DataFrame, x: str, y: str, serie: str | None) -> str | None:
    """Valid series column for a long-format chart, or None if not needed / not found."""
    if serie in df.columns and serie not in (x, y):
        return serie
    if not df[x].duplicated().any():
        return None
    # x repeats: look for exactly one other non-numeric column to split the series.
    candidatas = [
        c
        for c in df.columns
        if c not in (x, y) and not pd.api.types.is_numeric_dtype(df[c])
    ]
    return candidatas[0] if len(candidatas) == 1 else None


def escolher_visualizacao(
    df: pd.DataFrame | None,
    pedido: str,
    x: str | None,
    y: str | None,
    serie: str | None = None,
) -> dict:
    """Return {"tipo", "x", "y", "serie"} for what should actually be rendered."""
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
        serie = _escolher_serie(df, x, y, serie)
        if serie is None and df[x].duplicated().any():
            # Several rows per x and nothing to split them by: a chart would zigzag.
            return _result("tabela")
        return _result(pedido, x, y, serie)
    return _result("tabela")
