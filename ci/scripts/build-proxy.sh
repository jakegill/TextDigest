#!/usr/bin/env bash
# Build + push proxy image; emit digest to /workspace/digests/proxy.txt.

set -euo pipefail

: "${PROJECT_ID:?required}"
: "${_STAGE:?required}"

REPO="us-central1-docker.pkg.dev/${PROJECT_ID}/td-${_STAGE}-proxy/proxy"
IMAGE_TAG="${REPO}:latest"
CACHE_TAG="${REPO}:cache"

mkdir -p /workspace/digests

docker buildx create --use --driver docker-container --name td-proxy-builder

docker buildx build \
  --platform linux/amd64 \
  --cache-from type=registry,ref="${CACHE_TAG}" \
  --cache-to type=registry,ref="${CACHE_TAG}",mode=max,image-manifest=true \
  --tag "${IMAGE_TAG}" \
  --metadata-file /workspace/digests/proxy.json \
  --push \
  apps/proxy

DIGEST=$(grep -E '"containerimage\.digest"' /workspace/digests/proxy.json | grep -oE 'sha256:[0-9a-f]{64}')
: "${DIGEST:?failed to parse digest from proxy.json}"
printf '%s\n' "$DIGEST" > /workspace/digests/proxy.txt
echo "proxy digest: $DIGEST"
