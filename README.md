# Text Digest

## Architecture

- Monorepo, multiple services

```
/
├── apps/           # Services: frontend, api, ml inference
│   │
│   ├── app/        # Next.js web app (frontend)
│   ├── proxy/      # Nginx proxy for nextjs build + cdn (DNT)
│   ├── api/        # FastAPI api
│   └── mineru/     # MinerU inference service
│
├── ci/             # CI/CD via Google Cloud Build
│
├── infra/          # IaC via SST Framework, Google Cloud Provider
└── sst.config.ts
```

## Local Development Workflow

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

## Github & CICD Workflow

```
feature branch (<initials>/<feature-name>, e.g. jg/health-endpoint)
        │
        ▼
    staging          ← PR + CI checks. Manually test on the staging URL.
        │
        ▼
      prod           ← PR from staging + approval
```

### Prereq: Bootstrap CI Runner

- One per repo. (DONE)

```bash
BOOTSTRAP=1 pnpm exec sst deploy --stage staging
```

### 1. Merge to staging

- Open a PR from your feature branch into `staging`.
- Push/merge into staging triggers deployment in GCP.

### 2. Promote to prod

1. Open a PR from `staging` into `prod`.
2. Merging triggers deployment to prod in GCP.

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

4. Set the active project and the ADC quota project (the latter is required by APIs like `identitytoolkit` that bill the calling project):

    ```bash
    gcloud config set project <your-dev-project-id>
    gcloud auth application-default set-quota-project <your-dev-project-id>
    ```

### Enable Google sign-in (One-time, per GCP project)

In the Firebase console (one click, ever):
`https://console.firebase.google.com/project/<project-id>/authentication/providers`
→ click **Google** → toggle **Enable** → pick a support email → **Save**.

Firebase auto-creates the OAuth client behind the scenes — no Cloud Console form, no secrets.

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
