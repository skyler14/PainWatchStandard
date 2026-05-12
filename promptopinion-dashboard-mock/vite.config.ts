import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

function promptOpinionAuthzProxy(): Plugin {
  return {
    name: "promptopinion-authz-proxy",
    configureServer(server) {
      const env = loadEnv("", process.cwd(), "");
      server.middlewares.use("/api/promptopinion/authorize-patient-access", (request, response) => {
        if (request.method !== "POST") {
          response.statusCode = 405;
          response.end("Method Not Allowed");
          return;
        }

        let rawBody = "";
        request.on("data", (chunk) => {
          rawBody += chunk.toString();
        });
        request.on("end", async () => {
          const body = JSON.parse(rawBody || "{}");
          const upstreamEndpoint = env.PROMPTOPINION_AUTHZ_ENDPOINT;
          const apiKey = env.PROMPTOPINION_API_KEY;

          if (upstreamEndpoint && apiKey) {
            try {
              const upstreamResponse = await fetch(upstreamEndpoint, {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  Authorization: `Bearer ${apiKey}`,
                },
                body: JSON.stringify(body),
              });
              response.statusCode = upstreamResponse.status;
              response.setHeader("Content-Type", "application/json");
              response.end(await upstreamResponse.text());
              return;
            } catch {
              response.statusCode = 502;
              response.setHeader("Content-Type", "application/json");
              response.end(
                JSON.stringify({
                  allowed: false,
                  reason: "prompt_opinion_authz_proxy_unreachable",
                  requestId: "authz_proxy_502",
                  checkedAt: new Date().toISOString(),
                  source: "prompt_opinion_fhir",
                  fhirPatientId: body.patient_id,
                  policy: "registered_fhir_patient_scope",
                }),
              );
              return;
            }
          }

          const allowed =
            body.clinician_group_id === "grp_doctor_a" && body.patient_id === "pat_test";
          response.statusCode = allowed ? 200 : 403;
          response.setHeader("Content-Type", "application/json");
          response.end(
            JSON.stringify({
              allowed,
              reason: allowed
                ? undefined
                : "permission_denied: clinician group is not assigned to patient pat_test",
              requestId: allowed ? "local_authz_req_a_204" : "local_authz_req_b_403",
              checkedAt: new Date().toISOString(),
              source: "local_mock_fallback",
              fhirPatientId: body.patient_id,
              policy: "registered_fhir_patient_scope",
            }),
          );
        });
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), promptOpinionAuthzProxy()],
});
