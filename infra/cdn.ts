/// <reference path="../.sst/platform/config.d.ts" />

// Static frontend for apps/app — GCS bucket fronted by a global HTTPS load
// balancer with Cloud CDN.
//
// `apps/app` builds with `output: "export"` into out/. Uploading out/ to
// webBucket is NOT done here — only the bucket + LB/CDN path are stood up.

import { apiGatewayUrl } from "./api-gateway.js";
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

const deployCmd = [
	"pnpm --filter @td/app build",
	`gcloud storage rsync apps/app/out gs://td-${$app.stage}-web --recursive --delete-unmatched-destination-objects --cache-control='public,max-age=0,s-maxage=31536000,must-revalidate'`,
	`gcloud storage objects update 'gs://td-${$app.stage}-web/_next/static/**' --cache-control='max-age=31536000,public,immutable'`,
	`gcloud compute url-maps invalidate-cdn-cache td-${$app.stage}-web-urlmap --path='/*' --async`,
].join(" && ");

new command.local.Command(
	"WebDeploy",
	{
		create: deployCmd,
		update: deployCmd,
		dir: process.cwd(),
		environment: {
			NEXT_PUBLIC_API_URL: apiGatewayUrl,
			NEXT_PUBLIC_FIREBASE_API_KEY: webAppConfig.apply((c) => c.apiKey ?? ""),
			NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: webAppConfig.apply((c) => c.authDomain ?? ""),
			NEXT_PUBLIC_FIREBASE_PROJECT_ID: webAppConfig.apply((c) => c.project ?? ""),
		},
	},
	{ dependsOn: [webBucket, backendBucket, urlMap, forwardingRule] },
);

// Local dev — runs next dev in a multiplexer pane during `sst dev`. No-op on deploy.
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
		NEXT_PUBLIC_FIREBASE_PROJECT_ID: webAppConfig.project,
	},
});
