/// <reference path="./.sst/platform/config.d.ts" />

// Cloud Tasks queue for async title processing.
//
// `POST /titles` enqueues a task here; Cloud Tasks dispatches an HTTP POST
// (with an OIDC token signed by api-sa) to `${apiServiceUrl}/titles/process`
// — same Cloud Run service, worker endpoint.

import { apiSa } from "./cpu.js";
import { enabledServices } from "./project-services.js";

const project = gcp.config.project!;

export const titleProcessingQueue = new gcp.cloudtasks.Queue(
	"title-processing",
	{
		name: `td-${$app.stage}-title-processing`,
		location: "us-central1",
		rateLimits: {
			maxConcurrentDispatches: 10,
			maxDispatchesPerSecond: 5,
		},
		retryConfig: {
			maxAttempts: 3,
			minBackoff: "30s",
			maxBackoff: "300s",
		},
	},
	{ dependsOn: enabledServices },
);

// api-sa needs to enqueue tasks into the queue.
new gcp.projects.IAMMember("api-cloudtasks-enqueuer", {
	project,
	role: "roles/cloudtasks.enqueuer",
	member: $interpolate`serviceAccount:${apiSa.email}`,
});

// api-sa needs to act as itself when Cloud Tasks mints the OIDC token used
// to call /titles/process. This is the same `roles/iam.serviceAccountUser`
// grant pattern Google requires for HTTP-target tasks with OIDC auth.
new gcp.serviceaccount.IAMMember("api-sa-cloudtasks-actas", {
	serviceAccountId: apiSa.name,
	role: "roles/iam.serviceAccountUser",
	member: $interpolate`serviceAccount:${apiSa.email}`,
});
