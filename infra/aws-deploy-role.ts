/// <reference path="../.sst/platform/config.d.ts" />

// All infra is in GCP. SST IaC framework requires storing the state of the infra
// in aws, hence, why we need this role.

const accountId = aws.getCallerIdentityOutput().accountId;
const cicdSa = gcp.serviceaccount.getAccountOutput({
	accountId: "github-actions-cicd",
});

let oidcProviderArn: $util.Output<string>;

let roleArnOut: $util.Output<string>;

if ($app.stage === "staging") {
	const oidcProvider = new aws.iam.OpenIdConnectProvider("google-oidc", {
		url: "https://accounts.google.com",
		clientIdLists: [cicdSa.email, cicdSa.uniqueId],
	});

	const role = new aws.iam.Role("td-deploy-runner", {
		name: "TdDeployRunner",
		assumeRolePolicy: $util.all([oidcProvider.arn, cicdSa.uniqueId]).apply(([providerArn, saUid]) =>
			JSON.stringify({
				Version: "2012-10-17",
				Statement: [
					{
						Effect: "Allow",
						Principal: { Federated: providerArn },
						Action: "sts:AssumeRoleWithWebIdentity",
						Condition: { StringEquals: { "accounts.google.com:sub": saUid } },
					},
				],
			}),
		),
	});

	new aws.iam.RolePolicyAttachment("td-deploy-runner-admin", {
		role: role.name,
		policyArn: "arn:aws:iam::aws:policy/AdministratorAccess",
	});

	oidcProviderArn = oidcProvider.arn;
	roleArnOut = role.arn;
} else {
	oidcProviderArn = accountId.apply((a) => `arn:aws:iam::${a}:oidc-provider/accounts.google.com`);

	roleArnOut = accountId.apply((a) => `arn:aws:iam::${a}:role/TdDeployRunner`);
}

export const awsAccountId = accountId;
export const awsDeployRoleArn = roleArnOut;
export const awsOidcProviderArn = oidcProviderArn;
