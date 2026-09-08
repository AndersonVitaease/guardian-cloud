import { test } from "node:test";
import assert from "node:assert/strict";
import { runApplicationDomain, APPLICATION_DOMAIN_READ_PRIMITIVES } from "../src/applicationDomain.ts";
import type { VpsTransport, VpsTransportCall, VpsTransportResponse } from "../src/vpsTransport.ts";

// GCLOUD-01B — engineering "application-domain" READ-ONLY primitive tests.
// All tests use a FAKE transport: no network, no LLM, no SSH/shell, no real
// Dokploy calls, zero mutation. Fake values are obviously synthetic. Transport
// types are imported from the proven contract in ../src/vpsTransport.ts.

type Handler = (args: Record<string, unknown>) => unknown;

function fakeTransport(options: { handlers?: Record<string, Handler>; failFor?: string[]; log: VpsTransportCall[] }): VpsTransport {
  return {
    name: "fake",
    async call(request: VpsTransportCall): Promise<VpsTransportResponse> {
      options.log.push(request);
      if (options.failFor?.includes(request.toolName)) {
        return { ok: false, status: 502, error: `FAKE_UPSTREAM_FAILURE:${request.toolName}`, durationMs: 1 };
      }
      const handler = options.handlers?.[request.toolName];
      if (!handler) return { ok: false, status: 0, error: `FAKE_NO_HANDLER:${request.toolName}`, durationMs: 1 };
      return { ok: true, status: 200, result: handler(request.arguments), durationMs: 1 };
    },
  };
}

const APP_WITH_HTTPS_DOMAIN = {
  applicationId: "app-1",
  name: "my-app",
  applicationStatus: "running",
  domain: [{ host: "my-app.example.com", https: true, certificateType: "letsencrypt", domainType: "application" }],
};

const APP_WITHOUT_DOMAIN = { applicationId: "app-1", name: "my-app", applicationStatus: "running" };

test("01 missing applicationId is rejected BEFORE any transport call", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runApplicationDomain({}, { transport: fakeTransport({ log }) });
  assert.equal(result.ok, false);
  assert.equal(result.status, "NEEDS_INPUT");
  assert.deepEqual(result.missing, ["applicationId"]);
  assert.equal(log.length, 0);
  assert.equal(result.mutated, false);
  assert.equal(result.url, null);
});

test("02 existing application with HTTPS domain -> READY with evidenced URL", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runApplicationDomain({ applicationId: "app-1" }, {
    transport: fakeTransport({ handlers: { "application-one": () => APP_WITH_HTTPS_DOMAIN }, log }),
  });
  assert.equal(result.ok, true);
  assert.equal(result.status, "READY");
  assert.equal(result.applicationId, "app-1");
  assert.equal(result.domain, "my-app.example.com");
  assert.equal(result.url, "https://my-app.example.com");
  assert.equal(result.https, true);
  assert.equal(log.length, 1);
  assert.equal(log[0].toolName, "application-one");
  assert.equal(log[0].mutating, false);
  assert.deepEqual(log[0].arguments, { applicationId: "app-1" });
  assert.equal(result.guardianGate.includes("GUARDIAN_GATED=NO"), true);
});

test("03 nonexistent application -> NOT_FOUND, no invented domain or URL", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runApplicationDomain({ applicationId: "missing-app" }, {
    transport: fakeTransport({ handlers: { "application-one": () => ({ success: false, message: "Application not found" }) }, log }),
  });
  assert.equal(result.ok, true);
  assert.equal(result.status, "NOT_FOUND");
  assert.equal(result.domain, null);
  assert.equal(result.url, null);
  assert.equal(result.https, null);
  assert.equal(result.mutated, false);
  assert.equal(log.length, 1);
});

test("04 application without domain -> DOMAIN_PENDING; unrecognizable payload -> UNKNOWN", async () => {
  const log: VpsTransportCall[] = [];
  const pending = await runApplicationDomain({ applicationId: "app-1" }, {
    transport: fakeTransport({ handlers: { "application-one": () => APP_WITHOUT_DOMAIN }, log }),
  });
  assert.equal(pending.ok, true);
  assert.equal(pending.status, "DOMAIN_PENDING");
  assert.equal(pending.domain, null);
  assert.equal(pending.url, null);
  assert.equal(pending.https, null);
  const unknown = await runApplicationDomain({ applicationId: "app-1" }, {
    transport: fakeTransport({ handlers: { "application-one": () => "plain-text-body" }, log }),
  });
  assert.equal(unknown.ok, false);
  assert.equal(unknown.status, "UNKNOWN");
  assert.equal(unknown.url, null);
});

test("05 upstream failure is preserved honestly", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runApplicationDomain({ applicationId: "app-1" }, {
    transport: fakeTransport({ failFor: ["application-one"], log }),
  });
  assert.equal(result.ok, false);
  assert.equal(result.status, "UPSTREAM_ERROR");
  assert.equal(result.response?.status, 502);
  assert.equal(result.response?.error, "FAKE_UPSTREAM_FAILURE:application-one");
  assert.equal(result.domain, null);
  assert.equal(result.url, null);
  assert.equal(result.mutated, false);
  assert.equal(log.length, 1);
});

test("06 zero mutating calls: every call is read-only and allowlisted; multi-domain primary only with evidence", async () => {
  const log: VpsTransportCall[] = [];
  const multi = await runApplicationDomain({ applicationId: "app-1" }, {
    transport: fakeTransport({
      handlers: {
        "application-one": () => ({
          applicationId: "app-1",
          name: "my-app",
          domain: [
            { host: "one.example.com", https: true, domainType: "application" },
            { host: "two.example.com", https: false, domainType: "application" },
            { host: "preview-abc.example.com", https: true, domainType: "preview" },
          ],
        }),
      },
      log,
    }),
  });
  // Two domainType 'application' entries and no single evidenced primary -> AMBIGUOUS list, no arbitrary choice.
  assert.equal(multi.status, "AMBIGUOUS");
  assert.equal(multi.domain, null);
  assert.equal(multi.url, null);
  assert.equal(multi.domains.length, 3);

  const ready = await runApplicationDomain({ applicationId: "app-1" }, {
    transport: fakeTransport({
      handlers: {
        "application-one": () => ({
          applicationId: "app-1",
          name: "my-app",
          domain: [
            { host: "one.example.com", https: true, domainType: "application" },
            { host: "p.example.com", https: true, domainType: "preview" },
          ],
        }),
      },
      log,
    }),
  });
  // Exactly one domainType 'application' -> evidenced primary.
  assert.equal(ready.status, "READY");
  assert.equal(ready.domain, "one.example.com");
  assert.equal(ready.url, "https://one.example.com");
  assert.equal(ready.https, true);
  assert.equal(typeof ready.primaryEvidence === "string" && ready.primaryEvidence.length > 0, true);

  for (const call of log) {
    assert.equal(call.mutating, false, `mutating call detected: ${call.toolName}`);
    assert.ok((APPLICATION_DOMAIN_READ_PRIMITIVES as readonly string[]).includes(call.toolName), `non-allowlisted primitive: ${call.toolName}`);
    assert.equal(call.confirmation.toolName, call.toolName);
  }
  assert.equal(multi.mutated, false);
  assert.equal(ready.mutated, false);
});
