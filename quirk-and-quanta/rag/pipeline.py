"""
Quirk & Quanta - End-to-End RAG Pipeline Coordinator
Executes query embedding, vector similarity retrieval, RBAC enforcement,
and grounded answer generation with latency telemetry.
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
        role: str = "customer",
        retrieval_only: bool = False,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes the full RAG pipeline or retrieval-only mode.
        """
        pipeline_start = time.perf_counter()

        # Step 1 & 2: Query Embedding and Vector Retrieval
        retrieval_result = self.retriever.retrieve(
            query=question,
            top_k=top_k,
            strategy=strategy,
            role=role,
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
            "strategy": strategy,
            "topK": top_k,
            "retrievalOnly": False,
            "executionMode": gen_result["mode"],
            "generationModel": gen_result.get("model", "grounded_local_synthesizer"),
            "answer": gen_result["answer"],
            "citations": gen_result["citations"],
            "evidence": evidence,
            "latency": {
                "embeddingMs": retrieval_result["latency"]["embeddingMs"],
                "retrievalMs": retrieval_result["latency"]["retrievalMs"],
                "generationMs": gen_result["latencyMs"],
                "totalMs": total_ms
            }
        }
