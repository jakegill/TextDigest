/// <reference path="../.sst/platform/config.d.ts" />

import * as path from "node:path";

import { dataBucket } from "./blob-storage.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);

const region = "us-central1";
const project = gcp.config.project!;

const imageTag = `${region}-docker.pkg.dev/${project}/td-mineru/mineru:${$app.stage}`;
const cacheTag = `${region}-docker.pkg.dev/${project}/td-mineru/mineru:cache`;

const mineruImageRef = new dockerbuild.Image("mineru-image", {
	tags: [imageTag],
	context: { location: path.resolve("apps/mineru") },
	platforms: ["linux/amd64"],
	push: true,
	buildArgs: { MINERU_REF: "71fce538546fa6a1e1c93418555099eb5fe82e4c" },
	cacheFrom: [{ registry: { ref: cacheTag } }],
	cacheTo: [{ registry: { ref: cacheTag, mode: "max", imageManifest: true } }],
	load: false,
}).ref;

const mineruSa = new gcp.serviceaccount.Account("mineru-sa", {
	accountId: `td-${$app.stage}-mineru-sa`,
	displayName: `MinerU Cloud Run runtime (${$app.stage})`,
});

new gcp.storage.BucketIAMMember("mineru-bucket-writer", {
	bucket: dataBucket.name,
	role: "roles/storage.objectAdmin",
	member: $interpolate`serviceAccount:${mineruSa.email}`,
});

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
		nodeSelector: { accelerator: "nvidia-rtx-pro-6000" }, // CUDA 13.0
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
