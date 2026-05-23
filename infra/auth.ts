/// <reference path="./.sst/platform/config.d.ts" />

// Firebase Auth — Google sign-in is enabled via the Firebase console toggle
// (one-time per project), so no DefaultSupportedIdpConfig resource here.
//
// `gcp.firebase.WebApp` is a client-config registration, NOT a deployed app —
// its only output is the apiKey + authDomain the Firebase SDK needs.

import { enabledServices } from "./project-services.js";

const firebaseProject = new gcp.firebase.Project(
	"firebase",
	{},
	{ dependsOn: enabledServices },
);

const webApp = new gcp.firebase.WebApp(
	"web-app",
	{
		displayName: `td-${$app.stage}`,
		// Without ABANDON, removing the resource deletes the underlying Firebase
		// Web App and breaks any client still using the old apiKey.
		deletionPolicy: "ABANDON",
	},
	{ dependsOn: [firebaseProject] },
);

export const webAppConfig = gcp.firebase.getWebAppConfigOutput({
	webAppId: webApp.appId,
});
