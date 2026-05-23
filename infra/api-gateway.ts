/// <reference path="./.sst/platform/config.d.ts" />

// GCP API Gateway in front of the Cloud Run api service.
//
// The gateway reads an OpenAPI 2.0 (Swagger) spec — note: NOT OpenAPI 3.0
// that FastAPI emits natively, so apps/api/openapi.yaml is hand-written and
// kept in sync manually until we add a conversion step.
//
// The spec contains a `BACKEND_URL` placeholder that we substitute with the
// Cloud Run service URL at deploy time, then base64-encode for the
// ApiConfig resource.

import * as fs from "node:fs";
import * as path from "node:path";

import { apiService, apiServiceUrl } from "./cpu.js";
import { enabledServices } from "./project-services.js";

const openapiTemplate = fs.readFileSync(
  path.resolve("apps/api/openapi.yaml"),
  "utf-8",
);

const renderedSpec = apiServiceUrl.apply((url) =>
  Buffer.from(openapiTemplate.replaceAll("BACKEND_URL", url)).toString(
    "base64",
  ),
);

const api = new gcp.apigateway.Api(
  "api",
  {
    apiId: `td-${$app.stage}-api`,
  },
  { dependsOn: enabledServices },
);

const apiConfig = new gcp.apigateway.ApiConfig("api-config", {
  api: api.apiId,
  // ApiConfig resources are immutable — every spec change must produce a
  // new resource. The `prefix` plus stage keeps names unique per deploy.
  apiConfigIdPrefix: `td-${$app.stage}-`,
  openapiDocuments: [
    {
      document: {
        path: "openapi.yaml",
        contents: renderedSpec,
      },
    },
  ],
});

const gateway = new gcp.apigateway.Gateway("api-gateway", {
  gatewayId: `td-${$app.stage}-gateway`,
  apiConfig: apiConfig.id,
  region: "us-central1",
});

export const apiGatewayUrl = $interpolate`https://${gateway.defaultHostname}`;

// Re-export so sst.config.ts wiring stays in one place.
export { apiService };
