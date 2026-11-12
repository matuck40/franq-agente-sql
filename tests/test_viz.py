import pandas as pd

from src.viz import escolher_visualizacao


def _df():
    return pd.DataFrame({"mes": ["jan", "fev"], "total": [10, 20]})


def test_valid_bar_is_kept():
    r = escolher_visualizacao(_df(), "barra", "mes", "total")
    assert r == {"tipo": "barra", "x": "mes", "y": "total"}


def test_valid_line_is_kept():
    r = escolher_visualizacao(_df(), "linha", "mes", "total")
    assert r == {"tipo": "linha", "x": "mes", "y": "total"}


def test_x_not_in_columns_falls_back_to_table():
    r = escolher_visualizacao(_df(), "barra", "nope", "total")
    assert r == {"tipo": "tabela", "x": None, "y": None}


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
    }


def test_unknown_request_maps_to_table():
    r = escolher_visualizacao(_df(), "pizza", "mes", "total")
    assert r == {"tipo": "tabela", "x": None, "y": None}


def test_number_requested_on_multi_row_df_maps_to_table():
    r = escolher_visualizacao(_df(), "numero", None, None)
    assert r == {"tipo": "tabela", "x": None, "y": None}


def test_text_requested_with_data_maps_to_table():
    r = escolher_visualizacao(_df(), "texto", None, None)
    assert r["tipo"] == "tabela"
