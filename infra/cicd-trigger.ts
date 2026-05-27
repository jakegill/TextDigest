/// <reference path="../.sst/platform/config.d.ts" />

// Cloud Build Triggers — ci/cloudbuild/deploy.yml on git push to its stage's branch.

import { awsAccountId, awsDeployRoleArn } from "./aws-deploy-role.js";

const project = gcp.config.project!;

const region = "us-central1";

if ($app.stage === "staging") {
	for (const stage of ["staging", "prod"] as const) {
		new gcp.cloudbuild.Trigger(`${stage}-deploy-trigger`, {
			name: `td-${stage}-deploy`,
			location: region,
			serviceAccount: `projects/${project}/serviceAccounts/github-actions-cicd@${project}.iam.gserviceaccount.com`,
			github: {
				owner: "jakegill",
				name: "TextDigest",
				push: { branch: `^${stage}$` },
			},
			filename: "ci/cloudbuild/deploy.yml",
			substitutions: {
				_STAGE: stage,
				_AWS_ACCOUNT_ID: awsAccountId,
				_AWS_ROLE_ARN: awsDeployRoleArn,
			},
			includeBuildLogs: "INCLUDE_BUILD_LOGS_WITH_STATUS",
		});
	}
}
