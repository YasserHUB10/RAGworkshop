"""
Quirk & Quanta - End-to-End RAG Pipeline Coordinator
Executes query embedding, multi-strategy retrieval (Vector, BM25, Hybrid),
RBAC enforcement, and grounded answer generation with latency telemetry.
"""

import os
import time
from typing import Dict, Any, Optional
from .retriever import QuirkRetriever
from .generator import generate_grounded_answer

class RAGPipeline:
    def __init__(self, default_strategy: str = "semantic"):
        self.retriever = QuirkRetriever(default_strategy=default_strategy)

    def ask(
        self,
        question: str,
        top_k: int = 5,
        strategy: str = "semantic",
        method: str = "auto",
        role: str = "customer",
        retrieval_only: bool = False,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes the full RAG pipeline or retrieval-only mode across Vector, BM25, or Hybrid methods.
        """
        pipeline_start = time.perf_counter()

        # Step 1 & 2: Multi-Strategy Retrieval
        retrieval_result = self.retriever.retrieve(
            query=question,
            top_k=top_k,
            strategy=strategy,
            role=role,
            method=method,
            api_key=api_key
        )

        evidence = retrieval_result["evidence"]

        # If retrieval-only mode requested:
        if retrieval_only:
            total_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)
            retrieval_result["latency"]["totalMs"] = total_ms
            retrieval_result["retrievalOnly"] = True
            retrieval_result["answer"] = None
            return retrieval_result

        # Step 3: Grounded Answer Generation
        gen_result = generate_grounded_answer(
            query=question,
            evidence=evidence,
            role=role,
            api_key=api_key
        )

        total_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)

        return {
            "question": question,
            "role": role,
            "strategy": retrieval_result.get("strategy", strategy),
            "retrievalMethod": retrieval_result.get("retrievalMethod", method),
            "topK": top_k,
            "retrievalOnly": False,
            "executionMode": gen_result["mode"],
            "generationModel": gen_result.get("model", "grounded_local_synthesizer"),
            "answer": gen_result["answer"],
            "citations": gen_result["citations"],
            "evidence": evidence,
            "latency": {
                **retrieval_result.get("latency", {}),
                "generationMs": gen_result["latencyMs"],
                "totalMs": total_ms
            }
        }

    def compare(
        self,
        question: str,
        top_k: int = 5,
        strategy: str = "semantic",
        role: str = "customer",
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Performs side-by-side comparison across Vector, BM25, and Hybrid RRF retrieval.
        """
        vec_res = self.retriever.retrieve_vector(question, top_k=top_k, strategy=strategy, role=role, api_key=api_key)
        bm25_res = self.retriever.retrieve_bm25(question, top_k=top_k, strategy=strategy, role=role)
        hybrid_res = self.retriever.retrieve_hybrid(question, top_k=top_k, strategy=strategy, role=role, api_key=api_key)

        return {
            "question": question,
            "role": role,
            "topK": top_k,
            "vector": vec_res,
            "bm25": bm25_res,
            "hybrid": hybrid_res
        }
