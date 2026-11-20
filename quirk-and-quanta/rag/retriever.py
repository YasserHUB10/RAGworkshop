"""
Quirk & Quanta - Vector Similarity Retriever
Performs in-memory cosine similarity search over versioned chunk embeddings
with Role-Based Access Control (RBAC) filtering and citation mapping.
"""

import os
import sys
import json
import time
import math
from typing import List, Dict, Any, Optional

# Add scripts directory for offline embedding fallback
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.append(SCRIPTS_DIR)

from generate_embeddings import (
    cosine_similarity,
    normalize_vector,
    generate_offline_embedding,
    call_gemini_api_batch,
    DIMENSIONS,
    MODEL_NAME
)

CHUNKS_DIR = os.path.join(ROOT_DIR, "data", "chunks")
EMBEDDINGS_DIR = os.path.join(ROOT_DIR, "data", "embeddings", "v1")

class QuirkRetriever:
    def __init__(self, default_strategy: str = "semantic"):
        self.default_strategy = default_strategy
        self.chunks_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.embeddings_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.query_cache: Dict[str, Any] = {}
        self._load_query_cache()

    def _load_query_cache(self):
        cache_path = os.path.join(EMBEDDINGS_DIR, "query_embeddings_cache.json")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                self.query_cache = json.load(f)

    def _load_strategy(self, strategy: str):
        if strategy not in self.chunks_cache:
            chunk_file = os.path.join(CHUNKS_DIR, f"chunks_{strategy}.json")
            emb_file = os.path.join(EMBEDDINGS_DIR, f"embeddings_{strategy}.json")

            if not os.path.exists(chunk_file) or not os.path.exists(emb_file):
                raise FileNotFoundError(f"Missing chunk/embedding data for strategy: {strategy}")

            with open(chunk_file, "r", encoding="utf-8") as f:
                chunks = json.load(f)
            with open(emb_file, "r", encoding="utf-8") as f:
                embeddings = json.load(f)

            # Map chunks by chunkId
            chunk_map = {c["chunkId"]: c for c in chunks}
            for emb in embeddings:
                cid = emb["chunkId"]
                if cid in chunk_map:
                    emb["chunkData"] = chunk_map[cid]

            self.chunks_cache[strategy] = chunks
            self.embeddings_cache[strategy] = embeddings

    def embed_query(self, query_text: str, api_key: Optional[str] = None) -> tuple[List[float], str]:
        """
        Embeds a user query.
        Returns (vector, execution_mode).
        """
        # Check precomputed golden questions cache first
        for item in self.query_cache.values():
            if item["question"].strip().lower() == query_text.strip().lower():
                return item["vector"], "cached_query_embedding"

        # If live API key is provided, use live Gemini API
        if api_key:
            try:
                vectors = call_gemini_api_batch([query_text], api_key, task_type="RETRIEVAL_QUERY")
                if vectors:
                    return vectors[0], "live_gemini_api"
            except Exception as e:
                pass  # Fall back to deterministic projection

        # Offline deterministic projection
        return generate_offline_embedding(query_text, task_type="RETRIEVAL_QUERY"), "offline_projection"

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        strategy: str = "semantic",
        role: str = "customer",
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()
        self._load_strategy(strategy)

        # Step 1: Embed query
        emb_start = time.perf_counter()
        query_vec, mode = self.embed_query(query, api_key)
        emb_time_ms = round((time.perf_counter() - emb_start) * 1000, 2)

        # Step 2: Filter by Role-Based Access Control (RBAC)
        ret_start = time.perf_counter()
        candidates = self.embeddings_cache[strategy]
        filtered = []

        for item in candidates:
            # RBAC check: Customers can only access 'public' chunks
            access = item.get("accessLevel", "public")
            allowed_roles = item.get("allowedRoles", ["customer", "admin", "procurement"])

            if role.lower() == "customer" and access != "public":
                continue
            if role.lower() not in [r.lower() for r in allowed_roles]:
                continue

            filtered.append(item)

        # Step 3: Compute Cosine Similarity
        scored = []
        for item in filtered:
            score = cosine_similarity(query_vec, item["vector"])
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_items = scored[:top_k]
        ret_time_ms = round((time.perf_counter() - ret_start) * 1000, 2)

        # Step 4: Map to Evidence and Citations
        evidence_list = []
        for rank, (score, item) in enumerate(top_items, 1):
            cdata = item.get("chunkData", {})
            meta = cdata.get("metadata", {})
            citation_info = meta.get("citation", {})

            evidence_list.append({
                "rank": rank,
                "score": round(score, 4),
                "chunkId": item["chunkId"],
                "docId": item["docId"],
                "sourceId": item["sourceId"],
                "accessLevel": item["accessLevel"],
                "strategy": strategy,
                "sectionTitle": cdata.get("sectionTitle", meta.get("section", "General")),
                "text": cdata.get("text", ""),
                "citation": {
                    "label": citation_info.get("label", f"Document {item['sourceId']}"),
                    "url": citation_info.get("url", "#"),
                    "sectionName": citation_info.get("sectionName", "Catalog Dossier")
                }
            })

        total_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "query": query,
            "role": role,
            "strategy": strategy,
            "topK": top_k,
            "embeddingMode": mode,
            "evidenceCount": len(evidence_list),
            "evidence": evidence_list,
            "latency": {
                "embeddingMs": emb_time_ms,
                "retrievalMs": ret_time_ms,
                "totalMs": total_time_ms
            }
        }
