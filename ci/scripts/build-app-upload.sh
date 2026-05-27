#!/usr/bin/env bash
# Upload the built app to GCS, set cache headers, invalidate CDN.
# Runs in gcr.io/google.com/cloudsdktool/cloud-sdk:slim.

set -euo pipefail

: "${_STAGE:?required}"

gcloud storage rsync apps/app/out "gs://td-${_STAGE}-web" \
  --recursive \
  --delete-unmatched-destination-objects \
  --cache-control='public,max-age=0,s-maxage=31536000,must-revalidate'

gcloud storage objects update "gs://td-${_STAGE}-web/_next/static/**" \
  --cache-control='max-age=31536000,public,immutable'

gcloud compute url-maps invalidate-cdn-cache "td-${_STAGE}-web-urlmap" \
  --path='/*' \
  --async
