import pandas as pd

from src.evaluation import mesmos_dados

REF = pd.DataFrame({"canal": ["Telefone", "Chat", "E-mail"], "n": [19, 18, 14]})


def test_mesmos_dados_com_outros_nomes_e_ordem():
    agente = pd.DataFrame({"total": [14, 19, 18], "canal_contato": ["E-mail", "Telefone", "Chat"]})
    assert mesmos_dados(agente, REF, ["canal", "n"])


def test_valor_diferente_nao_bate():
    agente = pd.DataFrame({"canal": ["Telefone", "Chat", "E-mail"], "n": [19, 18, 15]})
    assert not mesmos_dados(agente, REF, ["canal", "n"])


def test_linhas_a_mais_ou_a_menos_nao_batem():
    assert not mesmos_dados(REF.head(2), REF, ["canal", "n"])
    extra = pd.concat([REF, pd.DataFrame({"canal": ["WhatsApp"], "n": [1]})])
    assert not mesmos_dados(extra, REF, ["canal", "n"])


def test_colunas_extras_do_agente_sao_ignoradas():
    agente = REF.assign(percentual=[37.3, 35.3, 27.5])
    assert mesmos_dados(agente, REF, ["canal", "n"])


def test_numeros_comparados_com_duas_casas():
    ref = pd.DataFrame({"categoria": ["Roupas", "Viagens"], "media": [2.211, 2.162]})
    agente = pd.DataFrame({"categoria": ["Roupas", "Viagens"], "media": [2.2105, 2.1622]})
    assert mesmos_dados(agente, ref, ["categoria", "media"])
    errado = pd.DataFrame({"categoria": ["Roupas", "Viagens"], "media": [1.57, 1.60]})
    assert not mesmos_dados(errado, ref, ["categoria", "media"])


def test_inteiro_e_float_iguais_batem():
    assert mesmos_dados(pd.DataFrame({"x": [17.0]}), pd.DataFrame({"clientes": [17]}), ["clientes"])


def test_sem_dados_nao_bate():
    assert not mesmos_dados(None, REF, ["canal", "n"])
    assert not mesmos_dados(REF.iloc[0:0], REF, ["canal", "n"])


def test_modo_minimo_aceita_subconjunto_com_empates():
    # Reference lists every state tied at the 5th place cut (6 rows).
    ref = pd.DataFrame(
        {"estado": ["SP", "MG", "SC", "PR", "ES", "AL"], "clientes": [6, 3, 3, 2, 2, 2]}
    )
    cinco = pd.DataFrame({"uf": ["SP", "MG", "SC", "PR", "AL"], "n": [6, 3, 3, 2, 2]})
    assert mesmos_dados(cinco, ref, ["estado", "clientes"], minimo=5)
    assert mesmos_dados(ref, ref, ["estado", "clientes"], minimo=5)
    quatro = cinco.head(4)
    assert not mesmos_dados(quatro, ref, ["estado", "clientes"], minimo=5)
    errado = pd.DataFrame({"uf": ["SP", "MG", "SC", "PR", "RJ"], "n": [6, 3, 3, 2, 2]})
    assert not mesmos_dados(errado, ref, ["estado", "clientes"], minimo=5)


def test_modo_minimo_exige_as_linhas_acima_do_empate():
    ref = pd.DataFrame(
        {"estado": ["SP", "MG", "SC", "PR", "ES", "AL"], "clientes": [6, 3, 3, 2, 2, 2]}
    )
    sem_o_primeiro = pd.DataFrame(
        {"uf": ["MG", "SC", "PR", "ES", "AL"], "n": [3, 3, 2, 2, 2]}
    )
    assert not mesmos_dados(sem_o_primeiro, ref, ["estado", "clientes"], minimo=5)


def test_valores_vazios_batem_entre_si():
    ref = pd.DataFrame({"canal": ["Chat", None], "n": [1.0, float("nan")]})
    assert mesmos_dados(ref.copy(), ref, ["canal", "n"])
