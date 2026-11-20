#!/usr/bin/env python3
"""
Quirk & Quanta - Unified Storefront & RAG API Server
Zero external dependencies (uses standard library http.server).
Serves static storefront assets from site/ and provides live JSON endpoints:
- POST /api/rag/retrieve (Multi-strategy Retrieval: Vector, BM25, Hybrid)
- POST /api/rag/ask      (Full grounded RAG pipeline with Guardrails & Server RBAC)
- POST /api/rag/compare  (Side-by-side Vector vs BM25 vs Hybrid comparison)
- POST /api/rag/graph    (Multi-hop Knowledge Graph defect investigation)
- POST /api/rag/doc      (Direct Document Access with IDOR protection)
- GET  /api/rag/auth/demo-token (Generates authentic signed HMAC bearer token)
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
CORPUS_DIR = os.path.join(ROOT_DIR, "data", "corpus")

if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from rag.pipeline import RAGPipeline
from rag.graph_local import get_graph
from rag.graph_neo4j import get_neo4j_adapter
from rag.auth import create_signed_token, resolve_effective_role, check_resource_access

pipeline = RAGPipeline(default_strategy="semantic")
graph = get_graph()
neo4j_adapter = get_neo4j_adapter()

class QuirkHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SITE_DIR, **kwargs)

    def translate_path(self, path):
        """
        Security hardening: Canonicalizes path to prevent directory traversal
        outside of SITE_DIR (e.g. attempting to read data/internal/ or private source).
        """
        resolved = super().translate_path(path)
        normalized = os.path.realpath(resolved)
        real_site_dir = os.path.realpath(SITE_DIR)
        if not (normalized == real_site_dir or normalized.startswith(real_site_dir + os.sep)):
            return os.path.join(real_site_dir, "__blocked_path_traversal__")
        return resolved

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

        if path in ["/healthz", "/health", "/api/health"]:
            self._send_json({
                "status": "healthy",
                "service": "quirk-quanta-rag",
                "region": "asia-south1",
                "version": "1.0.0",
                "environment": "production-ready"
            })
            return

        if path == "/api/rag/status":
            api_key = os.environ.get("GEMINI_API_KEY", "")
            manifest_file = os.path.join(ROOT_DIR, "data", "embeddings", "v1", "embeddings_manifest.json")
            manifest = json.load(open(manifest_file)) if os.path.exists(manifest_file) else {}

            self._send_json({
                "status": "ready",
                "service": "quirk-quanta-rag",
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
                    "ENABLE_GRAPH_NEO4J": True,
                    "ENABLE_GENERATION": True,
                    "ENABLE_GROUNDING": True,
                    "ENABLE_PROMPT_INJECTION_DEFENSE": True,
                    "ENABLE_RBAC": True,
                    "ENABLE_USAGE_LIMITS": True,
                    "ENABLE_OBSERVABILITY": True,
                    "ENABLE_RECORDED_DEMOS": True
                },
                "chunkingClassification": {
                    "semantic": "Structural / Heading-Based Section Splitting (H1/H2 Markdown boundaries)",
                    "fixed": "Fixed-Size 450-Char Word-Bounded Splitting",
                    "sliding": "Sliding-Window 450-Char / 150-Overlap Splitting"
                },
                "graphNodes": len(graph.nodes),
                "neo4j": neo4j_adapter.get_telemetry(),
                "observability": pipeline.tracer.get_aggregate_telemetry(),
                "embeddings": manifest.get("strategies", {}),
                "totalChunks": manifest.get("totalChunksEmbedded", 0)
            })
            return

        elif path == "/api/rag/traces":
            traces = pipeline.tracer.get_recent_traces(limit=25)
            self._send_json(traces)
            return

        elif path == "/api/rag/traces/aggregate":
            telemetry = pipeline.tracer.get_aggregate_telemetry()
            self._send_json(telemetry)
            return

        elif path == "/api/rag/auth/demo-token":
            # Issues authentic demo admin session token for workshop presenters
            token = create_signed_token(role="admin", user_id="dr_arthur")
            self._send_json({
                "role": "admin",
                "userId": "dr_arthur",
                "token": token,
                "type": "Bearer",
                "note": "Use in Authorization header 'Bearer <token>' or authToken parameter to authenticate as Admin."
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

        # Extract Auth Bearer header or JSON token
        auth_header = self.headers.get("Authorization", "")
        auth_token = params.get("authToken")
        if not auth_token and auth_header.startswith("Bearer "):
            auth_token = auth_header[7:].strip()

        question = params.get("question", "").strip()
        top_k = int(params.get("topK", 5))
        strategy = params.get("strategy", "semantic")
        method = params.get("method", "auto")
        role = params.get("role", "customer")
        hardened = bool(params.get("hardened", True))
        session_id = params.get("sessionId", "workshop_session")
        api_key = os.environ.get("GEMINI_API_KEY")

        # Resolve effective role at the server HTTP boundary
        effective_role, was_tampered, auth_msg = resolve_effective_role(
            requested_role=role,
            auth_token=auth_token,
            hardened=hardened
        )

        if path == "/api/rag/retrieve":
            if not question:
                self._send_json({"error": "Field 'question' is required"}, status=400)
                return
            result = pipeline.ask(
                question=question,
                top_k=top_k,
                strategy=strategy,
                method=method,
                role=effective_role,
                auth_token=auth_token,
                retrieval_only=True,
                api_key=api_key,
                hardened=hardened,
                session_id=session_id
            )
            result["roleResolution"] = {
                "requestedRole": role,
                "effectiveRole": effective_role,
                "wasTampered": was_tampered,
                "authMessage": auth_msg
            }
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
                role=effective_role,
                auth_token=auth_token,
                retrieval_only=False,
                api_key=api_key,
                hardened=hardened,
                session_id=session_id
            )
            result["roleResolution"] = {
                "requestedRole": role,
                "effectiveRole": effective_role,
                "wasTampered": was_tampered,
                "authMessage": auth_msg
            }
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
            
            graph_engine = params.get("engine", "local").lower()
            if graph_engine in ["neo4j", "auradb"]:
                result = neo4j_adapter.trace_defect_root_cause(skus)
            else:
                result = graph.trace_defect_root_cause(skus)
            self._send_json(result)
            return

        elif path == "/api/rag/doc":
            # IDOR Inspection endpoint (Demo 16)
            doc_id = params.get("docId", "")
            if not doc_id:
                self._send_json({"error": "Field 'docId' is required"}, status=400)
                return

            # Determine resource classification
            is_internal = "PROC" in doc_id or "INTERNAL" in doc_id
            access_level = "internal_procurement" if is_internal else "public"

            effective_role, was_tampered, auth_msg = resolve_effective_role(
                requested_role=role,
                auth_token=auth_token,
                hardened=hardened
            )

            # Check access
            allowed, access_msg = check_resource_access(doc_id, effective_role, access_level)

            if not allowed:
                self._send_json({
                    "error": "Forbidden",
                    "status": 403,
                    "docId": doc_id,
                    "accessLevel": access_level,
                    "requestedRole": role,
                    "effectiveRole": effective_role,
                    "wasTampered": was_tampered,
                    "securityAlert": access_msg
                }, status=403)
                return

            # If allowed, fetch document text from corpus
            doc_path = os.path.join(CORPUS_DIR, f"{doc_id}.json")
            if not os.path.exists(doc_path):
                # Check with prefix DOC-
                alt_path = os.path.join(CORPUS_DIR, f"DOC-{doc_id}.json")
                if os.path.exists(alt_path):
                    doc_path = alt_path

            doc_content = None
            if os.path.exists(doc_path):
                with open(doc_path, "r", encoding="utf-8") as f:
                    doc_content = json.load(f)
            else:
                doc_content = {
                    "docId": doc_id,
                    "title": f"Dossier {doc_id}",
                    "accessLevel": access_level,
                    "text": f"Confidential supplier contract and procurement margin records for {doc_id}."
                }

            self._send_json({
                "status": 200,
                "docId": doc_id,
                "accessLevel": access_level,
                "effectiveRole": effective_role,
                "wasTampered": was_tampered,
                "authMessage": auth_msg,
                "document": doc_content
            })
            return

        elif path == "/api/rag/simulate-spike":
            # Story 7 Cost Spike Simulation (Demo 14)
            iterations = int(params.get("iterations", 40))
            spike_data = pipeline.tracer.simulate_cost_spike(iterations=iterations)
            self._send_json(spike_data)
            return

        self._send_json({"error": f"Endpoint not found: {path}"}, status=404)

def create_server(port=8000, host="0.0.0.0"):
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    server = http.server.ThreadingHTTPServer((host, port), QuirkHTTPRequestHandler)
    server.daemon_threads = True
    return server

def run_server(port=None, host="0.0.0.0"):
    if port is None:
        port_env = os.environ.get("PORT")
        port = int(port_env) if port_env else 8000
    with create_server(port, host) as httpd:
        print("=" * 60)
        print(f"QUIRK & QUANTA UNIFIED STOREFRONT & RAG SERVER (Concurrent Threading)")
        print("=" * 60)
        print(f"Binding Address:     http://{host}:{port}")
        print(f"Serving static site: {SITE_DIR}")
        print(f"Storefront URL:      http://localhost:{port}/index.html")
        print(f"Workshop Lab URL:    http://localhost:{port}/workshop.html")
        print(f"Health Check:        http://localhost:{port}/healthz")
        print(f"API Endpoints:")
        print(f"  - POST http://localhost:{port}/api/rag/retrieve")
        print(f"  - POST http://localhost:{port}/api/rag/ask")
        print(f"  - POST http://localhost:{port}/api/rag/compare")
        print(f"  - POST http://localhost:{port}/api/rag/graph")
        print(f"  - POST http://localhost:{port}/api/rag/doc")
        print(f"  - GET  http://localhost:{port}/api/rag/auth/demo-token")
        print(f"  - GET  http://localhost:{port}/api/rag/status")
        print(f"  - GET  http://localhost:{port}/api/rag/questions")
        print(f"  - GET  http://localhost:{port}/api/rag/telemetry")
        print(f"  - GET  http://localhost:{port}/healthz")
        print("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")

if __name__ == "__main__":
    port_env = os.environ.get("PORT")
    port_val = int(port_env) if port_env else 8000
    if len(sys.argv) > 1:
        try:
            port_val = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port=port_val, host="0.0.0.0")
