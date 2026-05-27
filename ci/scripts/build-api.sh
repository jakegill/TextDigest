#!/usr/bin/env bash
# Build + push api image; emit digest to /workspace/digests/api.txt.

set -euo pipefail

: "${PROJECT_ID:?required}"
: "${_STAGE:?required}"

REPO="us-central1-docker.pkg.dev/${PROJECT_ID}/td-${_STAGE}-api/api"
IMAGE_TAG="${REPO}:latest"
CACHE_TAG="${REPO}:cache"

mkdir -p /workspace/digests

docker buildx create --use --driver docker-container --name td-api-builder

docker buildx build \
  --platform linux/amd64 \
  --cache-from type=registry,ref="${CACHE_TAG}" \
  --cache-to type=registry,ref="${CACHE_TAG}",mode=max,image-manifest=true \
  --tag "${IMAGE_TAG}" \
  --metadata-file /workspace/digests/api.json \
  --push \
  apps/api

jq -r '."containerimage.digest"' /workspace/digests/api.json > /workspace/digests/api.txt
echo "api digest: $(cat /workspace/digests/api.txt)"
