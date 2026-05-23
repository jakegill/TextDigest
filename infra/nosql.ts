/// <reference path="./.sst/platform/config.d.ts" />

// Per-stage Firestore database. The shared dev project hosts every personal
// stage as a separately-named DB.
//
// Name constraints: lowercase, 4-63 chars, [a-z0-9-], no leading/trailing hyphen.

import { enabledServices } from "./project-services.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);

export const firestoreDb = new gcp.firestore.Database(
	"user-data",
	{
		name: `td-${$app.stage}`,
		locationId: "us-east1",
		type: "FIRESTORE_NATIVE",
		// ABANDON keeps protected-stage data intact on `sst remove`. DELETE
		// frees dev resources so per-dev cleanup actually works.
		deletionPolicy: isProtectedStage ? "ABANDON" : "DELETE",
	},
	{ dependsOn: enabledServices },
);
