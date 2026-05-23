/// <reference path="./.sst/platform/config.d.ts" />

// Static frontend for apps/app — GCS bucket fronted by a global HTTPS load
// balancer with Cloud CDN.
//
// `apps/app` builds with `output: "export"` into out/. Uploading out/ to
// webBucket is NOT done here — only the bucket + LB/CDN path are stood up.

import { webAppConfig } from "./auth.js";
import { enabledServices } from "./project-services.js";

const isProtectedStage = ["staging", "prod"].includes($app.stage);

const webBucket = new gcp.storage.Bucket(
	"web",
	{
		name: `td-${$app.stage}-web`,
		location: "US",
		uniformBucketLevelAccess: true,
		forceDestroy: !isProtectedStage,
		website: {
			mainPageSuffix: "index.html",
			notFoundPage: "404.html",
		},
	},
	{ dependsOn: enabledServices },
);

// Public read at the bucket level — the CDN serves the same content, but
// direct bucket reads also need to work for the LB backend.
new gcp.storage.BucketIAMMember("web-public", {
	bucket: webBucket.name,
	role: "roles/storage.objectViewer",
	member: "allUsers",
});

const backendBucket = new gcp.compute.BackendBucket("web-backend", {
	name: `td-${$app.stage}-web-backend`,
	bucketName: webBucket.name,
	enableCdn: true,
});

const urlMap = new gcp.compute.URLMap("web-urlmap", {
	name: `td-${$app.stage}-web-urlmap`,
	defaultService: backendBucket.id,
});

// Plain HTTP only. HTTPS requires a managed cert + custom domain.
const httpProxy = new gcp.compute.TargetHttpProxy("web-http-proxy", {
	name: `td-${$app.stage}-web-http`,
	urlMap: urlMap.id,
});

const forwardingRule = new gcp.compute.GlobalForwardingRule("web-fwd", {
	name: `td-${$app.stage}-web-fwd`,
	target: httpProxy.id,
	portRange: "80",
});

export const appUrl = $interpolate`http://${forwardingRule.ipAddress}`;

export { webBucket };

// Local dev — runs next dev in a multiplexer pane during `sst dev`. No-op on deploy.
// Frontend talks to the local uvicorn (from infra/cpu.ts's DevCommand), not the deployed gateway.
new sst.x.DevCommand("WebApp", {
	dev: {
		command: "pnpm dev",
		directory: "apps/app",
		autostart: true,
	},
	environment: {
		NEXT_PUBLIC_API_URL: "http://localhost:8080",
		NEXT_PUBLIC_FIREBASE_API_KEY: webAppConfig.apiKey,
		NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: webAppConfig.authDomain,
		NEXT_PUBLIC_FIREBASE_PROJECT_ID: webAppConfig.projectId,
	},
});
