/// <reference path="./.sst/platform/config.d.ts" />

// Cloud Run v2 service for apps/mineru (MinerU 3.1.x on NVIDIA L4).
//
// Pipeline:
//   1. Artifact Registry repo (per stage) holds the mineru image.
//   2. docker-build provider builds apps/mineru/ and pushes it. First
//      build is slow because ~5–6 GB of VLM weights are baked in.
//   3. Cloud Run v2 runs the pushed image on port 30000 with one L4 GPU.

import * as path from "node:path";

import { dataBucket } from "./blob-storage.js";
import { enabledServices } from "./project-services.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);

const region = "us-central1";
const project = gcp.config.project!;

const registry = new gcp.artifactregistry.Repository(
	"mineru-images",
	{
		repositoryId: `td-${$app.stage}-mineru`,
		location: region,
		format: "DOCKER",
		cleanupPolicies: isProtectedStage
			? undefined
			: [
					{
						id: "keep-latest-3",
						action: "KEEP",
						mostRecentVersions: { keepCount: 3 },
					},
				],
	},
	{ dependsOn: enabledServices },
);

const imageTag = $interpolate`${region}-docker.pkg.dev/${project}/${registry.repositoryId}/mineru:latest`;
const cacheTag = $interpolate`${region}-docker.pkg.dev/${project}/${registry.repositoryId}/mineru:cache`;

const mineruImage = new dockerbuild.Image("mineru-image", {
	tags: [imageTag],
	context: { location: path.resolve("apps/mineru") },
	platforms: ["linux/amd64"],
	push: true,
	// Critical for mineru: the 5-6 GB model-download layer gets cached in
	// Artifact Registry, so subsequent builds skip re-downloading it.
	cacheFrom: [{ registry: { ref: cacheTag } }],
	cacheTo: [{ registry: { ref: cacheTag, mode: "max", imageManifest: true } }],
	// Don't load into local Docker — the image lives in Artifact Registry.
	load: false,
});

const mineruSa = new gcp.serviceaccount.Account("mineru-sa", {
	accountId: `td-${$app.stage}-mineru-sa`,
	displayName: `MinerU Cloud Run runtime (${$app.stage})`,
});

new gcp.storage.BucketIAMMember("mineru-bucket-reader", {
	bucket: dataBucket.name,
	role: "roles/storage.objectViewer",
	member: $interpolate`serviceAccount:${mineruSa.email}`,
});

export const mineruService = new gcp.cloudrunv2.Service("mineru", {
	name: `td-${$app.stage}-mineru`,
	location: region,
	ingress: "INGRESS_TRAFFIC_ALL",
	template: {
		serviceAccount: mineruSa.email,
		timeout: "3600s",
		maxInstanceRequestConcurrency: 1,
		scaling: { maxInstanceCount: 3 },
		nodeSelector: { accelerator: "nvidia-rtx-pro-6000" }, // RTX PRO 6000 Blackwell, CUDA 13.0
		gpuZonalRedundancyDisabled: true,
		containers: [
			{
				image: mineruImage.ref,
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
