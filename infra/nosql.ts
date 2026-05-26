/// <reference path="../.sst/platform/config.d.ts" />

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

// COLLECTION scope (not COLLECTION_GROUP): every find_nearest in the
// codebase walks down `users/{uid}/titles/{titleId}/chunks` and queries
// that specific subcollection. A single COLLECTION-scoped index on the
// "chunks" collection ID applies to every such subcollection across all
// parents. COLLECTION_GROUP would only serve `db.collection_group("chunks")`
// queries, which we don't make.
new gcp.firestore.Index(
	"chunks-embedding",
	{
		database: firestoreDb.name,
		collection: "chunks",
		queryScope: "COLLECTION",
		apiScope: "ANY_API",
		fields: [
			{ fieldPath: "__name__", order: "ASCENDING" },
			{ fieldPath: "embedding", vectorConfig: { dimension: 768, flat: {} } },
		],
	},
	{ dependsOn: [firestoreDb] },
);
