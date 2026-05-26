/// <reference path="../.sst/platform/config.d.ts" />

import * as path from "node:path";

import { enabledServices } from "./project-services.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);
const region = "us-central1";
const project = gcp.config.project!;

const registry = new gcp.artifactregistry.Repository(
	"web-router-images",
	{
		repositoryId: `td-${$app.stage}-web-router`,
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

const imageTag = $interpolate`${region}-docker.pkg.dev/${project}/${registry.repositoryId}/web-router:latest`;
const cacheTag = $interpolate`${region}-docker.pkg.dev/${project}/${registry.repositoryId}/web-router:cache`;

const webRouterImage = new dockerbuild.Image("web-router-image", {
	tags: [imageTag],
	context: { location: path.resolve("apps/web-router") },
	platforms: ["linux/amd64"],
	push: true,
	cacheFrom: [{ registry: { ref: cacheTag } }],
	cacheTo: [{ registry: { ref: cacheTag, mode: "max", imageManifest: true } }],
	load: false,
});

const webRouterSa = new gcp.serviceaccount.Account("web-router-sa", {
	accountId: `td-${$app.stage}-web-router-sa`,
	displayName: `Web router Cloud Run runtime (${$app.stage})`,
});

export const webRouterService = new gcp.cloudrunv2.Service("web-router", {
	name: `td-${$app.stage}-web-router`,
	location: region,
	ingress: "INGRESS_TRAFFIC_ALL",
	deletionProtection: isProtectedStage,
	template: {
		serviceAccount: webRouterSa.email,
		containers: [
			{
				image: webRouterImage.ref,
				ports: { containerPort: 8080 },
				resources: {
					limits: { cpu: "1", memory: "256Mi" },
				},
				envs: [{ name: "BUCKET", value: `td-${$app.stage}-web` }],
			},
		],
	},
});

new gcp.cloudrunv2.ServiceIamMember("web-router-public", {
	name: webRouterService.name,
	location: webRouterService.location,
	role: "roles/run.invoker",
	member: "allUsers",
});
