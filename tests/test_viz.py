import pandas as pd

from src.viz import escolher_visualizacao


def _df():
    return pd.DataFrame({"mes": ["jan", "fev"], "total": [10, 20]})


def test_valid_bar_is_kept():
    r = escolher_visualizacao(_df(), "barra", "mes", "total")
    assert r == {"tipo": "barra", "x": "mes", "y": "total", "serie": None}


def test_valid_line_is_kept():
    r = escolher_visualizacao(_df(), "linha", "mes", "total")
    assert r == {"tipo": "linha", "x": "mes", "y": "total", "serie": None}


def test_x_not_in_columns_falls_back_to_table():
    r = escolher_visualizacao(_df(), "barra", "nope", "total")
    assert r == {"tipo": "tabela", "x": None, "y": None, "serie": None}


def test_missing_y_falls_back_to_table():
    r = escolher_visualizacao(_df(), "barra", "mes", None)
    assert r["tipo"] == "tabela"


def test_non_numeric_y_falls_back_to_table():
    r = escolher_visualizacao(_df(), "barra", "total", "mes")
    assert r["tipo"] == "tabela"


def test_one_by_one_is_number_regardless_of_request():
    df = pd.DataFrame({"total": [42]})
    assert escolher_visualizacao(df, "barra", "total", "total")["tipo"] == "numero"
    assert escolher_visualizacao(df, "tabela", None, None)["tipo"] == "numero"


def test_none_is_text():
    assert escolher_visualizacao(None, "barra", "a", "b") == {
        "tipo": "texto",
        "x": None,
        "y": None,
        "serie": None,
    }


def test_unknown_request_maps_to_table():
    r = escolher_visualizacao(_df(), "pizza", "mes", "total")
    assert r == {"tipo": "tabela", "x": None, "y": None, "serie": None}


def test_number_requested_on_multi_row_df_maps_to_table():
    r = escolher_visualizacao(_df(), "numero", None, None)
    assert r == {"tipo": "tabela", "x": None, "y": None, "serie": None}


def test_text_requested_with_data_maps_to_table():
    r = escolher_visualizacao(_df(), "texto", None, None)
    assert r["tipo"] == "tabela"


def test_one_row_multi_column_chart_maps_to_table():
    df = pd.DataFrame({"mes": ["jan"], "total": [10]})
    assert escolher_visualizacao(df, "barra", "mes", "total")["tipo"] == "tabela"


def test_zero_row_df_chart_maps_to_table():
    df = pd.DataFrame({"mes": pd.Series([], dtype=object), "total": pd.Series([], dtype=int)})
    assert escolher_visualizacao(df, "linha", "mes", "total")["tipo"] == "tabela"


def test_same_x_and_y_maps_to_table():
    r = escolher_visualizacao(_df(), "barra", "total", "total")
    assert r == {"tipo": "tabela", "x": None, "y": None, "serie": None}


def _longo():
    return pd.DataFrame(
        {
            "mes": ["2025-01", "2025-01", "2025-02", "2025-02"],
            "canal": ["Chat", "Telefone", "Chat", "Telefone"],
            "n": [3, 5, 4, 2],
        }
    )


def test_long_format_with_serie_given():
    r = escolher_visualizacao(_longo(), "linha", "mes", "n", "canal")
    assert r == {"tipo": "linha", "x": "mes", "y": "n", "serie": "canal"}


def test_long_format_serie_auto_detected():
    r = escolher_visualizacao(_longo(), "barra", "mes", "n")
    assert r == {"tipo": "barra", "x": "mes", "y": "n", "serie": "canal"}


def test_invalid_serie_is_ignored_and_then_auto_detected():
    r = escolher_visualizacao(_longo(), "linha", "mes", "n", "mes")
    assert r["serie"] == "canal"


def test_duplicated_x_without_serie_maps_to_table():
    df = _longo().assign(regiao=["N", "S", "N", "S"])  # two candidate columns
    r = escolher_visualizacao(df, "linha", "mes", "n")
    assert r == {"tipo": "tabela", "x": None, "y": None, "serie": None}
    df = _longo().drop(columns="canal")  # nothing to split by
    assert escolher_visualizacao(df, "linha", "mes", "n")["tipo"] == "tabela"
