"""Run the 5 challenge questions against the real agent and compare with reference SQL.

Usage:
    python scripts/run_examples.py                    # needs OPENAI_API_KEY; writes docs/examples.md
    python scripts/run_examples.py --repeat           # each question 3 times (or --repeat N)
    python scripts/run_examples.py --reference-only   # no key needed; prints reference results only

Each run is checked against the reference result (src/evaluation.py): the columns in
"check" must hold the same values, whatever the agent named its columns.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from src.db import DB_PATH, run_query
from src.evaluation import mesmos_dados

# Reference SQL, written by hand. The data covers 2024-07-22..2025-07-22, so "maio" is
# May 2025 and "no ultimo ano" is the 12 months ending at the last date in the data.
# "check": reference columns compared with the agent's data. "minimo": for top-N with
# ties, the reference lists every tied row and the agent needs at least that many rows.
EXAMPLES = [
    {
        "question": "Liste os 5 estados com maior número de clientes que compraram via app em maio.",
        # Every state tied at the 5th place cut (Paraná, Espírito Santo, Alagoas at 2).
        "reference_sql": """
WITH por_estado AS (
  SELECT c.estado, COUNT(DISTINCT c.id) AS clientes
  FROM compras p JOIN clientes c ON c.id = p.cliente_id
  WHERE p.canal = 'App' AND strftime('%m', p.data_compra) = '05'
  GROUP BY c.estado
)
SELECT estado, clientes FROM por_estado
WHERE clientes >= (SELECT clientes FROM por_estado ORDER BY clientes DESC LIMIT 1 OFFSET 4)
ORDER BY clientes DESC, estado""",
        "check": ["estado", "clientes"],
        "minimo": 5,
    },
    {
        "question": "Quantos clientes interagiram com campanhas de WhatsApp em 2024?",
        "reference_sql": """
SELECT COUNT(DISTINCT cliente_id) AS clientes
FROM campanhas_marketing
WHERE canal = 'WhatsApp' AND interagiu = 1 AND strftime('%Y', data_envio) = '2024'""",
        "check": ["clientes"],
    },
    {
        "question": "Quais categorias de produto tiveram o maior número de compras em média por cliente?",
        "reference_sql": """
SELECT categoria,
       COUNT(*) AS compras,
       COUNT(DISTINCT cliente_id) AS clientes,
       ROUND(1.0 * COUNT(*) / COUNT(DISTINCT cliente_id), 3) AS compras_por_cliente
FROM compras
GROUP BY categoria
ORDER BY compras_por_cliente DESC""",
        "check": ["categoria", "compras_por_cliente"],
    },
    {
        "question": "Qual o número de reclamações não resolvidas por canal?",
        "reference_sql": """
SELECT canal, COUNT(*) AS reclamacoes_nao_resolvidas
FROM suporte
WHERE tipo_contato = 'Reclamação' AND resolvido = 0
GROUP BY canal
ORDER BY reclamacoes_nao_resolvidas DESC""",
        "check": ["canal", "reclamacoes_nao_resolvidas"],
    },
    {
        "question": "Qual a tendência de reclamações por canal no último ano?",
        "reference_sql": """
SELECT strftime('%Y-%m', data_contato) AS mes, canal, COUNT(*) AS reclamacoes
FROM suporte
WHERE tipo_contato = 'Reclamação'
  AND data_contato >= date('2025-07-22', '-1 year') AND data_contato <= '2025-07-22'
GROUP BY mes, canal
ORDER BY mes, canal""",
        "check": ["mes", "canal", "reclamacoes"],
    },
]


def reference_result(example):
    return run_query(example["reference_sql"], DB_PATH)


def matches_reference(dados, ref, example) -> bool:
    return mesmos_dados(dados, ref, example["check"], example.get("minimo"))


def print_references():
    for i, ex in enumerate(EXAMPLES, 1):
        print(f"\n## {i}. {ex['question']}")
        print(ex["reference_sql"].strip())
        print(reference_result(ex).to_string(index=False))


def run_agent_examples(repeat: int = 1):
    from src.agent import ask
    from src.llm import get_llm

    llm = get_llm()
    resumo, corpo = [], []
    for i, ex in enumerate(EXAMPLES, 1):
        ref = reference_result(ex)
        runs = []
        for r in range(1, repeat + 1):
            print(f"[{i}/{len(EXAMPLES)}] run {r}/{repeat}: {ex['question']}", flush=True)
            res = ask(ex["question"], llm)
            runs.append((res, matches_reference(res["dados"], ref, ex)))
        acertos = sum(ok for _, ok in runs)
        resumo.append(f"| {i} | {ex['question']} | {acertos}/{repeat} |")
        print(f"    matched the reference in {acertos}/{repeat} runs", flush=True)

        res = runs[0][0]  # details of the first run
        corpo += [f"## {i}. {ex['question']}", ""]
        corpo += ["Matched the reference data: "
                  + ", ".join(f"run {n}: {'yes' if ok else 'no'}"
                              for n, (_, ok) in enumerate(runs, 1)), ""]
        corpo += ["**Agent answer (run 1)**", "", res["texto"], ""]
        corpo += [f"Visualization requested: `{res['visualizacao']}`", ""]
        corpo += ["**Agent steps**", ""]
        for n, p in enumerate(res["passos"], 1):
            status = f"error: {p['erro']}" if p["erro"] else f"{p['linhas']} rows"
            corpo += [f"{n}. ({status})", "", "```sql", p["sql"], "```", ""]
        corpo += ["**Agent final SQL**", "", "```sql", res["sql"] or "-- none", "```", ""]
        if res["dados"] is not None:
            corpo += [f"Agent data ({len(res['dados'])} rows):", "", "```",
                      res["dados"].head(30).to_string(index=False), "```", ""]
        corpo += ["**Reference SQL**", "", "```sql", ex["reference_sql"].strip(), "```", ""]
        corpo += [f"Reference result ({len(ref)} rows):", "", "```",
                  ref.head(30).to_string(index=False), "```", ""]
        if len(runs) > 1:
            corpo += ["**Answer text of the other runs**", ""]
            for n, (outro, _) in enumerate(runs[1:], 2):
                corpo += [f"Run {n}:", "", outro["texto"], ""]

    cmd = "python scripts/run_examples.py" + (f" --repeat {repeat}" if repeat > 1 else "")
    out = ["# Example runs", "", f"Generated by `{cmd}`.", "",
           "| # | Question | Runs matching the reference data |", "| --- | --- | --- |",
           *resumo, ""]
    path = ROOT / "docs" / "examples.md"
    path.write_text("\n".join(out + corpo), encoding="utf-8")
    print(f"Wrote {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-only", action="store_true",
                        help="print the reference SQL results without calling the LLM")
    parser.add_argument("--repeat", type=int, nargs="?", const=3, default=1, metavar="N",
                        help="run each question N times (3 if N is omitted) and report "
                             "how many runs matched the reference data")
    args = parser.parse_args()
    if args.reference_only:
        print_references()
        return
    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in, "
                 "or use --reference-only to print only the reference results.")
    if args.repeat < 1:
        sys.exit("--repeat must be at least 1")
    run_agent_examples(args.repeat)


if __name__ == "__main__":
    main()
