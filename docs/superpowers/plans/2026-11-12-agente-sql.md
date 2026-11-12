# Franq SQL Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "virtual data analyst": a director asks a business question in Portuguese, an agent investigates `anexo_desafio_1.db` with as many read-only SQL queries as it needs, fixes its own SQL errors, and a Streamlit page shows the answer, a table or chart, and every query it ran.

**Architecture:** A LangGraph loop (`agent` node ⇄ `tools` node). The LLM sees the live schema and has two tools: `run_sql` (read-only execution, returns rows or the error text, so the LLM corrects itself) and `final_answer` (text + which query to chart + chart type). The final data is re-executed by code from the chosen SQL, never copied from LLM text. Streamlit calls `ask()` and renders the result.

**Tech Stack:** Python 3.11, LangGraph + langchain-core, langchain-openai (default model `gpt-5-mini`, swappable by env var), SQLite (`sqlite3`), pandas, Streamlit, pytest, ruff.

**Spec:** the challenge PDF "Desafio Técnico 1" (Franq, received 2026-11-12, deadline 2026-11-18) plus decisions in this session. Requirements quoted below in Global Constraints.

## Global Constraints

- Backend in Python receives a question and answers by querying the database. No hardcoded queries; schema discovered at runtime (`src/schema.py`).
- Must handle multi-step questions (more than one query) and invalid SQL (see the error, retry alone).
- Frontend: Streamlit. Shows a table for lists, a bar/line chart for comparisons/trends, or what the user asked for. Shows the reasoning: every query executed, its row count or error.
- Database is opened only in SQLite read-only mode (`file:...?mode=ro`, `uri=True`) and every statement passes an authorizer that allows only reads.
- Data spans 2024-07-22 to 2025-07-22. Relative periods ("último ano", "maio") are resolved against the data range, not today's date.
- Personal columns (`clientes.nome`, `clientes.email`) never have values sent to the LLM in the schema.
- Max 8 agent iterations per question; max 200 rows returned to the LLM per query.
- Tests never call a real LLM: they use a fake chat model. Real-LLM checks live in `scripts/` and are run by hand.
- Public repo: code, README, commit messages in English. UI text and prompts in Portuguese.
- Secrets only in `.env` (gitignored); `.env.example` committed with empty values. Dependencies pinned in `requirements.txt`.
- README has: run instructions, agent flow and architecture, example queries actually tested (with real outputs), improvement suggestions. Nothing claimed that was not run.

## Review Focus

1. **Relative dates** ("no último ano", "em maio"): expected to use the data range. Pinned by Task 1 (schema shows the date range) and Task 4 (system prompt states the rule; test asserts the prompt contains the range).
2. **LLM never finishes** (keeps calling `run_sql` or replies with plain text): expected a polite "não consegui concluir" answer with the steps so far, never a crash or infinite loop. Pinned in Task 4.
3. **Destructive or escaping SQL** from the LLM (`DELETE`, `DROP`, `ATTACH`, `PRAGMA` writes, two statements): expected to be refused with an error the LLM sees, database unchanged. Pinned in Task 2.
4. **Chart spec that doesn't fit the data** (column names not in the result, non-numeric y, one row): expected fallback to a table or a single number. Pinned in Task 5.
5. **Huge result** (`SELECT * FROM compras`, 946 rows): expected the LLM gets at most 200 rows and is told the result was truncated; the UI still gets the full final dataframe. Pinned in Task 2.

---

### Task 1: Schema description fit for the prompt

**Files:**
- Modify: `src/schema.py`
- Modify: `tests/test_schema.py`

**Interfaces:**
- Produces: `get_schema(caminho: str) -> dict[str, list[dict]]`. Each column dict has `nome`, `tipo`, and at most one of: `valores: list[str]` (all distinct values, only when the column has ≤ 20 distinct non-null values and is not personal), `intervalo: [min, max]` (TEXT columns whose values match `YYYY-MM-DD`).
- Produces: `format_schema(schema: dict) -> str`, one block per table, one line per column, e.g. `- canal (TEXT): valores = App, Loja Física, Site` and `- data_compra (TEXT): datas de 2024-07-22 a 2025-07-22`. The key name `exemplos` is removed.
- Produces: constants `PERSONAL_COLUMNS = {("clientes", "nome"), ("clientes", "email")}`, `MAX_CATEGORIAS = 20`.

- [ ] **Step 1: Rewrite the tests.** Keep tests 1, 2, 5, 6 (tables, types, read-only, missing file). Replace tests 3 and 4 with:

```python
def test_categoricas_listam_todos_os_valores(schema):
    assert sorted(coluna(schema, "compras", "canal")["valores"]) == ["App", "Loja Física", "Site"]

def test_colunas_pessoais_nao_expoem_valores(schema):
    for nome in ("nome", "email"):
        c = coluna(schema, "clientes", nome)
        assert "valores" not in c and "intervalo" not in c

def test_datas_trazem_intervalo(schema):
    assert coluna(schema, "compras", "data_compra")["intervalo"] == ["2024-07-22", "2025-07-22"]

def test_format_schema_texto(schema):
    texto = format_schema(schema)
    assert "compras" in texto and "Loja Física" in texto and "2025-07-22" in texto
    assert "@example" not in texto and "sqlite_sequence" not in texto
```

- [ ] **Step 2:** Run `pytest tests/test_schema.py -v`. Expected: the 4 new tests FAIL (KeyError / ImportError on `format_schema`).
- [ ] **Step 3:** Implement. Count distinct values with `SELECT COUNT(DISTINCT col)`; date detection by checking that `MIN`/`MAX` match `^\d{4}-\d{2}-\d{2}`. INTEGER columns with ≤ 20 distinct values (e.g. `resolvido`, `interagiu`) also get `valores`, so the LLM sees booleans are `0/1`.
- [ ] **Step 4:** Run `pytest -v`. Expected: all PASS.
- [ ] **Step 5:** Commit `feat: describe categorical values and date ranges in schema`.

### Task 2: Safe read-only query execution

**Files:**
- Create: `src/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `class SQLError(Exception)` (message is shown to the LLM).
- Produces: `run_query(sql: str, caminho: str) -> pandas.DataFrame`. Opens read-only, installs `conn.set_authorizer` allowing only `SQLITE_SELECT`, `SQLITE_READ`, `SQLITE_FUNCTION` (deny everything else), rejects more than one statement, wraps any `sqlite3.Error` in `SQLError` with the original message.
- Produces: `to_llm_text(df: pandas.DataFrame, max_linhas: int = 200) -> str` — CSV-like text; when truncated, ends with `(... N linhas no total, mostrando 200)`.
- Produces: constant `DB_PATH = "data/anexo_desafio_1.db"`.

- [ ] **Step 1: Write failing tests** (skip if DB missing, same as test_schema):

```python
def test_select_devolve_dataframe():
    df = run_query("SELECT canal, COUNT(*) AS n FROM compras GROUP BY canal", DB_PATH)
    assert list(df.columns) == ["canal", "n"] and df["n"].sum() == 946

@pytest.mark.parametrize("sql", [
    "DELETE FROM clientes",
    "DROP TABLE clientes",
    "ATTACH DATABASE 'x.db' AS x",
    "SELECT 1; DELETE FROM clientes",
    "PRAGMA writable_schema = 1",
])
def test_bloqueia_escrita(sql):
    with pytest.raises(SQLError):
        run_query(sql, DB_PATH)
    assert run_query("SELECT COUNT(*) AS n FROM clientes", DB_PATH)["n"][0] == 100

def test_sql_invalido_vira_sqlerror_com_mensagem():
    with pytest.raises(SQLError, match="no such column"):
        run_query("SELECT coluna_inexistente FROM clientes", DB_PATH)

def test_to_llm_text_trunca():
    df = run_query("SELECT * FROM compras", DB_PATH)
    texto = to_llm_text(df)
    assert texto.count("\n") <= 202 and "946 linhas no total" in texto
```

- [ ] **Step 2:** Run `pytest tests/test_db.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement. Reuse the URI pattern of `src/schema.py`. Use `pandas.read_sql_query`. Multiple-statement check: `sqlite3.complete_statement` on the text after the first `;` being non-empty, or simpler: strip trailing `;` and reject if `;` remains outside quotes — pick one and keep the test green.
- [ ] **Step 4:** Run `pytest -v`. Expected: all PASS.
- [ ] **Step 5:** Commit `feat: add read-only guarded SQL execution`.

### Task 3: LLM factory and fake model for tests

**Files:**
- Create: `src/llm.py`, `.env.example`
- Create: `tests/fakes.py`
- Modify: `requirements.txt` (add pinned `langgraph`, `langchain-core`, `langchain-openai`, `python-dotenv`, `streamlit`, `ruff`; pin to the versions pip installs)
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces: `get_llm() -> BaseChatModel`. Loads `.env` with python-dotenv, reads `LLM_MODEL` (default `"gpt-5-mini"`), returns `langchain_openai.ChatOpenAI(model=...)`; raises `RuntimeError("Defina OPENAI_API_KEY no .env")` when the key is missing.
- Produces (tests only): `class FakeToolLLM(BaseChatModel)` built from a list of `AIMessage`s returned in order; `bind_tools(...)` returns self; records the messages it received in `self.recebidas: list[list[BaseMessage]]`.
- `.env.example` contains `OPENAI_API_KEY=` and `LLM_MODEL=gpt-5-mini`.

- [ ] **Step 1:** Failing tests: `get_llm()` raises `RuntimeError` when `OPENAI_API_KEY` is unset (use `monkeypatch.delenv`); `FakeToolLLM([AIMessage("a"), AIMessage("b")])` returns `"a"` then `"b"` on two `invoke` calls.
- [ ] **Step 2:** Run, expect FAIL.
- [ ] **Step 3:** Install deps, implement, pin versions.
- [ ] **Step 4:** Run `pytest -v`, expect all PASS.
- [ ] **Step 5:** Commit `feat: add LLM factory and fake chat model`.

### Task 4: The agent graph

**Files:**
- Create: `src/agent.py`, `src/prompts.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `get_schema`, `format_schema` (Task 1); `run_query`, `to_llm_text`, `SQLError`, `DB_PATH` (Task 2); `FakeToolLLM` (Task 3, tests only).
- Produces: `class Passo(TypedDict)`: `sql: str`, `linhas: int | None`, `erro: str | None`.
- Produces: `class Resultado(TypedDict)`: `texto: str`, `sql: str | None`, `dados: pandas.DataFrame | None`, `visualizacao: Literal["tabela", "barra", "linha", "numero", "texto"]`, `x: str | None`, `y: str | None`, `passos: list[Passo]`.
- Produces: `ask(pergunta: str, llm: BaseChatModel, caminho: str = DB_PATH, max_passos: int = 8) -> Resultado`.
- Produces: `build_system_prompt(caminho: str) -> str` in `src/prompts.py`.
- Tools given to the LLM (names fixed): `run_sql(sql: str)` → `to_llm_text(df)` or `"ERRO: <mensagem>"`; `final_answer(texto: str, sql: str | None, visualizacao: str, x: str | None, y: str | None)`.

Graph: `START → agent → (tool call run_sql → tools → agent) | (tool call final_answer → END) | (no tool call or passos ≥ max_passos → END)`. State keeps `messages` and `passos`. After END, `ask()` re-runs `final_answer.sql` with `run_query` to build `dados`; if that fails or there is no final_answer, `texto` is `"Não consegui concluir a análise."` + last error, `visualizacao="texto"`.

System prompt (Portuguese) must state: the schema text; the data covers `<min date> a <max date>` and relative periods are counted back from the max date; SQLite dialect (dates are `YYYY-MM-DD` text, use `strftime`); booleans are 0/1; investigate with several queries when needed; on `ERRO` fix the SQL and retry; always end with `final_answer`; pick `linha` for trends over time, `barra` for comparisons between categories, `tabela` for lists, `numero` for a single value; answer in Portuguese.

- [ ] **Step 1: Failing tests** with `FakeToolLLM`:

```python
def test_responde_com_uma_query(): ...
    # fake: run_sql("SELECT canal, COUNT(*) n FROM compras GROUP BY canal") then final_answer(..., visualizacao="barra", x="canal", y="n")
    # assert r["visualizacao"] == "barra", len(r["dados"]) == 3, len(r["passos"]) == 1, r["passos"][0]["erro"] is None

def test_corrige_sql_invalido(): ...
    # fake: run_sql("SELECT x FROM compras") → then run_sql(valid) → final_answer
    # assert r["passos"][0]["erro"] contains "no such column"; r["passos"][1]["erro"] is None
    # assert the 3rd call to the fake received a ToolMessage containing "ERRO"

def test_para_no_limite_de_passos(): ...
    # fake returns run_sql forever (10 messages); ask(..., max_passos=3)
    # assert len(r["passos"]) == 3 and r["visualizacao"] == "texto" and "Não consegui" in r["texto"]

def test_resposta_sem_ferramenta_vira_texto(): ...
    # fake: AIMessage("Não sei") with no tool calls → r["texto"] == "Não sei", r["dados"] is None

def test_prompt_traz_intervalo_e_regra_de_datas():
    p = build_system_prompt(DB_PATH)
    assert "2025-07-22" in p and "último ano" in p
```

- [ ] **Step 2:** Run `pytest tests/test_agent.py -v`, expect FAIL.
- [ ] **Step 3:** Implement with `langgraph.graph.StateGraph`; use a custom tools node (not `ToolNode`) so each `run_sql` call appends a `Passo`.
- [ ] **Step 4:** Run `pytest -v`, expect all PASS.
- [ ] **Step 5:** Commit `feat: add LangGraph SQL agent with self-correction`.

### Task 5: Visualization choice

**Files:**
- Create: `src/viz.py`
- Test: `tests/test_viz.py`

**Interfaces:**
- Consumes: `Resultado` (Task 4).
- Produces: `escolher_visualizacao(df: pandas.DataFrame | None, pedido: str, x: str | None, y: str | None) -> dict` returning `{"tipo": "tabela"|"barra"|"linha"|"numero"|"texto", "x": str|None, "y": str|None}`. Rules: `df is None` → `texto`; 1×1 → `numero`; `barra`/`linha` kept only if `x` and `y` are columns of `df` and `y` is numeric, else `tabela`.

- [ ] **Step 1: Failing tests:** valid bar kept; `x` not in columns → `tabela`; non-numeric `y` → `tabela`; 1×1 df → `numero`; `None` → `texto`.
- [ ] **Step 2–4:** fail, implement, pass.
- [ ] **Step 5:** Commit `feat: validate chart choice against result data`.

### Task 6: Streamlit interface

**Files:**
- Create: `app.py`
- Test: `tests/test_app.py` (uses `streamlit.testing.v1.AppTest` with `ask` monkeypatched to return a fixed `Resultado`)

**Interfaces:**
- Consumes: `ask` (Task 4), `escolher_visualizacao` (Task 5), `get_llm` (Task 3).
- Page: title, `st.chat_input` for the question, chat history in `st.session_state["historico"]`; for each answer: the text, then `st.metric` / `st.bar_chart` / `st.line_chart` / `st.dataframe` by `tipo`, then `st.expander("Como cheguei aqui")` listing each `Passo` (`st.code(sql, language="sql")` + row count or error). Sidebar: 5 example questions from the PDF as buttons. Missing API key → `st.error` with setup instructions instead of a crash.

- [ ] **Step 1:** Failing test: AppTest runs `app.py`, submits a question through the chat input, asserts `at.exception` is empty, the fixed answer text appears in `at.markdown`, and an expander labeled `Como cheguei aqui` exists.
- [ ] **Step 2–4:** fail, implement, pass. Also run `streamlit run app.py` and ask one real question by hand.
- [ ] **Step 5:** Commit `feat: add Streamlit chat interface`.

### Task 7: Real-question check, README, CI

**Files:**
- Create: `scripts/run_examples.py`, `docs/examples.md` (generated output)
- Modify: `README.md`
- Create: `.github/workflows/ci.yml`, `pyproject.toml` (add `[tool.ruff]`)

**Interfaces:**
- Consumes: `ask`, `get_llm`.
- `scripts/run_examples.py` runs the 5 PDF questions against the real LLM and writes `docs/examples.md` with, per question: final text, visualization type, every SQL step, row counts. For each, a hand-written reference SQL in the script is executed and its result shown next to the agent's, so a reader can check correctness.

- [ ] **Step 1:** Run `python scripts/run_examples.py` (needs a real key). Read the 5 outputs against the reference SQL; record any wrong answer honestly in README instead of hiding it.
- [ ] **Step 2:** README (English): what it does, setup (`python3.11 -m venv`, `pip install -r requirements.txt`, copy `.env.example`, place `anexo_desafio_1.db` in `data/`), `streamlit run app.py`, `pytest`, architecture diagram of the graph in text, design decisions (read-only + authorizer, re-executing final SQL, date-range rule, PII kept out of the prompt), tested examples linking `docs/examples.md`, improvements.
- [ ] **Step 3:** CI workflow on push/PR: Python 3.11, `pip install -r requirements.txt`, `ruff check .`, `pytest` (DB-dependent tests skip), `gitleaks` action over full history.
- [ ] **Step 4:** Run `ruff check . && pytest -v` locally, expect clean.
- [ ] **Step 5:** Commit `docs: add README, example runs and CI`. `/security-review` and gitleaks before the first push; push and make the repo public only with Lucca's explicit ok.
