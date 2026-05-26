# MinerU

Cloud Run service that wraps MinerU's PDF parsing pipeline behind `POST /parse`. The api calls into this service; nothing else does.

This image is built and pushed **from personal computer**, not by CI — the image bundles models and massive deps like torch, this doesnt fit on a github actions runner and I am not paying for an organization account.

## CI

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev  # One time (DONE!)
```

```bash
# Run from project root
docker buildx build --platform linux/amd64 \
  --tag us-central1-docker.pkg.dev/text-digest-497216/td-mineru/mineru:latest \
  --push apps/mineru \
&& gcloud run deploy td-staging-mineru --region us-central1 \
  --image us-central1-docker.pkg.dev/text-digest-497216/td-mineru/mineru:latest
```
