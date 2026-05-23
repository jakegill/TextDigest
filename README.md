# Text Digest

## Architecture

```
text-digest/
├── apps/
│   ├── app/        # Next.js web app
│   ├── api/        # FastAPI api
│   └── mineru/     # MinerU inference pipeline
├── infra/          # IaC SST, GCP
└── sst.config.ts
```

## Development Workflow

### Prerequisites

- Node 22+
- pnpm 10+
- Python 3.13 + [`uv`](https://docs.astral.sh/uv/)
- Docker
- Google Cloud CLI
- WSL (if using windows - SST requires unix environment)

_See appendix for install information_

### First-time setup (per machine)

```bash
pnpm install
pnpm exec sst install          # generates .sst/platform/ type defs
```

Then create `apps/app/.env.local` mirroring `apps/app/.env.local.example`.

### Personal Dev Stages

- **Docker Daemon must be running**
- Each developer gets their own isolated set of resources GCP project.
- Use lowercase initials — `jg`, `td`, etc. Use the same initials every time so resources are reused across sessions instead of re-provisioned.

```bash
pnpm dev <your-initials>     # e.g. pnpm dev jg
```

- `sst dev` starts a live multiplexer in your terminal: redeploying on api changes + `next dev` for the frontend with `NEXT_PUBLIC_API_URL`
- This means that for all changes made, despite being a serverless deployment, are as if you are developing locally / instantly reflected.

### Cleanup a stage

```bash
pnpm exec sst remove --stage jg     # deletes all resources for this stage
```

- SST does not auto-cleanup, skipping this leaves resources in GCP ($).

---

## Github Branching Workflow

```
feature branch (<initials>/<feature-name>, e.g. jg/health-endpoint)
        │
        ▼
    staging          ← PR + CI checks. Manually test on the staging URL.
        │
        ▼
      prod           ← PR from staging + approval
```

### 1. Merge to staging

- Open a PR from your feature branch into `staging`.
- Smoke test on live deployed staging endpoint

### 2. Promote to prod

1. Open a PR from `staging` into `prod`. This is a promotion — staging must already have been tested.
2. Merging triggers `deploy-prod.yml` (gated on `head.ref == 'staging'`).

### Stage retention

Both `staging` and `prod` use `removal: "retain"` — an accidental `sst remove` skips destroy calls and leaves resources orphaned rather than deleted.

---

## Appendix

### Setup GCP (One-time, per machine)

1. Install the gcloud CLI:

    ```bash
    brew install --cask google-cloud-sdk
    ```

2. Log in (CLI auth, interactive browser flow):

    ```bash
    gcloud auth login
    ```

3. Set up Application Default Credentials (what Pulumi/SST reads — separate from CLI auth):

    ```bash
    gcloud auth application-default login
    ```

---

SST stores its Pulumi state in an S3 bucket (No GCP support for SST). Resources still deploy to GCP — AWS is metadata-only.

### Setup AWS (One-time, per machine)

1. Install the AWS CLI:

    ```bash
    brew install awscli
    ```

2. Log in with credentials that can create/read/write an S3 bucket (`AdministratorAccess` works, or `s3:CreateBucket` + `s3:Get*` + `s3:Put*` + `s3:List*` + `s3:Delete*`):

    ```bash
    aws configure        # or `aws sso login --profile <name>` if using SSO
    ```

3. Verify:

    ```bash
    aws sts get-caller-identity
    ```

SST auto-creates the state bucket on the first `sst dev` / `sst deploy` run — no manual bucket setup required.

### Setup Node / SST

#### Install Node

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 22
```

#### Install pnpm

```bash
corepack enable
corepack prepare pnpm@10.33.0 --activate
```

#### Install SST

```bash
curl -fsSL https://sst.dev/install | bash
```
