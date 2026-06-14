#!/usr/bin/env python3
"""Evaluation runner. Usage: python eval/run_eval.py --api http://localhost:8000

Add --faithfulness to run an LLM judge that scores whether each answer's claims
are grounded in the retrieved provisions (RAGAS-style). Requires an LLM API key
in this process's environment (GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY).
"""
import argparse
import json
import re
import sys
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GOLD_SET_PATH = Path(__file__).parent / "gold_set.json"
REFUSE_PHRASES = [
    "cannot answer", "not enough information", "i don't know",
    "no information", "outside my", "cannot provide",
    "ei suuda vastata", "ei leia", "piisavalt teavet",
]

# /answer grounds on the top-5 retrieved provisions (engine default limit=5).
# Fetch a superset via /search so the judge sees at least what the answer saw.
# Caveat: a superset means a claim can occasionally score "supported" by a
# provision the answer-LLM didn't actually see, slightly inflating faithfulness.
FAITHFULNESS_CONTEXT_LIMIT = 8

FAITHFULNESS_PROMPT = """\
You are a strict faithfulness evaluator for a legal-information assistant.
You are given SOURCE PROVISIONS (the only evidence the assistant was allowed to
use) and an ANSWER. Break the answer into its distinct factual or legal claims,
then decide for each whether it is directly supported by the source provisions.

Rules:
- Ignore the disclaimer and generic boilerplate (e.g. "consult a lawyer",
  "this is legal information not legal advice").
- A claim is supported only if the provisions state or directly entail it.
  Do not use outside knowledge.
- Statements that the provisions lack the information (refusals/hedges) are not
  claims — do not count them.

Return ONLY a JSON object, no markdown, in this exact shape:
{{"claims": [{{"claim": "<text>", "supported": true|false}}]}}

SOURCE PROVISIONS:
{context}

ANSWER:
{answer}"""


def call_answer(api_url: str, query: str) -> dict:
    resp = requests.post(f"{api_url}/answer", json={"query": query}, timeout=30)
    if resp.status_code == 422:
        return {"answer": "No relevant provisions found.", "citations": [], "model_used": "n/a",
                "language_detected": "en", "translation_warning": False, "disclaimer": ""}
    resp.raise_for_status()
    return resp.json()


def is_refusal(answer: str) -> bool:
    lower = answer.lower()
    return any(phrase in lower for phrase in REFUSE_PHRASES)


def fetch_context(api_url: str, query: str) -> list[dict]:
    resp = requests.post(
        f"{api_url}/search",
        json={"query": query, "limit": FAITHFULNESS_CONTEXT_LIMIT},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _format_context(provisions: list[dict]) -> str:
    parts = []
    for p in provisions:
        section = p.get("section_num", "")
        act_title = p.get("act_title", "")
        eli = p.get("eli", "")
        text = p.get("text_et", "")
        parts.append(f"[§ {section} | {act_title} | {eli}]\n{text}")
    return "\n\n---\n\n".join(parts)


def _parse_judge_json(raw: str) -> dict:
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(stripped)


def faithfulness_score(llm, answer: str, provisions: list[dict]) -> tuple[float, list[str]]:
    """Returns (score, unsupported_claims). Score is supported/total claims;
    1.0 when the answer makes no verifiable claims (nothing to contradict)."""
    if not provisions:
        return 0.0, ["no source provisions retrieved"]
    prompt = FAITHFULNESS_PROMPT.format(
        context=_format_context(provisions), answer=answer
    )
    raw = str(llm.complete(prompt))
    try:
        claims = _parse_judge_json(raw).get("claims", [])
    except (json.JSONDecodeError, ValueError):
        return 0.0, [f"judge returned unparseable output: {raw[:120]}"]
    if not claims:
        return 1.0, []
    unsupported = [c.get("claim", "") for c in claims if not c.get("supported")]
    score = (len(claims) - len(unsupported)) / len(claims)
    return score, unsupported


def citation_precision(returned: list[dict], expected: list[dict]) -> float:
    if not returned:
        return 1.0 if not expected else 0.0
    expected_set = {(e["eli"], e["section"]) for e in expected}
    correct = sum(
        1 for c in returned
        if (c.get("eli", ""), c.get("section", "").lstrip("§ ").strip()) in
           {(e, s) for e, s in expected_set}
    )
    return correct / len(returned)


def citation_recall(returned: list[dict], expected: list[dict]) -> float:
    if not expected:
        return 1.0
    expected_set = {(e["eli"], e["section"]) for e in expected}
    found = sum(
        1 for exp_eli, exp_sec in expected_set
        if any(
            c.get("eli", "") == exp_eli and exp_sec in c.get("section", "")
            for c in returned
        )
    )
    return found / len(expected_set)


def run_eval(api_url: str, check_faithfulness: bool = False, judge_model=None) -> None:
    gold = json.loads(GOLD_SET_PATH.read_text())
    results = []
    print(f"Running eval against {api_url} with {len(gold)} cases...\n")

    llm = None
    if check_faithfulness:
        from lawboi.adapters.llm.factory import build_llm

        llm = build_llm(judge_model)

    for case in gold:
        print(f"  [{case['id']}] {case['query'][:60]}...")
        response = call_answer(api_url, case["query"])
        answer = response.get("answer", "")
        citations = response.get("citations", [])
        refused = is_refusal(answer)

        precision = citation_precision(citations, case["expected_citations"])
        recall = citation_recall(citations, case["expected_citations"])
        contains_ok = all(
            phrase.lower() in answer.lower()
            for phrase in case["expected_answer_contains"]
        )
        refusal_ok = refused == case["should_refuse"]

        record = {
            "id": case["id"],
            "category": case["category"],
            "precision": precision,
            "recall": recall,
            "contains_ok": contains_ok,
            "refusal_ok": refusal_ok,
            "faithfulness": None,
        }

        # Faithfulness only applies to substantive answers; a refusal makes no
        # claims to verify against the sources.
        if check_faithfulness and not refused:
            context = fetch_context(api_url, case["query"])
            score, unsupported = faithfulness_score(llm, answer, context)
            record["faithfulness"] = score
            record["unsupported"] = unsupported

        results.append(record)

    total = len(results)
    avg_precision = sum(r["precision"] for r in results) / total
    avg_recall = sum(r["recall"] for r in results) / total
    refusal_rate = sum(1 for r in results if r["refusal_ok"]) / total
    contains_rate = sum(1 for r in results if r["contains_ok"]) / total

    print("\n=== EVAL RESULTS ===")
    print(f"  Cases:             {total}")
    print(f"  Citation precision: {avg_precision:.0%}  (target ≥85%)")
    print(f"  Citation recall:    {avg_recall:.0%}  (target ≥75%)")
    print(f"  Refusal accuracy:   {refusal_rate:.0%}  (target 100%)")
    print(f"  Contains check:     {contains_rate:.0%}")
    if check_faithfulness:
        scored = [r for r in results if r["faithfulness"] is not None]
        if scored:
            avg_faith = sum(r["faithfulness"] for r in scored) / len(scored)
            print(f"  Faithfulness:       {avg_faith:.0%}  "
                  f"({len(scored)} answered cases, target ≥90%)")
    print()
    failing = [r for r in results if not r["refusal_ok"] or r["precision"] < 0.8]
    if failing:
        print("Failing cases:")
        for r in failing:
            print(f"  {r['id']} ({r['category']}): precision={r['precision']:.0%} "
                  f"recall={r['recall']:.0%} refusal_ok={r['refusal_ok']}")

    if check_faithfulness:
        unfaithful = [
            r for r in results
            if r["faithfulness"] is not None and r["faithfulness"] < 0.9
        ]
        if unfaithful:
            print("\nUnfaithful answers (claims not grounded in sources):")
            for r in unfaithful:
                print(f"  {r['id']} ({r['category']}): faithfulness={r['faithfulness']:.0%}")
                for claim in r.get("unsupported", []):
                    print(f"      - {claim}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument(
        "--faithfulness", action="store_true",
        help="Run an LLM judge scoring whether answers are grounded in sources",
    )
    parser.add_argument(
        "--judge-model", default=None,
        help="Model for the faithfulness judge (defaults to pipeline auto-select)",
    )
    args = parser.parse_args()
    run_eval(args.api, check_faithfulness=args.faithfulness, judge_model=args.judge_model)
