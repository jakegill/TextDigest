/// <reference path="../.sst/platform/config.d.ts" />

import { awsAccountId, awsDeployRoleArn } from "./aws-deploy-role.js";

const project = gcp.config.project!;

const connectionRegion = "us-central1";
const repository = `projects/${project}/locations/${connectionRegion}/connections/jakegill/repositories/jakegill-TextDigest`;

if ($app.stage === "staging") {
	for (const stage of ["staging", "prod"] as const) {
		new gcp.cloudbuild.Trigger(`${stage}-deploy-trigger`, {
			name: `td-${stage}-deploy`,
			location: connectionRegion,
			serviceAccount: `projects/${project}/serviceAccounts/github-actions-cicd@${project}.iam.gserviceaccount.com`,
			repositoryEventConfig: {
				repository,
				push: { branch: `^${stage}$` },
			},
			filename: "ci/cloudbuild/deploy.yml",
			// _STAGE is no longer passed — deploy.yml derives the stage from
			// $BRANCH_NAME so the git ref is the single source of truth.
			substitutions: {
				_AWS_ACCOUNT_ID: awsAccountId,
				_AWS_ROLE_ARN: awsDeployRoleArn,
			},
			includeBuildLogs: "INCLUDE_BUILD_LOGS_WITH_STATUS",
		});
	}
}
