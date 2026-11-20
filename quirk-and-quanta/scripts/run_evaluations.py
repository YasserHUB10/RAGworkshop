#!/usr/bin/env python3
"""
Quirk & Quanta - Multi-Strategy RAG Benchmark & Evaluation Runner
Executes the golden evaluation dataset (22 curated test cases across 8 families)
against Vector, BM25, and Hybrid RRF pipelines and measures empirical metrics:
- Hit Rate @ k
- Precision @ k
- Recall @ k
- Mean Reciprocal Rank (MRR)
- RBAC Security Compliance
- Latency Telemetry (p50, p95, avg)
"""

import os
import sys
import json
import time
from typing import Dict, Any

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from rag.pipeline import RAGPipeline

EVAL_DIR = os.path.join(ROOT_DIR, "data", "evaluation")

def run_evaluation(strategy: str = "semantic", method: str = "vector", top_k: int = 5) -> Dict[str, Any]:
    print("=" * 70)
    print(f"RUNNING RAG BENCHMARK (Strategy: {strategy}, Method: {method.upper()}, Top-K: {top_k})")
    print("=" * 70)

    golden_file = os.path.join(EVAL_DIR, "golden_dataset.json")
    if not os.path.exists(golden_file):
        print(f"[FAIL] Missing golden dataset at {golden_file}")
        sys.exit(1)

    with open(golden_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    pipeline = RAGPipeline(default_strategy=strategy)

    results = []
    hits = 0
    reciprocal_ranks = []
    all_precisions = []
    all_recalls = []
    latencies = []
    rbac_pass = 0
    rbac_total = 0

    print(f"{'ID':<10} {'Family':<24} {'Role':<10} {'Hit?':<6} {'Score':<8} {'Time (ms)':<10}")
    print("-" * 70)

    for item in cases:
        qid = item["id"]
        family = item["family"]
        q_text = item["question"]
        expected_sources = item.get("relevantSourceIds", [])
        expected_docs = item.get("relevantDocIds", [])
        
        # Test role based on query type
        role = "admin" if "admin" in family or "authorized_admin" in family else "customer"

        t_start = time.perf_counter()
        res = pipeline.ask(
            question=q_text,
            top_k=top_k,
            strategy=strategy,
            method=method,
            role=role,
            retrieval_only=True
        )
        t_elapsed = round((time.perf_counter() - t_start) * 1000, 2)
        latencies.append(t_elapsed)

        retrieved_sources = [e["sourceId"] for e in res["evidence"]]
        retrieved_docs = [e["docId"] for e in res["evidence"]]
        top_score = res["evidence"][0]["score"] if res["evidence"] else 0.0

        # Evaluation logic
        is_hit = False
        rr = 0.0
        p_at_k = 0.0
        r_at_k = 0.0

        if family in ["out_of_domain", "prompt_injection"]:
            # Correct behavior: either 0 matches, or very low score
            # In BM25, out_of_domain queries often return 0 matches (ideal precision!)
            is_hit = (len(res["evidence"]) == 0) or (top_score < 0.20 and method == "vector") or (top_score < 2.0 and method == "bm25")
            rr = 1.0 if is_hit else 0.0
            p_at_k = 1.0 if is_hit else 0.0
            r_at_k = 1.0 if is_hit else 0.0
        elif family == "role_restricted_customer":
            # Correct behavior: customer must NOT see any internal documents
            has_leak = any(e.get("accessLevel") != "public" for e in res["evidence"])
            is_hit = not has_leak
            rr = 1.0 if not has_leak else 0.0
            p_at_k = 1.0 if not has_leak else 0.0
            r_at_k = 1.0 if not has_leak else 0.0
            rbac_total += 1
            if not has_leak:
                rbac_pass += 1
        else:
            overlap_sources = set(retrieved_sources).intersection(set(expected_sources))
            overlap_docs = set(retrieved_docs).intersection(set(expected_docs))
            has_relevant = bool(overlap_sources or overlap_docs)
            is_hit = has_relevant

            if is_hit:
                for rank_idx, e in enumerate(res["evidence"], 1):
                    if e["sourceId"] in expected_sources or e["docId"] in expected_docs:
                        rr = 1.0 / rank_idx
                        break

            relevant_retrieved = len(overlap_sources or overlap_docs)
            p_at_k = round(relevant_retrieved / max(len(res["evidence"]), 1), 3)
            r_at_k = round(relevant_retrieved / max(len(expected_sources or expected_docs), 1), 3)

            if "admin" in family:
                rbac_total += 1
                if any(e.get("accessLevel") != "public" for e in res["evidence"]):
                    rbac_pass += 1

        if is_hit:
            hits += 1
        reciprocal_ranks.append(rr)
        all_precisions.append(p_at_k)
        all_recalls.append(r_at_k)

        status_str = "HIT" if is_hit else "MISS"
        print(f"{qid:<10} {family[:22]:<24} {role:<10} {status_str:<6} {top_score:<8.4f} {t_elapsed:<10.1f}")

        results.append({
            "id": qid,
            "family": family,
            "question": q_text,
            "role": role,
            "hit": is_hit,
            "reciprocalRank": rr,
            "precisionAtK": p_at_k,
            "recallAtK": r_at_k,
            "topScore": top_score,
            "retrievedDocs": retrieved_docs[:3],
            "latencyMs": t_elapsed
        })

    # Summary Metrics
    total_q = len(cases)
    hit_rate = round(hits / total_q, 4)
    mrr = round(sum(reciprocal_ranks) / total_q, 4)
    mean_precision = round(sum(all_precisions) / total_q, 4)
    mean_recall = round(sum(all_recalls) / total_q, 4)
    latencies.sort()
    p50_latency = latencies[int(len(latencies) * 0.50)]
    p95_latency = latencies[int(len(latencies) * 0.95)]
    avg_latency = round(sum(latencies) / len(latencies), 2)

    print("-" * 70)
    print("EMPIRICAL BENCHMARK SUMMARY:")
    print(f"  - Total Test Questions:    {total_q}")
    print(f"  - Hit Rate @ {top_k}:            {hit_rate * 100:.1f}% ({hits}/{total_q})")
    print(f"  - Mean Reciprocal Rank:    {mrr:.4f}")
    print(f"  - Mean Precision @ {top_k}:      {mean_precision:.4f}")
    print(f"  - Mean Recall @ {top_k}:         {mean_recall:.4f}")
    print(f"  - RBAC Compliance:         {rbac_pass}/{rbac_total} ({100 if rbac_total==rbac_pass else 0}%)" if rbac_total > 0 else "")
    print(f"  - Latency: p50={p50_latency:.1f}ms | p95={p95_latency:.1f}ms | avg={avg_latency:.1f}ms")
    print("=" * 70)

    eval_output = {
        "benchmarkDate": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "strategy": strategy,
        "method": method,
        "topK": top_k,
        "metrics": {
            "totalQuestions": total_q,
            "hitRate": hit_rate,
            "meanReciprocalRank": mrr,
            "meanPrecisionAtK": mean_precision,
            "meanRecallAtK": mean_recall,
            "latencyP50Ms": p50_latency,
            "latencyP95Ms": p95_latency,
            "latencyAvgMs": avg_latency
        },
        "testCases": results
    }

    out_file = os.path.join(EVAL_DIR, f"eval_results_{method}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(eval_output, f, indent=2)

    # Also save as main eval_results.json
    with open(os.path.join(EVAL_DIR, "eval_results.json"), "w", encoding="utf-8") as f:
        json.dump(eval_output, f, indent=2)

    return eval_output

if __name__ == "__main__":
    method_arg = "vector"
    strat_arg = "semantic"
    for arg in sys.argv[1:]:
        if arg in ["vector", "bm25", "hybrid"]:
            method_arg = arg
        elif arg in ["semantic", "fixed", "sliding"]:
            strat_arg = arg

    run_evaluation(strategy=strat_arg, method=method_arg)
