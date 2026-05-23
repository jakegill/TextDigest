/// <reference path="./.sst/platform/config.d.ts" />

// Cloud Run v2 service for apps/api (FastAPI).
//
// Pipeline:
//   1. Artifact Registry repo (per stage) holds the api image.
//   2. docker-build provider builds apps/api/ and pushes it.
//   3. Cloud Run v2 runs the pushed image on port 8080.

import * as path from "node:path";

import { enabledServices } from "./project-services.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);

const region = "us-east1";
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

const apiImage = new dockerbuild.Image("api-image", {
	tags: [imageTag],
	context: { location: path.resolve("apps/api") },
	platforms: ["linux/amd64"],
	push: true,
});

export const apiService = new gcp.cloudrunv2.Service("api", {
	name: `td-${$app.stage}-api`,
	location: region,
	ingress: "INGRESS_TRAFFIC_ALL",
	template: {
		containers: [
			{
				image: apiImage.ref,
				ports: { containerPort: 8080 },
				envs: [
					{ name: "STAGE", value: $app.stage },
					{ name: "PROJECT_ID", value: project },
				],
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

// Local dev — runs uvicorn in a multiplexer pane during `sst dev`. No-op on deploy.
new sst.x.DevCommand("Api", {
	dev: {
		command: "pnpm dev",
		directory: "apps/api",
		autostart: true,
	},
});
