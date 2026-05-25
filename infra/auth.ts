/// <reference path="./.sst/platform/config.d.ts" />

// Firebase Auth — Google sign-in is enabled via the Firebase console toggle

// `gcp.firebase.WebApp` is a client-config registration, NOT a deployed app —
// its only output is the apiKey + authDomain the Firebase SDK needs.

import { enabledServices } from "./project-services.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);

const firebaseProject = new gcp.firebase.Project("firebase", {}, { dependsOn: enabledServices });

const webApp = new gcp.firebase.WebApp(
	"web-app",
	{
		displayName: `td-${$app.stage}`,
		deletionPolicy: isProtectedStage ? "ABANDON" : "DELETE",
	},
	{ dependsOn: [firebaseProject] },
);

export const webAppConfig = gcp.firebase.getWebAppConfigOutput({
	webAppId: webApp.appId,
});
