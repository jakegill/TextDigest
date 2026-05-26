#!/usr/bin/env bash

set -euo pipefail

STAGE="${1:-}"
if [[ -z "$STAGE" ]]; then
	echo "usage: pnpm dev <stage>" >&2
	echo "       e.g. pnpm dev jg" >&2
	exit 1
fi

# Kill leftover processes from prev/concurrent runtimes
LEFTOVER=$(lsof -ti:3000,8080 2>/dev/null || true)
if [[ -n "$LEFTOVER" ]]; then
	echo "killing leftover dev processes on :3000/:8080 (pids: $LEFTOVER)" >&2
	kill -9 $LEFTOVER 2>/dev/null || true
	sleep 1
fi

# Inject GCP ID for personal stages into sst.config.ts.
export GOOGLE_PROJECT="$(gcloud config get-value project 2>/dev/null)"
if [[ -z "$GOOGLE_PROJECT" ]]; then
	echo "error: no active GCP project. Run: gcloud config set project <id>" >&2
	exit 1
fi

# Surface the active gcloud user so infra/cpu.ts can grant them the rights to
# impersonate api-sa locally (needed for OIDC token minting in dev).
export DEV_USER_EMAIL="$(gcloud config get-value account 2>/dev/null)"
if [[ -z "$DEV_USER_EMAIL" ]]; then
	echo "error: no active gcloud account. Run: gcloud auth login" >&2
	exit 1
fi

# Build a per-process ADC file that impersonates api-sa, for the uvicorn
# child only. This lets the api Python code use stock `id_token.fetch_id_token`
# (same as on Cloud Run) without any conditional logic, while SST/Pulumi keeps
# using your normal admin ADC. DEV_ADC_PATH is consumed in infra/cpu.ts and
# injected into the Api DevCommand as GOOGLE_APPLICATION_CREDENTIALS.
USER_ADC="$HOME/.config/gcloud/application_default_credentials.json"
if [[ ! -f "$USER_ADC" ]]; then
	echo "error: no ADC found at $USER_ADC. Run: gcloud auth application-default login" >&2
	exit 1
fi
API_SA_EMAIL="td-${STAGE}-api-sa@${GOOGLE_PROJECT}.iam.gserviceaccount.com"
export DEV_ADC_PATH="/tmp/td-${STAGE}-api-sa-adc.json"
SOURCE_CREDS=$(cat "$USER_ADC")
cat > "$DEV_ADC_PATH" <<EOF
{
  "type": "impersonated_service_account",
  "service_account_impersonation_url": "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${API_SA_EMAIL}:generateAccessToken",
  "delegates": [],
  "source_credentials": ${SOURCE_CREDS}
}
EOF
chmod 600 "$DEV_ADC_PATH"

# Authenticate docker to push to Artifact Registry. Idempotent (writes ~/.docker/config.json).
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

# Required gcloud components — idempotent installs.
# - beta: for `gcloud beta logging tail`
# - log-streaming: gRPC bits for live log tailing (the Mineru DevCommand uses this)
gcloud components install beta log-streaming --quiet

(cd apps/api && uv sync)

pnpm exec sst install --print-logs

# Refresh if the stage already has state to avoid divergence between machines — `sst refresh`
if pnpm exec sst state export --stage "$STAGE" >/dev/null 2>&1; then
	pnpm exec sst refresh --stage "$STAGE" --print-logs
fi

pnpm exec sst dev --stage "$STAGE"
