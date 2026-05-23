#!/usr/bin/env bash

set -euo pipefail

STAGE="${1:-}"
if [[ -z "$STAGE" ]]; then
	echo "usage: pnpm dev <stage>" >&2
	echo "       e.g. pnpm dev jg" >&2
	exit 1
fi

# Inject GCP ID for personal stages into sst.config.ts.
export GOOGLE_PROJECT="$(gcloud config get-value project 2>/dev/null)"
if [[ -z "$GOOGLE_PROJECT" ]]; then
	echo "error: no active GCP project. Run: gcloud config set project <id>" >&2
	exit 1
fi

# Authenticate docker to push to Artifact Registry. Idempotent (writes ~/.docker/config.json).
gcloud auth configure-docker us-east1-docker.pkg.dev --quiet

pnpm exec sst install --print-logs

# Refresh if the stage already has state to avoid divergence between machines — `sst refresh`
if pnpm exec sst state export --stage "$STAGE" >/dev/null 2>&1; then
	pnpm exec sst refresh --stage "$STAGE" --print-logs
fi

pnpm exec sst dev --stage "$STAGE"
