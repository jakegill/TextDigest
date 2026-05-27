/// <reference path="./.sst/platform/config.d.ts" />

// SST top-level configuration for text-digest.

// Per-resource files live in infra/:
//   - infra/auth.ts          — Identity Platform
//   - infra/nosql.ts         — Firestore Native
//   - infra/blob-storage.ts  — Cloud Storage bucket
//   - infra/cpu.ts           — Cloud Run + Artifact Registry (api)
//   - infra/api-gateway.ts   — GCP API Gateway
//   - infra/cdn.ts           — GCS web bucket + Cloud CDN
//   - infra/gpu.ts           — Cloud Run on L4, inference
//   - infra/cicd-trigger.ts  — Cloud Build Triggers (per protected stage)

export default $config({
	app(input) {
		const stage = input?.stage ?? "";

		const isProtected = ["staging", "prod"].includes(stage);

		return {
			name: "td",
			removal: isProtected ? "retain" : "remove",
			home: "aws",
			providers: {
				aws: {
					version: "7.30.0",
					region: "us-east-1",
				},
				gcp: {
					version: "9.25.0",
					project: "text-digest-497216",
					region: "us-central1",
				},
				"docker-build": "0.0.17",
				command: "1.2.1",
			},
		};
	},
	async run() {
		const isProtected = ["staging", "prod"].includes($app.stage);

		console.log("Running app.stage=", $app.stage, " command=", $cli.command);

		const isWriteCommand = ["deploy", "dev", "refresh", "remove"].includes($cli.command);

		if (isProtected && isWriteCommand) {
			throw new Error(
				`Stage "${$app.stage}" can only be deployed from CI to avoid destructive changes. ` +
					`Use a personal stage (e.g., pnpm dev <initials>) for local development`,
			);
		}

		await import("./infra/project-services.js");
		await import("./infra/aws-deploy-role.js");

		await import("./infra/auth.js");
		const storage = await import("./infra/blob-storage.js");
		const nosql = await import("./infra/nosql.js");
		const gpu = await import("./infra/gpu.js");
		const cpu = await import("./infra/cpu.js");
		await import("./infra/queue.js");
		const gateway = await import("./infra/api-gateway.js");
		await import("./infra/proxy.js");
		const cdn = await import("./infra/cdn.js");
		await import("./infra/cicd-trigger.js");

		return {
			dataBucket: storage.dataBucket.name,
			firestoreDb: nosql.firestoreDb.name,
			apiServiceUrl: cpu.apiServiceUrl,
			mineruServiceUrl: gpu.mineruServiceUrl,
			apiGatewayUrl: gateway.apiGatewayUrl,
			appUrl: cdn.appUrl,
		};
	},
});
