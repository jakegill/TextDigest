/// <reference path="../.sst/platform/config.d.ts" />

import { enabledServices } from "./project-services.js";

const region = "us-central1";
const project = gcp.config.project!;

if ($app.stage === "staging") {
	new gcp.cloudbuild.WorkerPool(
		"cicd-worker",
		{
			name: "td-cicd-worker",
			location: region,
			workerConfig: { machineType: "e2-standard-32", diskSizeGb: 200 },
		},
		{ dependsOn: enabledServices },
	);
}

export const cicdWorkerPoolId = `projects/${project}/locations/${region}/workerPools/td-cicd-worker`;
export const inCi = !!process.env.BUILD_ID;
