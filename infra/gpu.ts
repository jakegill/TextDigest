/// <reference path="../.sst/platform/config.d.ts" />

// Cloud Run v2 service for apps/mineru (MinerU 3.1.x on NVIDIA L4).
//
// Deploy model:
//   - Local `sst deploy --stage <stage>`: builds apps/mineru via the
//     docker-build provider and pushes :${stage} to the shared td-mineru
//     AR repo (single repo across stages so the ~18 GB model-download
//     layers reuse via registry cache).
//   - CI (staging/prod via GitHub Actions): build is SKIPPED — the GHA
//     runner OOMs on the model-download layers. Cloud Run is just told to
//     pull whatever digest :${stage} currently resolves to in AR. To get
//     new mineru bytes into staging/prod, a human runs `sst deploy
//     --stage staging` (or prod) from their machine; the subsequent CI
//     run on merge just re-applies infra.
//
// Cloud Run pulls the resulting reference (digest-pinned locally,
// tag-pinned in CI) on port 30000 with one GPU.

import * as path from "node:path";

import { dataBucket } from "./blob-storage.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);

const region = "us-central1";
const project = gcp.config.project!;

const imageTag = $interpolate`${region}-docker.pkg.dev/${project}/td-mineru/mineru:${$app.stage}`;
const cacheTag = $interpolate`${region}-docker.pkg.dev/${project}/td-mineru/mineru:cache`;

// GHA sets CI=true; locally it's unset. See deploy-model comment at the top
// for why we skip the build in CI.
const isCi = !!process.env.CI;

const mineruImageRef = isCi
	? imageTag
	: new dockerbuild.Image("mineru-image", {
			tags: [imageTag],
			context: { location: path.resolve("apps/mineru") },
			platforms: ["linux/amd64"],
			push: true,
			cacheFrom: [{ registry: { ref: cacheTag } }],
			cacheTo: [
				{ registry: { ref: cacheTag, mode: "max", imageManifest: true } },
			],
			load: false,
		}).ref;

const mineruSa = new gcp.serviceaccount.Account("mineru-sa", {
	accountId: `td-${$app.stage}-mineru-sa`,
	displayName: `MinerU Cloud Run runtime (${$app.stage})`,
});

// Mineru now owns the parse pipeline, including writing extracted images
// directly to GCS — needs object create/delete, not just read.
new gcp.storage.BucketIAMMember("mineru-bucket-writer", {
	bucket: dataBucket.name,
	role: "roles/storage.objectAdmin",
	member: $interpolate`serviceAccount:${mineruSa.email}`,
});

// Mineru's title-aided post-processing calls Vertex Gemini directly; mirrors
// the `api-vertex-user` grant in infra/cpu.ts.
new gcp.projects.IAMMember("mineru-vertex-user", {
	project,
	role: "roles/aiplatform.user",
	member: $interpolate`serviceAccount:${mineruSa.email}`,
});

export const mineruService = new gcp.cloudrunv2.Service("mineru", {
	name: `td-${$app.stage}-mineru`,
	location: region,
	ingress: "INGRESS_TRAFFIC_ALL",
	deletionProtection: isProtectedStage,
	template: {
		serviceAccount: mineruSa.email,
		timeout: "3600s",
		maxInstanceRequestConcurrency: 1,
		scaling: { maxInstanceCount: 3 },
		nodeSelector: { accelerator: "nvidia-rtx-pro-6000" }, // RTX PRO 6000 Blackwell, CUDA 13.0
		gpuZonalRedundancyDisabled: true,
		containers: [
			{
				image: mineruImageRef,
				ports: { containerPort: 30000 },
				resources: {
					limits: {
						cpu: "20",
						memory: "80Gi",
						"nvidia.com/gpu": "1",
					},
					startupCpuBoost: true,
				},
				envs: [
					{ name: "STAGE", value: $app.stage },
					{ name: "PROJECT_ID", value: project },
					{ name: "DATA_BUCKET", value: dataBucket.name },
				],
				// 90 * 10s = 15 min ceiling for VLM preload + vllm compile.
				startupProbe: {
					httpGet: { path: "/health", port: 30000 },
					initialDelaySeconds: 30,
					periodSeconds: 10,
					timeoutSeconds: 5,
					failureThreshold: 90,
				},
			},
		],
	},
});

export const mineruServiceUrl = mineruService.uri;

// mineru can't run locally (no NVIDIA GPU on dev machines), so the
// "Mineru" pane just tails the deployed service's logs via Cloud Logging's
// streaming tail API. `gcloud beta run services logs tail` doesn't exist —
// only `read`. Use `gcloud beta logging tail` with a resource filter.
new sst.x.DevCommand("Mineru", {
	dev: {
		command: $interpolate`gcloud beta logging tail 'resource.type="cloud_run_revision" AND resource.labels.service_name="td-${$app.stage}-mineru"' --project=${project} --format='value(timestamp,textPayload)'`,
		autostart: true,
	},
});
