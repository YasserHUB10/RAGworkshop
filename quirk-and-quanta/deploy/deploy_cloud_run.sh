#!/usr/bin/env bash
# ==============================================================================
# Quirk & Quanta - Automated Google Cloud Run Deployment Script
# Target Project: momence-support-agent | Region: asia-south1
# Workshop: "Beyond Basic RAG: Building Production-Ready AI Systems"
# ==============================================================================

set -euo pipefail

PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null || echo 'momence-support-agent')}"
REGION="asia-south1"
SERVICE_NAME="quirk-quanta-rag"
IMAGE_TAG="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')"

echo "=============================================================================="
echo "DEPLOYING QUIRK & QUANTA BACKEND TO GOOGLE CLOUD RUN"
echo "=============================================================================="
echo "Target Project:   ${PROJECT_ID}"
echo "Region:           ${REGION}"
echo "Service Name:     ${SERVICE_NAME}"
echo "Image Tag:        ${IMAGE_TAG}"
echo "=============================================================================="

# 1. Check Authentication Preflight
echo "--> [1/4] Checking gcloud authentication and project configuration..."
if ! gcloud auth print-access-token >/dev/null 2>&1; then
    echo "⚠️  Authentication required. Please run: 'gcloud auth login' and try again."
    exit 1
fi

# 2. Build Container using Cloud Build
echo "--> [2/4] Submitting container build to Google Cloud Build..."
gcloud builds submit \
    --project="${PROJECT_ID}" \
    --tag="${IMAGE_TAG}" \
    --substitutions=_SERVICE="${SERVICE_NAME}" \
    deploy/

# 3. Deploy to Cloud Run
echo "--> [3/4] Deploying container image to Cloud Run (${REGION})..."
gcloud run deploy "${SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --image="${IMAGE_TAG}" \
    --region="${REGION}" \
    --platform="managed" \
    --allow-unauthenticated \
    --port="8080" \
    --memory="2Gi" \
    --cpu="1" \
    --concurrency="20" \
    --min-instances="1" \
    --max-instances="3" \
    --timeout="45s" \
    --set-env-vars="PYTHONUNBUFFERED=1,WORKSHOP_MODE=production"

# 4. Verify Service Health
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT_ID}" --region="${REGION}" --format="value(status.url)")
echo "--> [4/4] Verifying Cloud Run service endpoint health at ${SERVICE_URL}/healthz..."
if curl -sf "${SERVICE_URL}/healthz" >/dev/null; then
    echo "✅ Service successfully deployed and healthy!"
    echo "   URL: ${SERVICE_URL}"
else
    echo "⚠️  Healthcheck failed on ${SERVICE_URL}/healthz"
    exit 1
fi
