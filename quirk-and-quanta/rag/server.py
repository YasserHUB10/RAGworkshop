#!/usr/bin/env python3
"""
Quirk & Quanta - Unified Storefront & RAG API Server
Zero external dependencies (uses standard library http.server).
Serves static storefront assets from site/ and provides live JSON endpoints:
- POST /api/rag/retrieve (Multi-strategy Retrieval: Vector, BM25, Hybrid)
- POST /api/rag/ask      (Full grounded RAG pipeline with Guardrails)
- POST /api/rag/compare  (Side-by-side Vector vs BM25 vs Hybrid comparison)
- POST /api/rag/graph    (Multi-hop Knowledge Graph defect investigation)
- GET  /api/rag/status   (System health & model telemetry)
- GET  /api/rag/questions (Curated golden evaluation questions)
- GET  /api/rag/telemetry (Chunking strategy statistics)
"""

import os
import sys
import json
import http.server
import socketserver
from urllib.parse import urlparse

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT_DIR, "site")
EVAL_DIR = os.path.join(ROOT_DIR, "data", "evaluation")
CHUNKS_DIR = os.path.join(ROOT_DIR, "data", "chunks")

if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from rag.pipeline import RAGPipeline
from rag.graph_local import get_graph

pipeline = RAGPipeline(default_strategy="semantic")
graph = get_graph()

class QuirkHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SITE_DIR, **kwargs)

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/rag/status":
            api_key = os.environ.get("GEMINI_API_KEY", "")
            manifest_file = os.path.join(ROOT_DIR, "data", "embeddings", "v1", "embeddings_manifest.json")
            manifest = json.load(open(manifest_file)) if os.path.exists(manifest_file) else {}

            self._send_json({
                "status": "ready",
                "embeddingModel": "gemini-embedding-001",
                "vectorDimensions": 768,
                "generationModel": "gemini-2.5-flash",
                "hasGeminiKey": bool(api_key),
                "activeMode": "live_gemini" if bool(api_key) else "offline_reference",
                "featureFlags": {
                    "ENABLE_VECTOR": True,
                    "ENABLE_BM25": True,
                    "ENABLE_HYBRID": True,
                    "ENABLE_GRAPH_LOCAL": True,
                    "ENABLE_GRAPH_NEO4J": False,
                    "ENABLE_GENERATION": True,
                    "ENABLE_GROUNDING": True,
                    "ENABLE_PROMPT_INJECTION_DEFENSE": True,
                    "ENABLE_RBAC": True,
                    "ENABLE_USAGE_LIMITS": True,
                    "ENABLE_OBSERVABILITY": False,
                    "ENABLE_RECORDED_DEMOS": True
                },
                "graphNodes": len(graph.nodes),
                "embeddings": manifest.get("strategies", {}),
                "totalChunks": manifest.get("totalChunksEmbedded", 0)
            })
            return

        elif path == "/api/rag/questions":
            golden_path = os.path.join(EVAL_DIR, "golden_dataset.json")
            if os.path.exists(golden_path):
                questions = json.load(open(golden_path))
                self._send_json(questions)
            else:
                self._send_json([], status=404)
            return

        elif path == "/api/rag/telemetry":
            telemetry_path = os.path.join(CHUNKS_DIR, "chunks_manifest.json")
            if os.path.exists(telemetry_path):
                data = json.load(open(telemetry_path))
                self._send_json(data)
            else:
                self._send_json({}, status=404)
            return

        # Fallback to serving static storefront assets
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            params = json.loads(post_body.decode("utf-8"))
        except Exception:
            self._send_json({"error": "Invalid JSON in request body"}, status=400)
            return

        question = params.get("question", "").strip()
        top_k = int(params.get("topK", 5))
        strategy = params.get("strategy", "semantic")
        method = params.get("method", "auto")
        role = params.get("role", "customer")
        hardened = bool(params.get("hardened", True))
        session_id = params.get("sessionId", "workshop_session")
        api_key = os.environ.get("GEMINI_API_KEY")

        if path == "/api/rag/retrieve":
            if not question:
                self._send_json({"error": "Field 'question' is required"}, status=400)
                return
            result = pipeline.ask(
                question=question,
                top_k=top_k,
                strategy=strategy,
                method=method,
                role=role,
                retrieval_only=True,
                api_key=api_key,
                hardened=hardened,
                session_id=session_id
            )
            self._send_json(result)
            return

        elif path == "/api/rag/ask":
            if not question:
                self._send_json({"error": "Field 'question' is required"}, status=400)
                return
            result = pipeline.ask(
                question=question,
                top_k=top_k,
                strategy=strategy,
                method=method,
                role=role,
                retrieval_only=False,
                api_key=api_key,
                hardened=hardened,
                session_id=session_id
            )
            self._send_json(result)
            return

        elif path == "/api/rag/compare":
            if not question:
                self._send_json({"error": "Field 'question' is required"}, status=400)
                return
            result = pipeline.compare(
                question=question,
                top_k=top_k,
                strategy=strategy,
                role=role,
                api_key=api_key
            )
            self._send_json(result)
            return

        elif path == "/api/rag/graph":
            skus = params.get("productSkus")
            if not skus and question:
                import re
                skus = re.findall(r'QQ-[0-9]{4}', question.upper())
            if not skus:
                skus = ["QQ-0011", "QQ-0074", "QQ-0049"]
            result = graph.trace_defect_root_cause(skus)
            self._send_json(result)
            return

        self._send_json({"error": f"Endpoint not found: {path}"}, status=404)

def run_server(port=8000):
    handler = QuirkHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print("=" * 60)
        print(f"QUIRK & QUANTA UNIFIED STOREFRONT & RAG SERVER")
        print("=" * 60)
        print(f"Serving static site: {SITE_DIR}")
        print(f"Storefront URL:      http://localhost:{port}/index.html")
        print(f"Workshop Lab URL:    http://localhost:{port}/workshop.html")
        print(f"API Endpoints:")
        print(f"  - POST http://localhost:{port}/api/rag/retrieve")
        print(f"  - POST http://localhost:{port}/api/rag/ask")
        print(f"  - POST http://localhost:{port}/api/rag/compare")
        print(f"  - POST http://localhost:{port}/api/rag/graph")
        print(f"  - GET  http://localhost:{port}/api/rag/status")
        print(f"  - GET  http://localhost:{port}/api/rag/questions")
        print(f"  - GET  http://localhost:{port}/api/rag/telemetry")
        print("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")

if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port_arg)
