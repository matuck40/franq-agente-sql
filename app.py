"""Streamlit chat UI for the virtual data analyst."""
import streamlit as st

from src import agent, llm, viz

EXEMPLOS = [
    "Liste os 5 estados com maior número de clientes que compraram via app em maio.",
    "Quantos clientes interagiram com campanhas de WhatsApp em 2024?",
    "Quais categorias de produto tiveram o maior número de compras em média por cliente?",
    "Qual o número de reclamações não resolvidas por canal?",
    "Qual a tendência de reclamações por canal no último ano?",
]


def render_dados(res: dict) -> None:
    """Render the data using the validated choice from viz, never the raw LLM one."""
    df = res["dados"]
    if df is None:
        return
    escolha = viz.escolher_visualizacao(
        df, res["visualizacao"], res["x"], res["y"], res.get("serie")
    )
    tipo, x, y, serie = escolha["tipo"], escolha["x"], escolha["y"], escolha["serie"]
    if tipo in ("barra", "linha"):
        if serie:
            # Long format (x, serie, y) -> one column per series, one line/bar each.
            dados = df.pivot_table(index=x, columns=serie, values=y, aggfunc="sum")
        else:
            dados = df.set_index(x)[y]
        if tipo == "linha":
            st.line_chart(dados.sort_index())
        else:
            st.bar_chart(dados)
    elif tipo == "numero":
        st.metric(str(df.columns[0]), str(df.iloc[0, 0]))
    elif tipo == "tabela":
        if df.empty:
            st.info("A consulta não retornou linhas.")
        st.dataframe(df)


def render_passos(passos: list) -> None:
    with st.expander("Como cheguei aqui"):
        if not passos:
            st.write("Nenhuma consulta foi executada.")
        for i, p in enumerate(passos, 1):
            st.markdown(f"**Consulta {i}**")
            st.code(p["sql"], language="sql")
            if p["erro"]:
                st.error(p["erro"])
            else:
                st.caption(f"{p['linhas']} linhas")


def render_turno(turno: dict) -> None:
    with st.chat_message("user"):
        st.write(turno["pergunta"])
    with st.chat_message("assistant"):
        if "erro" in turno:
            st.error(turno["erro"])
            return
        res = turno["resultado"]
        st.write(res["texto"])
        render_dados(res)
        render_passos(res["passos"])


def responder(pergunta: str) -> dict:
    try:
        modelo = llm.get_llm()
    except RuntimeError as e:
        return {
            "pergunta": pergunta,
            "erro": f"{e}. Copie .env.example para .env, preencha a chave e reinicie o app.",
        }
    try:
        return {"pergunta": pergunta, "resultado": agent.ask(pergunta, modelo)}
    except Exception as e:  # noqa: BLE001 - keep the page alive on unexpected failures
        return {"pergunta": pergunta, "erro": f"Erro ao processar a pergunta: {e}"}


st.set_page_config(page_title="Analista de Dados Virtual", page_icon="📊")
st.title("Analista de Dados Virtual")
st.caption("Faça perguntas de negócio em português sobre os dados da Franq.")

if "historico" not in st.session_state:
    st.session_state["historico"] = []

clicada = None
with st.sidebar:
    st.header("Exemplos")
    for i, ex in enumerate(EXEMPLOS):
        if st.button(ex, key=f"ex{i}", use_container_width=True):
            clicada = ex

pergunta = st.chat_input("Pergunte algo sobre os dados...") or clicada
if pergunta:
    with st.spinner("Analisando os dados..."):
        st.session_state["historico"].append(responder(pergunta))

for turno in st.session_state["historico"]:
    render_turno(turno)
