/// <reference path="./.sst/platform/config.d.ts" />

// Firestore database.

// Name constraints: lowercase, 4-63 chars, [a-z0-9-], no leading/trailing hyphen.

import { enabledServices } from "./project-services.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);

export const firestoreDb = new gcp.firestore.Database(
	"user-data",
	{
		name: `td-${$app.stage}`,
		locationId: "us-central1",
		type: "FIRESTORE_NATIVE",
		deletionPolicy: isProtectedStage ? "ABANDON" : "DELETE",
	},
	{ dependsOn: enabledServices },
);
