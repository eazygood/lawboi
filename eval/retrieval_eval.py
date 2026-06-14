#!/usr/bin/env python3
"""
Retrieval-level evaluation.

Measures precision@k, recall@k, nDCG@k, hit@k, and MRR against a gold set
by calling RetrievalEngine.retrieve() directly — no LLM involved.

Usage:
    .venv/bin/python eval/retrieval_eval.py            # default k=5
    .venv/bin/python eval/retrieval_eval.py --k 10
    .venv/bin/python eval/retrieval_eval.py --json      # machine-readable output
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lawboi.config.settings import Settings
from lawboi.config.composition import build_container

GOLD_SET_PATH = Path(__file__).parent / "retrieval_gold_set.json"


def _match(result: dict, expected: dict) -> bool:
    meta = result.get("metadata", {})
    eli = meta.get("eli", "")
    section = str(result.get("section_num", meta.get("section_num", "")))
    return eli == expected["eli"] and section == expected["section"]


def precision_at_k(results: list[dict], expected: list[dict], k: int) -> float:
    top_k = results[:k]
    if not top_k:
        return 1.0 if not expected else 0.0
    hits = sum(1 for r in top_k if any(_match(r, e) for e in expected))
    return hits / len(top_k)


def recall_at_k(results: list[dict], expected: list[dict], k: int) -> float:
    if not expected:
        return 1.0
    top_k = results[:k]
    found = sum(1 for e in expected if any(_match(r, e) for r in top_k))
    return found / len(expected)


def hit_at_k(results: list[dict], expected: list[dict], k: int) -> float:
    if not expected:
        return 1.0
    top_k = results[:k]
    return 1.0 if any(_match(r, e) for r in top_k for e in expected) else 0.0


def reciprocal_rank(results: list[dict], expected: list[dict]) -> float:
    for i, r in enumerate(results):
        if any(_match(r, e) for e in expected):
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(results: list[dict], expected: list[dict], k: int) -> float:
    if not expected:
        return 1.0
    top_k = results[:k]
    dcg = sum(
        1.0 / math.log2(i + 2)
        for i, r in enumerate(top_k)
        if any(_match(r, e) for e in expected)
    )
    ideal_hits = min(len(expected), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


def run_retrieval_eval(k: int, as_json: bool) -> None:
    gold = json.loads(GOLD_SET_PATH.read_text())
    cases_with_expected = [c for c in gold if c["expected_provisions"]]
    all_cases = gold

    if not as_json:
        print(f"Retrieval eval: {len(all_cases)} cases, k={k}\n")

    engine = build_container(Settings()).retrieval

    per_case = []
    for case in all_cases:
        expected = case["expected_provisions"]
        results = engine.retrieve(case["query"], limit=max(k, 20))

        metrics = {
            "id": case["id"],
            "category": case["category"],
            "query": case["query"],
            "precision_at_k": precision_at_k(results, expected, k),
            "recall_at_k": recall_at_k(results, expected, k),
            "ndcg_at_k": ndcg_at_k(results, expected, k),
            "hit_at_k": hit_at_k(results, expected, k),
            "mrr": reciprocal_rank(results, expected),
            "num_results": len(results),
        }
        per_case.append(metrics)

        if not as_json:
            print(
                f"  [{case['id']}] P@{k}={metrics['precision_at_k']:.2f}  "
                f"R@{k}={metrics['recall_at_k']:.2f}  "
                f"nDCG@{k}={metrics['ndcg_at_k']:.2f}  "
                f"Hit@{k}={metrics['hit_at_k']:.0f}  "
                f"MRR={metrics['mrr']:.2f}  "
                f"  {case['query'][:50]}"
            )

    n = len(per_case)
    n_with_expected = len(cases_with_expected)
    case_ids_with_expected = {c["id"] for c in cases_with_expected}
    cases_scored = [c for c in per_case if c["id"] in case_ids_with_expected]

    summary = {
        "k": k,
        "total_cases": n,
        "scored_cases": n_with_expected,
        "avg_precision_at_k": sum(c["precision_at_k"] for c in cases_scored) / n_with_expected,
        "avg_recall_at_k": sum(c["recall_at_k"] for c in cases_scored) / n_with_expected,
        "avg_ndcg_at_k": sum(c["ndcg_at_k"] for c in cases_scored) / n_with_expected,
        "hit_rate_at_k": sum(c["hit_at_k"] for c in cases_scored) / n_with_expected,
        "mrr": sum(c["mrr"] for c in cases_scored) / n_with_expected,
    }

    if as_json:
        print(json.dumps({"summary": summary, "cases": per_case}, indent=2))
    else:
        print(f"\n{'=' * 40}")
        print(f"  RETRIEVAL METRICS  (k={k}, {n_with_expected} scored cases)")
        print(f"{'=' * 40}")
        print(f"  Precision@{k}:  {summary['avg_precision_at_k']:.0%}")
        print(f"  Recall@{k}:     {summary['avg_recall_at_k']:.0%}")
        print(f"  nDCG@{k}:       {summary['avg_ndcg_at_k']:.0%}")
        print(f"  Hit@{k}:        {summary['hit_rate_at_k']:.0%}")
        print(f"  MRR:           {summary['mrr']:.2f}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrieval-level IR evaluation")
    parser.add_argument("--k", type=int, default=5, help="Cutoff for @k metrics")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    args = parser.parse_args()
    run_retrieval_eval(args.k, args.json)
