/// <reference path="./.sst/platform/config.d.ts" />

// Enable every GCP API the rest of infra/ depends on.

const APIS = [
	"run.googleapis.com",
	"apigateway.googleapis.com",
	"servicecontrol.googleapis.com",
	"servicemanagement.googleapis.com",
	"artifactregistry.googleapis.com",
	"storage.googleapis.com",
	"compute.googleapis.com",
	"firestore.googleapis.com",
	"iam.googleapis.com",
	"firebase.googleapis.com",
	"identitytoolkit.googleapis.com",
	"aiplatform.googleapis.com",
	"cloudtasks.googleapis.com",
];

export const enabledServices = APIS.map(
	(service) =>
		new gcp.projects.Service(`svc-${service.split(".")[0]}`, {
			service,
			disableOnDestroy: false,
			disableDependentServices: false,
		}),
);
