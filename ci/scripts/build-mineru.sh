#!/usr/bin/env bash
# Build + push MinerU image; emit digest to /workspace/digests/mineru.txt.
# Runs inside Cloud Build (default pool, E2_HIGHCPU_8).

set -euo pipefail

: "${PROJECT_ID:?required}"
: "${_STAGE:?required}"

REPO="us-central1-docker.pkg.dev/${PROJECT_ID}/td-mineru/mineru"
IMAGE_TAG="${REPO}:${_STAGE}"
CACHE_TAG="${REPO}:cache"

mkdir -p /workspace/digests

docker buildx create --use --driver docker-container --name td-builder

docker buildx build \
  --platform linux/amd64 \
  --cache-from type=registry,ref="${CACHE_TAG}" \
  --cache-to type=registry,ref="${CACHE_TAG}",mode=max,image-manifest=true \
  --tag "${IMAGE_TAG}" \
  --metadata-file /workspace/digests/mineru.json \
  --push \
  apps/mineru

DIGEST=$(grep -E '"containerimage\.digest"' /workspace/digests/mineru.json | grep -oE 'sha256:[0-9a-f]{64}')
: "${DIGEST:?failed to parse digest from mineru.json}"
printf '%s\n' "$DIGEST" > /workspace/digests/mineru.txt
echo "mineru digest: $DIGEST"
