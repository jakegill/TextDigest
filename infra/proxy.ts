/// <reference path="../.sst/platform/config.d.ts" />

import * as path from "node:path";

import { enabledServices } from "./project-services.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);
const region = "us-central1";
const project = gcp.config.project!;
const inCi = !!process.env.BUILD_ID;

const registry = new gcp.artifactregistry.Repository(
	"proxy-images",
	{
		repositoryId: `td-${$app.stage}-proxy`,
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

const imageTag = $interpolate`${region}-docker.pkg.dev/${project}/${registry.repositoryId}/proxy:latest`;
const cacheTag = $interpolate`${region}-docker.pkg.dev/${project}/${registry.repositoryId}/proxy:cache`;

const proxyImageRef = inCi
	? $interpolate`${region}-docker.pkg.dev/${project}/${registry.repositoryId}/proxy@${process.env.PROXY_IMAGE_DIGEST!}`
	: new dockerbuild.Image(
			"proxy-image",
			{
				tags: [imageTag],
				context: { location: path.resolve("apps/proxy") },
				platforms: ["linux/amd64"],
				push: true,
				cacheFrom: [{ registry: { ref: cacheTag } }],
				cacheTo: [
					{ registry: { ref: cacheTag, mode: "max", imageManifest: true } },
				],
				load: false,
			},
			{ dependsOn: [registry] },
		).ref;

const proxySa = new gcp.serviceaccount.Account("proxy-sa", {
	accountId: `td-${$app.stage}-proxy-sa`,
	displayName: `Proxy Cloud Run runtime (${$app.stage})`,
});

export const proxyService = new gcp.cloudrunv2.Service("proxy", {
	name: `td-${$app.stage}-proxy`,
	location: region,
	ingress: "INGRESS_TRAFFIC_ALL",
	deletionProtection: isProtectedStage,
	template: {
		serviceAccount: proxySa.email,
		containers: [
			{
				image: proxyImageRef,
				ports: { containerPort: 8080 },
				resources: {
					limits: { cpu: "1", memory: "256Mi" },
					cpuIdle: true,
				},
				envs: [{ name: "BUCKET", value: `td-${$app.stage}-web` }],
			},
		],
	},
});

new gcp.cloudrunv2.ServiceIamMember("proxy-public", {
	name: proxyService.name,
	location: proxyService.location,
	role: "roles/run.invoker",
	member: "allUsers",
});
