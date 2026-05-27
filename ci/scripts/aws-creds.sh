#!/usr/bin/env bash
# Exchange a Google-issued ID token for short-lived AWS creds via
# sts:AssumeRoleWithWebIdentity. Writes /workspace/.aws-creds.env which the
# sst-deploy step sources.

set -euo pipefail

: "${_AWS_ACCOUNT_ID:?required}"
: "${_AWS_ROLE_ARN:?required}"

# 1) Get a Google ID token from the metadata server. Audience must match
#    what's in the AWS IAM role trust policy (we use the AWS account ID).
ID_TOKEN=$(curl -fsS \
  -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${_AWS_ACCOUNT_ID}&format=full")

# 2) Trade it for AWS creds. Session name has to be DNS-safe (no dots).
CREDS=$(aws sts assume-role-with-web-identity \
  --role-arn "${_AWS_ROLE_ARN}" \
  --role-session-name "td-cicd-${_STAGE:-bootstrap}" \
  --web-identity-token "${ID_TOKEN}" \
  --duration-seconds 3600)

# 3) Persist as a sourceable env file. The sst-deploy step does
#    `set -a; . /workspace/.aws-creds.env; set +a`.
cat > /workspace/.aws-creds.env <<EOF
AWS_ACCESS_KEY_ID=$(echo "${CREDS}" | jq -r '.Credentials.AccessKeyId')
AWS_SECRET_ACCESS_KEY=$(echo "${CREDS}" | jq -r '.Credentials.SecretAccessKey')
AWS_SESSION_TOKEN=$(echo "${CREDS}" | jq -r '.Credentials.SessionToken')
AWS_REGION=us-east-1
EOF

echo "aws creds ready (expires $(echo "${CREDS}" | jq -r '.Credentials.Expiration'))"
