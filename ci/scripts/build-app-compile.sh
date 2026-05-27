#!/usr/bin/env bash
# Compile the Next.js app to apps/app/out. Runs in node:22.

set -euo pipefail

: "${_API_URL:?required}"
: "${_FB_API_KEY:?required}"
: "${_FB_AUTH_DOMAIN:?required}"
: "${_FB_PROJECT_ID:?required}"

export NEXT_PUBLIC_API_URL="${_API_URL}"
export NEXT_PUBLIC_FIREBASE_API_KEY="${_FB_API_KEY}"
export NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN="${_FB_AUTH_DOMAIN}"
export NEXT_PUBLIC_FIREBASE_PROJECT_ID="${_FB_PROJECT_ID}"

corepack enable
pnpm install --frozen-lockfile
pnpm --filter @td/app build
