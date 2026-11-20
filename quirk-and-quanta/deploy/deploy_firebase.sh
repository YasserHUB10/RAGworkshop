#!/usr/bin/env bash
# Quirk & Quanta - Firebase Hosting Deployment Automation
# Deploys the static storefront and reverse proxy rules to Firebase Hosting
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GCP_PROJECT="momence-support-agent"
SERVICE_NAME="quirk-quanta-rag"
REGION="asia-south1"

echo "======================================================================"
echo "QUIRK & QUANTA - FIREBASE HOSTING DEPLOYMENT"
echo "Project:  ${GCP_PROJECT}"
echo "Backend:  ${SERVICE_NAME} (${REGION})"
echo "======================================================================"

cd "${PROJECT_ROOT}"

# 1. Preflight checks
if [ ! -f "firebase.json" ]; then
    echo "ERROR: firebase.json not found in ${PROJECT_ROOT}" >&2
    exit 1
fi

if [ ! -d "site" ]; then
    echo "ERROR: site/ directory not found in ${PROJECT_ROOT}" >&2
    exit 1
fi

if [ ! -f "site/index.html" ] || [ ! -f "site/workshop.html" ]; then
    echo "ERROR: Essential storefront HTML files missing from site/" >&2
    exit 1
fi

echo "--> Preflight check passed. Site directory and configuration verified."

# 2. Check for Firebase CLI
FIREBASE_CMD=""
if command -v firebase >/dev/null 2>&1; then
    FIREBASE_CMD="firebase"
elif command -v npx >/dev/null 2>&1; then
    FIREBASE_CMD="npx --yes firebase-tools"
fi

if [ -z "${FIREBASE_CMD}" ]; then
    echo "WARNING: Neither 'firebase' nor 'npx' CLI found in PATH."
    echo "To deploy manually once Node/Firebase CLI is present:"
    echo "  npm install -g firebase-tools"
    echo "  firebase login"
    echo "  firebase use ${GCP_PROJECT}"
    echo "  firebase deploy --only hosting"
    exit 0
fi

echo "--> Using Firebase CLI: ${FIREBASE_CMD}"
echo "--> Deploying hosting configuration to ${GCP_PROJECT}..."

${FIREBASE_CMD} deploy --only hosting --project "${GCP_PROJECT}"

echo "======================================================================"
echo "FIREBASE HOSTING DEPLOYMENT COMPLETE"
echo "Public Domain: https://${GCP_PROJECT}.web.app"
echo "               https://${GCP_PROJECT}.firebaseapp.com"
echo "======================================================================"
