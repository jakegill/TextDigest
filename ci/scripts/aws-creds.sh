#!/usr/bin/env bash
# Exchange a Google-issued ID token for short-lived AWS creds via
# sts:AssumeRoleWithWebIdentity. Writes /workspace/.aws-creds.env which the
# sst-deploy step sources.

set -euo pipefail

: "${_AWS_ROLE_ARN:?required}"

ID_TOKEN=$(curl -fsS \
  -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=https://sts.amazonaws.com&format=standard")

# 2) Trade it for AWS creds. Session name has to be DNS-safe (no dots).
read -r AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN EXPIRY < <(
  aws sts assume-role-with-web-identity \
    --role-arn "${_AWS_ROLE_ARN}" \
    --role-session-name "td-cicd-${_STAGE:-bootstrap}" \
    --web-identity-token "${ID_TOKEN}" \
    --duration-seconds 3600 \
    --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken,Expiration]' \
    --output text
)
: "${AWS_ACCESS_KEY_ID:?assume-role-with-web-identity returned no credentials}"

# 3) Persist as a sourceable env file.
cat > /workspace/.aws-creds.env <<EOF
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}
AWS_REGION=us-east-1
EOF

echo "aws creds ready (expires ${EXPIRY})"
