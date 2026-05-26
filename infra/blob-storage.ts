/// <reference path="../.sst/platform/config.d.ts" />

// GCS data-lake bucket. Bucket names are globally unique on GCS, so the
// name is suffixed with `$app.stage`.

import { enabledServices } from "./project-services.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);

export const dataBucket = new gcp.storage.Bucket(
	"data",
	{
		name: `td-${$app.stage}-blobs`,
		location: "US",
		uniformBucketLevelAccess: true,
		forceDestroy: !isProtectedStage,
		cors: [
			{
				origins: ["*"],
				methods: ["GET", "PUT", "POST", "HEAD"],
				responseHeaders: ["*"],
				maxAgeSeconds: 3600,
			},
		],
	},
	{ dependsOn: enabledServices },
);
