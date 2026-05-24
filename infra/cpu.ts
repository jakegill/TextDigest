/// <reference path="./.sst/platform/config.d.ts" />

// Cloud Run v2 service for apps/api (FastAPI).
//
// Pipeline:
//   1. Artifact Registry repo (per stage) holds the api image.
//   2. docker-build provider builds apps/api/ and pushes it.
//   3. Cloud Run v2 runs the pushed image on port 8080 for Fast API.

import * as path from "node:path";

import { dataBucket } from "./blob-storage.js";
import { mineruService, mineruServiceUrl } from "./gpu.js";
import { enabledServices } from "./project-services.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);

const region = "us-central1";
const project = gcp.config.project!;

const registry = new gcp.artifactregistry.Repository(
	"api-images",
	{
		repositoryId: `td-${$app.stage}-api`,
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

const imageTag = $interpolate`${region}-docker.pkg.dev/${project}/${registry.repositoryId}/api:latest`;
const cacheTag = $interpolate`${region}-docker.pkg.dev/${project}/${registry.repositoryId}/api:cache`;

const apiImage = new dockerbuild.Image("api-image", {
	tags: [imageTag],
	context: { location: path.resolve("apps/api") },
	platforms: ["linux/amd64"],
	push: true,
	cacheFrom: [{ registry: { ref: cacheTag } }],
	cacheTo: [{ registry: { ref: cacheTag, mode: "max", imageManifest: true } }],
	load: false,
});

const apiSa = new gcp.serviceaccount.Account("api-sa", {
	accountId: `td-${$app.stage}-api-sa`,
	displayName: `API Cloud Run runtime (${$app.stage})`,
});

new gcp.storage.BucketIAMMember("api-bucket-writer", {
	bucket: dataBucket.name,
	role: "roles/storage.objectAdmin",
	member: $interpolate`serviceAccount:${apiSa.email}`,
});

new gcp.cloudrunv2.ServiceIamMember("api-invokes-mineru", {
	name: mineruService.name,
	location: mineruService.location,
	role: "roles/run.invoker",
	member: $interpolate`serviceAccount:${apiSa.email}`,
});

new gcp.projects.IAMMember("api-vertex-user", {
	project,
	role: "roles/aiplatform.user",
	member: $interpolate`serviceAccount:${apiSa.email}`,
});

new gcp.projects.IAMMember("api-firestore-user", {
	project,
	role: "roles/datastore.user",
	member: $interpolate`serviceAccount:${apiSa.email}`,
});

// v4 signed URLs require the signer to mint tokens on its own behalf
new gcp.serviceaccount.IAMMember("api-sa-self-sign", {
	serviceAccountId: apiSa.name,
	role: "roles/iam.serviceAccountTokenCreator",
	member: $interpolate`serviceAccount:${apiSa.email}`,
});

// Running server locally requires impersonating api-sa to mint OIDC
if (!isProtectedStage && process.env.DEV_USER_EMAIL) {
	new gcp.serviceaccount.IAMMember("api-sa-dev-impersonate", {
		serviceAccountId: apiSa.name,
		role: "roles/iam.serviceAccountTokenCreator",
		member: `user:${process.env.DEV_USER_EMAIL}`,
	});
}

export const apiService = new gcp.cloudrunv2.Service("api", {
	name: `td-${$app.stage}-api`,
	location: region,
	ingress: "INGRESS_TRAFFIC_ALL",
	deletionProtection: isProtectedStage,
	template: {
		serviceAccount: apiSa.email,
		containers: [
			{
				image: apiImage.ref,
				ports: { containerPort: 8080 },
				resources: {
					limits: {
						cpu: "4",
						memory: "8Gi",
					},
					startupCpuBoost: true,
				},
				envs: [
					{ name: "STAGE", value: $app.stage },
					{ name: "PROJECT_ID", value: project },
					{ name: "MINERU_URL", value: mineruServiceUrl },
					{ name: "DATA_BUCKET", value: dataBucket.name },
					{ name: "MINERU_TOOLS_CONFIG_JSON", value: "/tmp/mineru-api.json" },
				],
				startupProbe: {
					httpGet: { path: "/health", port: 8080 },
					initialDelaySeconds: 10,
					periodSeconds: 5,
					timeoutSeconds: 3,
					failureThreshold: 60,
				},
			},
		],
	},
});

// Public invocation — the gateway sits in front and does its own auth.
new gcp.cloudrunv2.ServiceIamMember("api-public", {
	name: apiService.name,
	location: apiService.location,
	role: "roles/run.invoker",
	member: "allUsers",
});

export const apiServiceUrl = apiService.uri;

// Local dev — runs uvicorn in a multiplexer pane during `sst dev`.
new sst.x.DevCommand("Api", {
	dev: {
		command: "pnpm dev",
		directory: "apps/api",
		autostart: true,
	},
	environment: {
		STAGE: $app.stage,
		MINERU_URL: mineruServiceUrl,
		DATA_BUCKET: dataBucket.name,
		GOOGLE_CLOUD_PROJECT: project,
		GOOGLE_APPLICATION_CREDENTIALS: process.env.DEV_ADC_PATH ?? "",
		MINERU_TOOLS_CONFIG_JSON: "/tmp/mineru-api.json",
	},
});
