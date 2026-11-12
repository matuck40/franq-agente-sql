# Franq SQL Agent

A "virtual data analyst": ask a business question in Portuguese, and an LLM agent
explores a SQLite database with SQL, answers in text and shows the data as a table,
bar chart, line chart or single number. Built for the Franq hiring challenge
(Desafio Técnico 1) with LangGraph, OpenAI and Streamlit.

The database (`anexo_desafio_1.db`, from the challenge) has four tables: `clientes`,
`compras`, `suporte` and `campanhas_marketing`. Its data spans 2024-07-22 to 2025-07-22.

## How to run

Requirements: Python 3.11, an OpenAI API key, and the challenge database file.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then set OPENAI_API_KEY in .env
# optional: LLM_MODEL in .env (default: gpt-5-mini)

# put the challenge database at data/anexo_desafio_1.db (it is not in git)

streamlit run app.py          # chat UI; the sidebar has the 5 example questions
pytest                        # tests; the ones needing the database skip if it is missing
ruff check .                  # lint
```

## Agent flow and architecture

```
START --> agent <---> tools
            |
            +--> END
```

- `agent`: the LLM (with two tools bound) reads the conversation and either calls
  `run_sql`, or calls `final_answer`.
- `tools`: runs the `run_sql` query against the database and sends the result (or the
  error message) back to the agent, which can then correct its SQL.
- The graph ends when the agent calls `final_answer` (text, final SQL, chart type and
  x/y columns), or when the turn limit is reached.

Code layout:

| File | Role |
| --- | --- |
| `src/schema.py` | Reads the schema, value lists for low-cardinality columns and date ranges |
| `src/prompts.py` | Builds the system prompt (in Portuguese) from the schema |
| `src/db.py` | Safe query execution (`run_query`) and CSV formatting for the LLM |
| `src/agent.py` | The LangGraph agent and `ask()` |
| `src/viz.py` | Validates the LLM's chart choice against the real data |
| `src/llm.py` | OpenAI model factory (`OPENAI_API_KEY`, `LLM_MODEL`) |
| `app.py` | Streamlit chat interface |
| `scripts/run_examples.py` | Runs the 5 example questions and compares with reference SQL |

## Design decisions

- **Read-only database access.** Queries run on a connection opened with the SQLite URI
  `mode=ro`, with an authorizer that only allows `SELECT`, reads and functions, and a
  check that only a single statement is sent. The LLM cannot change the data.
- **Final data comes from code, not from the LLM.** The agent returns the final SQL;
  the code re-executes it and shows that result. The numbers on screen are never copied
  from text the LLM wrote.
- **Relative periods use the data, not today's date.** The prompt tells the model the
  data's last date and that "last year" or "last 3 months" count backwards from it
  (for example `date('2025-07-22', '-1 year')`).
- **Personal data stays out of the prompt.** The schema given to the LLM lists only
  column names, types, categories and date ranges. The columns `clientes.nome` and
  `clientes.email` are never sampled. Note that query results (up to 200 rows, as CSV)
  are sent back to the LLM so it can reason about them, so the LLM could still see
  those columns if it selected them in a query.
- **Bounded loops with a polite fallback.** The agent is limited to 8 turns and the
  graph has a recursion limit as a safety net. If it cannot finish, the user gets
  "Não consegui concluir a análise." plus the last SQL error, if any.
- **Chart choice is validated.** The LLM may request a bar or line chart, but
  `src/viz.py` checks it against the data (x and y exist and differ, y is numeric,
  more than one row) and falls back to a table otherwise. A 1x1 result is shown as a
  number.

## Tested examples

The 5 questions below are the example questions from the challenge (they are also in
the app's sidebar). Each has a hand-written reference SQL in
`scripts/run_examples.py`. The results below were computed by running those reference
queries with `python scripts/run_examples.py --reference-only`. They are what the agent
should answer; they are **not** the agent's own outputs.

Interpretation choices: "em maio" means May 2025 (the only May in the data), "no último
ano" means 2025-07-22 minus one year up to 2025-07-22, "reclamações" means
`suporte.tipo_contato = 'Reclamação'`, and boolean columns are 0/1.

1. **Liste os 5 estados com maior número de clientes que compraram via app em maio.**
   Distinct customers per state with an `App` purchase in May:
   São Paulo 6, Minas Gerais 3, Santa Catarina 3, then a three-way tie at 2 (Paraná,
   Espírito Santo, Alagoas). The reference query breaks ties by state name, so it shows
   Alagoas and Espírito Santo; any of the three tied states is a valid 5th place.
2. **Quantos clientes interagiram com campanhas de WhatsApp em 2024?**
   17 distinct customers (`interagiu = 1`, channel WhatsApp, `data_envio` in 2024).
3. **Quais categorias de produto tiveram o maior número de compras em média por cliente?**
   Purchases divided by distinct buyers per category: Roupas 2.211, Viagens 2.162,
   Livros 1.976, Serviços 1.962, Eletrônicos 1.923, Alimentos 1.882.
4. **Qual o número de reclamações não resolvidas por canal?**
   Telefone 19, Chat 18, E-mail 14.
5. **Qual a tendência de reclamações por canal no último ano?**
   Monthly complaints per channel, 2024-07 to 2025-07 (38 rows, in the script output).
   For example, Telefone peaks at 6 in 2024-10 and Chat at 6 in 2025-02. 2024-07 and
   2025-07 are partial months.

The agent's own answers to these questions have not been recorded in this repository
yet. Running `python scripts/run_examples.py` (needs `OPENAI_API_KEY`) runs the agent on
the 5 questions and writes `docs/examples.md` with, for each: the final text, the
requested visualization, every SQL step with its row count, the final SQL and data,
and the reference SQL and result side by side for checking.

## Possible improvements

- **Evaluation set.** Grow the 5 reference queries into a larger set and score the
  agent's final data against them automatically (for example in CI, with a small model).
- **Cache the schema.** The schema is read from the database on every question; compute
  it once per process.
- **Stream the steps in the UI.** Show each SQL query as the agent runs it, instead of
  a spinner followed by an expander.
- **Few-shot examples.** Add a few question/SQL pairs to the prompt for tricky cases
  (relative dates, ties, "average per customer").
- **Cost and latency tracking.** Record tokens, number of turns and time per question.
- **Handle ties and ambiguity.** Ask the user a clarifying question (for example the
  tie at 5th place above) instead of choosing silently.
- **Stricter privacy.** Mask `nome` and `email` in the results sent back to the LLM, not
  only in the schema.
