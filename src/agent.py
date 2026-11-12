"""LangGraph SQL agent: the LLM calls run_sql until it calls final_answer."""
import operator
from typing import Annotated, Literal, TypedDict

import pandas as pd
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from src.db import DB_PATH, SQLError, run_query, to_llm_text
from src.prompts import build_system_prompt

FALLBACK = "Não consegui concluir a análise."

Visualizacao = Literal["tabela", "barra", "linha", "numero", "texto"]


class Passo(TypedDict):
    sql: str
    linhas: int | None
    erro: str | None


class Resultado(TypedDict):
    texto: str
    sql: str | None
    dados: pd.DataFrame | None
    visualizacao: Visualizacao
    x: str | None
    y: str | None
    passos: list[Passo]


# --- Tool schemas exposed to the LLM (descriptions are prompt text, in Portuguese).


class _RunSqlArgs(BaseModel):
    sql: str = Field(description="Uma única consulta SELECT em SQLite.")


class _FinalAnswerArgs(BaseModel):
    texto: str = Field(description="Resposta final ao usuário, em português.")
    sql: str | None = Field(
        description="SQL que gera os dados a exibir, ou null se não houver dados."
    )
    visualizacao: Visualizacao = Field(description="Como exibir os dados.")
    x: str | None = Field(description="Coluna do eixo x (linha/barra), ou null.")
    y: str | None = Field(description="Coluna do eixo y (linha/barra), ou null.")


@tool(
    "run_sql",
    args_schema=_RunSqlArgs,
    description="Executa uma consulta SELECT no banco e devolve o resultado em CSV "
    "(ou 'ERRO: <mensagem>').",
)
def run_sql_tool(sql: str) -> str:
    # Only the schema is used: execution happens in the graph's tools node.
    raise NotImplementedError


@tool(
    "final_answer",
    args_schema=_FinalAnswerArgs,
    description="Entrega a resposta final, o SQL dos dados e a visualização. "
    "Chame sempre ao terminar.",
)
def final_answer_tool(
    texto: str, sql: str | None, visualizacao: str, x: str | None, y: str | None
) -> str:
    # Only the schema is used: the graph ends when this tool is called.
    raise NotImplementedError


class _State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    passos: Annotated[list[Passo], operator.add]
    rodadas: Annotated[int, operator.add]  # tool rounds (agent turns that called tools)


def _tool_calls(msg) -> list[dict]:
    return getattr(msg, "tool_calls", None) or []


def _build_graph(llm, caminho: str, max_passos: int):
    # One tool call per turn, so a single message cannot overshoot max_passos.
    modelo = llm.bind_tools([run_sql_tool, final_answer_tool], parallel_tool_calls=False)

    def agent(state: _State) -> dict:
        return {"messages": [modelo.invoke(state["messages"])]}

    def tools(state: _State) -> dict:
        mensagens, passos = [], []
        for call in _tool_calls(state["messages"][-1]):
            if call["name"] != "run_sql":
                conteudo = f"ERRO: ferramenta desconhecida '{call['name']}'"
            else:
                sql = call["args"].get("sql", "")
                try:
                    df = run_query(sql, caminho)
                except SQLError as e:
                    conteudo = f"ERRO: {e}"
                    passos.append(Passo(sql=sql, linhas=None, erro=str(e)))
                else:
                    conteudo = to_llm_text(df)
                    passos.append(Passo(sql=sql, linhas=len(df), erro=None))
            mensagens.append(ToolMessage(content=conteudo, tool_call_id=call["id"]))
        return {"messages": mensagens, "passos": passos, "rodadas": 1}

    def depois_do_agent(state: _State) -> str:
        calls = _tool_calls(state["messages"][-1])
        if not calls or any(c["name"] == "final_answer" for c in calls):
            return END
        return "tools"

    def depois_das_tools(state: _State) -> str:
        # Bound agent turns too, so turns without run_sql (e.g. unknown tools) end.
        if state["rodadas"] >= max_passos or len(state["passos"]) >= max_passos:
            return END
        return "agent"

    grafo = StateGraph(_State)
    grafo.add_node("agent", agent)
    grafo.add_node("tools", tools)
    grafo.add_edge(START, "agent")
    grafo.add_conditional_edges("agent", depois_do_agent, ["tools", END])
    grafo.add_conditional_edges("tools", depois_das_tools, ["agent", END])
    return grafo.compile()


def _fallback(passos: list[Passo], erro: str | None = None) -> Resultado:
    if erro is None:
        erros = [p["erro"] for p in passos if p["erro"]]
        erro = erros[-1] if erros else None
    texto = FALLBACK if erro is None else f"{FALLBACK}\n\nÚltimo erro: {erro}"
    return Resultado(
        texto=texto, sql=None, dados=None, visualizacao="texto", x=None, y=None, passos=passos
    )


def ask(
    pergunta: str, llm: BaseChatModel, caminho: str = DB_PATH, max_passos: int = 8
) -> Resultado:
    """Answer a business question by letting the LLM query the database."""
    grafo = _build_graph(llm, caminho, max_passos)
    entrada = {
        "messages": [
            SystemMessage(content=build_system_prompt(caminho)),
            HumanMessage(content=pergunta),
        ],
        "passos": [],
        "rodadas": 0,
    }
    # Safety net on top of the round counter: never loop without bound.
    config = {"recursion_limit": 2 * max_passos + 5}
    try:
        estado = grafo.invoke(entrada, config=config)
    except GraphRecursionError:
        return _fallback([])
    passos = estado["passos"]
    ultima = estado["messages"][-1]
    calls = _tool_calls(ultima)

    final = next((c for c in calls if c["name"] == "final_answer"), None)
    if final is None:
        if not isinstance(ultima, AIMessage) or not ultima.text:
            # Step limit reached (last message is a tool result) or empty reply.
            return _fallback(passos)
        return Resultado(
            texto=ultima.text, sql=None, dados=None, visualizacao="texto",
            x=None, y=None, passos=passos,
        )

    args = final["args"]
    sql = args.get("sql")
    if not sql:
        return Resultado(
            texto=args.get("texto", ""), sql=None, dados=None, visualizacao="texto",
            x=None, y=None, passos=passos,
        )
    try:
        dados = run_query(sql, caminho)
    except SQLError as e:
        return _fallback(passos, str(e))
    return Resultado(
        texto=args.get("texto", ""),
        sql=sql,
        dados=dados,
        visualizacao=args.get("visualizacao") or "tabela",
        x=args.get("x"),
        y=args.get("y"),
        passos=passos,
    )
