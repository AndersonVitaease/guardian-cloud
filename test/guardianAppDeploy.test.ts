import { test } from "node:test";
import assert from "node:assert/strict";
import { runGuardianAppDeploy } from "../src/guardianAppDeploy.ts";
import type { VpsTransport, VpsTransportCall, VpsTransportResponse } from "../src/vpsTransport.ts";
import type { DomainAdapter, GuardianCoreModule, GuardianResult } from "../src/guardianCoreLoad.ts";

// GCLOUD-01D — SuperTool guardian.app.deploy composition tests.
// Fake transport + fake Guardian Core (mirrors the real contract: bind ->
// apply). Zero network, zero production, zero real Dokploy calls.

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

// Mirrors the frozen Guardian Core v0.1.0 observable contract: bind is
// fail-closed; apply is reached ONLY after a BOUND result.
function fakeGuardianCore(): GuardianCoreModule {
  return {
    async executeGuardianIntent<I, B>(intent: I, adapter: DomainAdapter<I, B>): Promise<GuardianResult> {
      const bound = await adapter.bind(intent);
      const record = bound as Record<string, unknown>;
      if (record.outcome === "NOT_EXECUTED") return bound as GuardianResult;
      return adapter.apply(record.proposal as B);
    },
  };
}

const SNAPSHOT = {
  packageJsonText: JSON.stringify({ name: "svc", scripts: { start: "node server.js" } }),
  files: { "server.js": "http.createServer(handler).listen(4100);\n" },
};

const BASE_INPUT = {
  name: "my-app",
  source: "git@example.com:u/my-app.git",
  environmentId: "env-e2e",
  projectSnapshot: SNAPSHOT,
  env: { API_KEY: "sk-super-secret-123" },
};

const HEALTHY_APP_WITH_DOMAIN = {
  applicationId: "app-77",
  applicationStatus: "running",
  domain: [{ host: "my-app.example.com", https: true, certificateType: "letsencrypt", domainType: "application" }],
};

function happyHandlers(overrides: Record<string, Handler> = {}): Record<string, Handler> {
  return {
    "application-search": () => ({ success: true, data: [] }),
    "application-create": () => ({ applicationId: "app-77" }),
    "application-deploy": () => ({ success: true, deployId: "dep-1" }),
    "application-one": () => HEALTHY_APP_WITH_DOMAIN,
    "application-saveGitProvider": () => ({ success: true }),
    "application-saveBuildType": () => ({ success: true }),
    "application-saveEnvironment": () => ({ success: true }),
    ...overrides,
  };
}

test("01 PLAN mode -> PLANNED with zero transport calls and zero mutation", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(BASE_INPUT, { transport: fakeTransport({ log }) });
  assert.equal(result.status, "PLANNED");
  assert.equal(result.ok, true);
  assert.equal(result.mutated, false);
  assert.equal(log.length, 0);
  assert.equal(result.plan?.startCommand, "npm start");
  assert.equal(result.plan?.port, 4100);
  assert.deepEqual(result.plan?.envKeys, ["API_KEY"]);
});

test("02 detector NEEDS_INPUT -> SuperTool stops before any transport call", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    { ...BASE_INPUT, projectSnapshot: { packageJsonText: JSON.stringify({ name: "x", scripts: { build: "tsc" } }) } },
    { transport: fakeTransport({ log }) },
  );
  assert.equal(result.status, "NEEDS_INPUT");
  assert.equal(result.mutated, false);
  assert.equal(log.length, 0);
  assert.ok(result.missing.includes("startCommand"));
  assert.ok(result.missing.includes("port"));
});

test("03 execute=true without approval -> APPROVAL_REQUIRED, zero mutation (Guardian bind refuses)", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy({ ...BASE_INPUT, execute: true }, { transport: fakeTransport({ log }), guardian: fakeGuardianCore() });
  assert.equal(result.status, "APPROVAL_REQUIRED");
  assert.equal(result.mutated, false);
  assert.equal(log.length, 0);
  assert.equal(result.guardian?.outcome, "NOT_EXECUTED");
  assert.ok(result.guardian?.reasons.includes("APPROVAL_GATE_NOT_SATISFIED"));
});

test("04 approval=true -> Guardian permits the mutant path (bind BOUND -> apply EXECUTED)", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    { ...BASE_INPUT, execute: true, approved: true },
    { transport: fakeTransport({ handlers: happyHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.guardian?.outcome, "EXECUTED");
  assert.equal(log.filter((c) => c.toolName === "application-create").length, 1);
  assert.ok(result.mutated);
});

test("05 nominal flow -> application-create dispatched AT MOST once", async () => {
  const log: VpsTransportCall[] = [];
  await runGuardianAppDeploy(
    { ...BASE_INPUT, execute: true, approved: true },
    { transport: fakeTransport({ handlers: happyHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(log.filter((c) => c.toolName === "application-create").length, 1);
  // The rest of the flow is read-only, the allowlisted deploy primitive, or the
  // GCLOUD-01F source-configuration primitives (all allowlisted, all governed).
  assert.ok(log.every((c) => ["application-search", "application-create", "application-saveGitProvider", "application-saveBuildType", "application-saveEnvironment", "application-deploy", "application-one"].includes(c.toolName)));
});

test("06 create failure -> FAILED and deploy never attempted", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    { ...BASE_INPUT, execute: true, approved: true },
    { transport: fakeTransport({ failFor: ["application-create"], handlers: happyHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "FAILED");
  assert.equal(result.create?.response?.error, "FAKE_UPSTREAM_FAILURE:application-create");
  assert.equal(log.filter((c) => c.toolName === "application-deploy").length, 0);
  assert.notEqual(result.status, "LIVE");
});

test("07 deploy failure -> FAILED, LIVE never claimed, upstream error preserved", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    { ...BASE_INPUT, execute: true, approved: true },
    { transport: fakeTransport({ failFor: ["application-deploy"], handlers: happyHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "FAILED");
  assert.equal(result.deploy?.ok, false);
  assert.equal(result.deploy?.error, "FAKE_UPSTREAM_FAILURE:application-deploy");
  assert.notEqual(result.status, "LIVE");
  assert.equal(result.url, null);
});

test("08 health evidence insufficient -> never LIVE", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    { ...BASE_INPUT, execute: true, approved: true },
    {
      transport: fakeTransport({ handlers: happyHandlers({ "application-one": () => ({ applicationId: "app-77", applicationStatus: "installing", domain: HEALTHY_APP_WITH_DOMAIN.domain }) }), log }),
      guardian: fakeGuardianCore(),
    },
  );
  assert.equal(result.status, "DEPLOYING");
  assert.equal(result.health?.healthy, false);
  assert.notEqual(result.status, "LIVE");
  assert.equal(result.url, null);
});

test("09 healthy app with pending domain -> DEPLOYED_AWAITING_DOMAIN, no invented URL", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    { ...BASE_INPUT, execute: true, approved: true },
    {
      transport: fakeTransport({ handlers: happyHandlers({ "application-one": () => ({ applicationId: "app-77", applicationStatus: "running" }) }), log }),
      guardian: fakeGuardianCore(),
    },
  );
  assert.equal(result.status, "DEPLOYED_AWAITING_DOMAIN");
  assert.equal(result.domain?.status, "DOMAIN_PENDING");
  assert.equal(result.url, null);
  assert.notEqual(result.status, "LIVE");
});

test("10 fully evidenced flow -> LIVE with the evidenced URL", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    { ...BASE_INPUT, execute: true, approved: true },
    { transport: fakeTransport({ handlers: happyHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "LIVE");
  assert.equal(result.ok, true);
  assert.equal(result.url, "https://my-app.example.com");
  assert.equal(result.domain?.https, true);
  assert.equal(result.health?.healthy, true);
});

test("11 secrets never appear in plan or output (env values redacted, names only)", async () => {
  const log: VpsTransportCall[] = [];
  const planned = await runGuardianAppDeploy(BASE_INPUT, { transport: fakeTransport({ log }) });
  assert.ok(!JSON.stringify(planned).includes("sk-super-secret-123"));
  assert.deepEqual(planned.plan?.envKeys, ["API_KEY"]);
  const log2: VpsTransportCall[] = [];
  const live = await runGuardianAppDeploy(
    { ...BASE_INPUT, execute: true, approved: true },
    { transport: fakeTransport({ handlers: happyHandlers(), log: log2 }), guardian: fakeGuardianCore() },
  );
  assert.ok(!JSON.stringify(live).includes("sk-super-secret-123"));
});

test("12 revalidation read fails -> fail-closed UNKNOWN with zero mutation, upstream state honest", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    { ...BASE_INPUT, execute: true, approved: true },
    { transport: fakeTransport({ failFor: ["application-search"], log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "UNKNOWN");
  assert.equal(log.filter((c) => c.toolName === "application-create").length, 0);
  assert.equal(result.mutated, false);
  assert.ok(result.guardian?.reasons.includes("REVALIDATION_READ_FAILED"));
});

// ---- GCLOUD-01F: governed provisioning sequence (12 mandated scenarios) ----

// Provisioning-aware happy handlers: empty project/environment lookups (nothing
// exists upstream) plus accepted creates returning real-shaped IDs.
function provisioningHandlers(overrides: Record<string, Handler> = {}): Record<string, Handler> {
  return happyHandlers({
    "project-all": () => ({ success: true, data: [] }),
    "project-create": () => ({ projectId: "proj-1" }),
    "environment-byProjectId": () => ({ success: true, data: [] }),
    "environment-create": () => ({ environmentId: "env-1" }),
    ...overrides,
  });
}

// environmentId ABSENT -> the governed provisioning path resolves it.
const PROVISION_INPUT = {
  name: "provisioned-app",
  source: "https://github.com/AndersonVitaease/guardian-cloud-e2e.git",
  projectSnapshot: SNAPSHOT,
  env: { API_KEY: "sk-super-secret-123" },
  execute: true,
  approved: true,
};

test("13F project existente -> reutilizado (no project-create; reuse reported)", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    PROVISION_INPUT,
    {
      transport: fakeTransport({
        handlers: provisioningHandlers({ "project-all": () => ({ success: true, data: [{ projectId: "proj-x", name: "guardian-cloud" }] }) }),
        log,
      }),
      guardian: fakeGuardianCore(),
    },
  );
  assert.equal(log.filter((c) => c.toolName === "project-create").length, 0);
  assert.equal(result.provisioning?.projectReused, true);
  assert.equal(result.provisioning?.projectId, "proj-x");
});

test("14F environment existente -> reutilizado (no environment-create; reuse reported)", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    PROVISION_INPUT,
    {
      transport: fakeTransport({
        handlers: provisioningHandlers({ "environment-byProjectId": () => ({ success: true, data: [{ environmentId: "env-x", name: "production", projectId: "proj-1" }] }) }),
        log,
      }),
      guardian: fakeGuardianCore(),
    },
  );
  assert.equal(log.filter((c) => c.toolName === "environment-create").length, 0);
  assert.equal(result.provisioning?.environmentReused, true);
  assert.equal(result.provisioning?.environmentId, "env-x");
});

test("15F project/environment ausentes -> cada um criado exatamente uma vez", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(PROVISION_INPUT, { transport: fakeTransport({ handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() });
  assert.equal(log.filter((c) => c.toolName === "project-create").length, 1);
  assert.equal(log.filter((c) => c.toolName === "environment-create").length, 1);
  assert.equal(result.provisioning?.projectReused, false);
  assert.equal(result.provisioning?.environmentReused, false);
  assert.equal(result.provisioning?.projectId, "proj-1");
  assert.equal(result.provisioning?.environmentId, "env-1");
});

test("16F falha project-create -> nada depois (sem environment/application/source/deploy)", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    PROVISION_INPUT,
    { transport: fakeTransport({ failFor: ["project-create"], handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "FAILED");
  assert.equal(log.filter((c) => c.toolName === "environment-byProjectId").length, 0);
  assert.equal(log.filter((c) => c.toolName === "environment-create").length, 0);
  assert.equal(log.filter((c) => c.toolName === "application-create").length, 0);
  assert.equal(log.filter((c) => c.toolName === "application-saveGitProvider").length, 0);
  assert.equal(log.filter((c) => c.toolName === "application-deploy").length, 0);
  assert.equal(result.provisioning?.projectId, null);
  assert.equal(result.mutated, false);
  assert.ok(result.note?.includes("provisioning failed at step=project"));
});

test("17F falha environment-create -> project pode existir (parcial honesto), application NUNCA criada", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    PROVISION_INPUT,
    { transport: fakeTransport({ failFor: ["environment-create"], handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "FAILED");
  assert.equal(result.provisioning?.projectId, "proj-1");
  assert.equal(result.provisioning?.environmentId, null);
  assert.equal(log.filter((c) => c.toolName === "application-create").length, 0);
  assert.equal(log.filter((c) => c.toolName === "application-saveGitProvider").length, 0);
  assert.equal(log.filter((c) => c.toolName === "application-deploy").length, 0);
  assert.equal(result.mutated, true);
});

test("18F falha application-create -> source config e deploy nunca executados", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    PROVISION_INPUT,
    { transport: fakeTransport({ failFor: ["application-create"], handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "FAILED");
  assert.equal(log.filter((c) => c.toolName === "application-saveGitProvider").length, 0);
  assert.equal(log.filter((c) => c.toolName === "application-saveBuildType").length, 0);
  assert.equal(log.filter((c) => c.toolName === "application-deploy").length, 0);
  assert.equal(result.provisioning?.sourceConfigured, null);
});

test("19F falha source config (build) -> deploy nunca executado; estado parcial honesto", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    PROVISION_INPUT,
    { transport: fakeTransport({ failFor: ["application-saveBuildType"], handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "FAILED");
  assert.equal(log.filter((c) => c.toolName === "application-saveGitProvider").length, 1);
  assert.equal(log.filter((c) => c.toolName === "application-saveEnvironment").length, 0);
  assert.equal(log.filter((c) => c.toolName === "application-deploy").length, 0);
  assert.equal(result.provisioning?.sourceConfigured, true);
  assert.equal(result.provisioning?.buildConfigured, false);
  assert.ok(result.note?.includes("governed sequence incomplete"));
  assert.equal(result.url, null);
});

test("20F secret redaction: env value NUNCA no resultado; vai apenas no wire do saveEnvironment", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(PROVISION_INPUT, { transport: fakeTransport({ handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() });
  assert.ok(!JSON.stringify(result).includes("sk-super-secret-123"));
  const envCall = log.find((c) => c.toolName === "application-saveEnvironment");
  assert.ok(envCall);
  // The upstream contract REQUIRES the env string on the wire (container env);
  // the RESULT/steps/plan never echo it.
  assert.ok(String(envCall.arguments.env).includes("API_KEY=sk-super-secret-123"));
});

test("21F execute=true sem approval -> NENHUMA mutacao de provisioning (zero transport)", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    { ...PROVISION_INPUT, approved: false },
    { transport: fakeTransport({ handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "APPROVAL_REQUIRED");
  assert.equal(log.length, 0);
  for (const tool of ["project-create", "environment-create", "application-create", "application-saveGitProvider", "application-saveBuildType", "application-saveEnvironment", "application-deploy"]) {
    assert.equal(log.filter((c) => c.toolName === tool).length, 0, tool);
  }
});

test("22F rerun com recursos existentes -> sem duplicacao arbitraria (revalidation preservada)", async () => {
  const log1: VpsTransportCall[] = [];
  const run1 = await runGuardianAppDeploy(
    PROVISION_INPUT,
    { transport: fakeTransport({ failFor: ["application-deploy"], handlers: provisioningHandlers(), log: log1 }), guardian: fakeGuardianCore() },
  );
  assert.equal(run1.status, "FAILED");
  const log2: VpsTransportCall[] = [];
  const run2 = await runGuardianAppDeploy(
    PROVISION_INPUT,
    {
      transport: fakeTransport({
        handlers: provisioningHandlers({
          // application now EXISTS upstream -> revalidation refuses a duplicate.
          "application-search": () => ({ success: true, data: [{ name: "provisioned-app", applicationId: "app-77" }] }),
        }),
        log: log2,
      }),
      guardian: fakeGuardianCore(),
    },
  );
  assert.equal(log1.filter((c) => c.toolName === "project-create").length, 1);
  assert.equal(log2.filter((c) => c.toolName === "project-create").length, 0, "rerun must NOT create the project again");
  assert.equal(log2.filter((c) => c.toolName === "environment-create").length, 0, "rerun must NOT create the environment again");
  assert.equal(log2.filter((c) => c.toolName === "application-create").length, 0, "duplicate application name is refused by revalidation");
  assert.ok(run2.guardian?.reasons.includes("STATE_CHANGED_SINCE_PRECHECK"));
});

test("23F sucesso nominal -> sequencia mutante exata e contratos de wire corretos", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(PROVISION_INPUT, { transport: fakeTransport({ handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() });
  assert.equal(result.status, "LIVE");
  assert.deepEqual(
    log.map((c) => c.toolName).slice(0, 10),
    [
      "application-search",
      "project-all",
      "project-create",
      "environment-byProjectId",
      "environment-create",
      "application-create",
      "application-saveGitProvider",
      "application-saveBuildType",
      "application-saveEnvironment",
      "application-deploy",
    ],
  );
  const git = log.find((c) => c.toolName === "application-saveGitProvider");
  assert.deepEqual(git?.arguments, { applicationId: "app-77", customGitUrl: PROVISION_INPUT.source, customGitBranch: "main", customGitBuildPath: null, watchPaths: null });
  const build = log.find((c) => c.toolName === "application-saveBuildType");
  assert.deepEqual(build?.arguments, { applicationId: "app-77", buildType: "nixpacks", dockerfile: null, dockerContextPath: null, dockerBuildStage: null, herokuVersion: null, railpackVersion: null });
  const env = log.find((c) => c.toolName === "application-saveEnvironment");
  assert.equal(env?.arguments.createEnvFile, false);
  assert.equal(env?.arguments.buildArgs, null);
  assert.equal(env?.arguments.buildSecrets, null);
  assert.equal(env?.arguments.applicationId, "app-77");
  assert.equal(result.provisioning?.sourceConfigured, true);
  assert.equal(result.provisioning?.buildConfigured, true);
  assert.equal(result.provisioning?.envConfigured, true);
});

test("24F identity overrides: branch/buildType informados chegam ao wire; branch invalido -> NEEDS_INPUT", async () => {
  const log: VpsTransportCall[] = [];
  await runGuardianAppDeploy(
    { ...PROVISION_INPUT, branch: "release/1.0", buildType: "static" },
    { transport: fakeTransport({ handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() },
  );
  const git = log.find((c) => c.toolName === "application-saveGitProvider");
  assert.equal(git?.arguments.customGitBranch, "release/1.0");
  const build = log.find((c) => c.toolName === "application-saveBuildType");
  assert.equal(build?.arguments.buildType, "static");
  const invalid = await runGuardianAppDeploy(
    { ...PROVISION_INPUT, branch: "not valid branch!", execute: false },
    { transport: fakeTransport({ handlers: provisioningHandlers(), log: [] }), guardian: fakeGuardianCore() },
  );
  assert.equal(invalid.status, "NEEDS_INPUT");
  assert.ok(invalid.missing.includes("branch"));
});

test("25F dominio ausente -> generateDomain + domain-create (letsencrypt) -> LIVE com URL real", async () => {
  let oneCalls = 0;
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    PROVISION_INPUT,
    {
      transport: fakeTransport({
        handlers: provisioningHandlers({
          // 1st application-one (health): running but NO domain yet; appName present.
          // 2nd application-one (domain re-read after create): domain evidenced.
          "application-one": () => {
            oneCalls += 1;
            return oneCalls < 3
              ? { applicationId: "app-77", applicationStatus: "running", appName: "guardian-cloud-e2e" }
              : { applicationId: "app-77", applicationStatus: "running", appName: "guardian-cloud-e2e", domain: [{ host: "guardian-cloud-e2e.traefik.me", https: true, certificateType: "letsencrypt", domainType: "application" }] };
          },
          "domain-generateDomain": () => ({ host: "guardian-cloud-e2e.traefik.me" }),
          "domain-create": () => ({ success: true }),
        }),
        log,
      }),
      guardian: fakeGuardianCore(),
    },
  );
  assert.equal(result.status, "LIVE");
  assert.equal(result.url, "https://guardian-cloud-e2e.traefik.me");
  const generate = log.find((c) => c.toolName === "domain-generateDomain");
  assert.deepEqual(generate?.arguments, { appName: "guardian-cloud-e2e" });
  const create = log.find((c) => c.toolName === "domain-create");
  assert.deepEqual(create?.arguments, { host: "guardian-cloud-e2e.traefik.me", applicationId: "app-77", https: true, certificateType: "letsencrypt", domainType: "application" });
  assert.equal(result.provisioning?.domainGenerated, true);
  assert.equal(result.provisioning?.domainHost, "guardian-cloud-e2e.traefik.me");
});

test("26F generateDomain falha -> DEPLOYED_AWAITING_DOMAIN honesto, host nunca inventado", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    PROVISION_INPUT,
    {
      transport: fakeTransport({
        handlers: provisioningHandlers({
          "application-one": () => ({ applicationId: "app-77", applicationStatus: "running", appName: "guardian-cloud-e2e" }),
          "domain-generateDomain": () => ({ success: false, error: "no traefik.me support" }),
        }),
        log,
      }),
      guardian: fakeGuardianCore(),
    },
  );
  assert.equal(result.status, "DEPLOYED_AWAITING_DOMAIN");
  assert.equal(result.url, null);
  assert.equal(log.filter((c) => c.toolName === "domain-create").length, 0);
  assert.equal(result.provisioning?.domainGenerated, false);
  assert.ok(result.note?.includes("domain auto-provisioning failed"));
});

// MVP EXTERNO 01: serverId must reach domain-generateDomain so the generated
// host embeds the REAL destination IP (GCLOUD-01F finding) instead of 127-0-0-1.
test("29B serverId -> domain-generateDomain recebe serverId (host com IP real do destino)", async () => {
  let oneCalls = 0;
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    SERVER_ID_INPUT,
    {
      transport: fakeTransport({
        handlers: provisioningHandlers({
          "application-one": () => {
            oneCalls += 1;
            return oneCalls < 3
              ? { applicationId: "app-77", applicationStatus: "running", appName: "guardian-cloud-e2e" }
              : { applicationId: "app-77", applicationStatus: "running", appName: "guardian-cloud-e2e", domain: [{ host: "guardian-cloud-e2e.real-destination-ip.traefik.me", https: true, certificateType: "letsencrypt", domainType: "application" }] };
          },
          "domain-generateDomain": (args) => ({ host: `guardian-cloud-e2e.${args.serverId === "srv-destination-1" ? "real-destination-ip" : "127-0-0-1"}.traefik.me` }),
          "domain-create": () => ({ success: true }),
        }),
        log,
      }),
      guardian: fakeGuardianCore(),
    },
  );
  assert.equal(result.status, "LIVE");
  const generate = log.find((c) => c.toolName === "domain-generateDomain");
  assert.deepEqual(generate?.arguments, { appName: "guardian-cloud-e2e", serverId: "srv-destination-1" });
  assert.equal(result.provisioning?.domainHost, "guardian-cloud-e2e.real-destination-ip.traefik.me");
});

// ---- GCLOUD-01F: destination serverId (application-create upstream gate) ----

// Same nominal provisioning fixture + an explicit destination server. serverId
// is NOT a secret: it is a routing identity (shown in the plan destination).
const SERVER_ID_INPUT = { ...PROVISION_INPUT, serverId: "srv-destination-1" };

test("27F serverId informado -> propagado EXATAMENTE ao wire de application-create", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    SERVER_ID_INPUT,
    { transport: fakeTransport({ handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "LIVE");
  const create = log.find((c) => c.toolName === "application-create");
  assert.deepEqual(create?.arguments, { name: SERVER_ID_INPUT.name, environmentId: "env-1", sourceType: "git", serverId: "srv-destination-1" });
});

test("28F PLAN com serverId -> serverId=<id> no destino planejado; zero transport, zero mutation", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    { ...SERVER_ID_INPUT, execute: false },
    { transport: fakeTransport({ log }) },
  );
  assert.equal(result.status, "PLANNED");
  assert.equal(result.ok, true);
  assert.equal(result.mutated, false);
  assert.equal(log.length, 0);
  assert.equal(result.plan?.provisioning.serverId, "srv-destination-1");
});

test("29F approved=false com serverId -> Guardian recusa (zero transport, zero mutation)", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    { ...SERVER_ID_INPUT, approved: false },
    { transport: fakeTransport({ handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "APPROVAL_REQUIRED");
  assert.equal(result.mutated, false);
  assert.equal(log.length, 0);
  assert.ok(result.guardian?.reasons.includes("APPROVAL_GATE_NOT_SATISFIED"));
});

test("30F serverId aprovado nao pode ser trocado silenciosamente: destino vem SEMPRE do bind-forged proposal", async () => {
  const log: VpsTransportCall[] = [];
  const mutableInput: Record<string, unknown> = { ...SERVER_ID_INPUT };
  // Simulated post-approval destination-swap attempt: the RAW input object is
  // mutated AFTER bind (approval) and BEFORE apply (execution). The governed
  // path must still dispatch the APPROVED serverId, never the swapped one.
  const swappingCore: GuardianCoreModule = {
    async executeGuardianIntent<I, B>(intent: I, adapter: DomainAdapter<I, B>): Promise<GuardianResult> {
      const bound = await adapter.bind(intent);
      const record = bound as Record<string, unknown>;
      if (record.outcome === "NOT_EXECUTED") return bound as GuardianResult;
      mutableInput.serverId = "srv-EVIL-swap";
      return adapter.apply(record.proposal as B);
    },
  };
  const result = await runGuardianAppDeploy(
    mutableInput,
    { transport: fakeTransport({ handlers: provisioningHandlers(), log }), guardian: swappingCore },
  );
  assert.equal(result.status, "LIVE");
  const create = log.find((c) => c.toolName === "application-create");
  assert.equal(create?.arguments.serverId, "srv-destination-1");
  assert.notEqual(create?.arguments.serverId, "srv-EVIL-swap");
});

test("31F sem serverId -> contrato de wire anterior preservado (exatamente 3 campos; PLAN sem serverId)", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    PROVISION_INPUT,
    { transport: fakeTransport({ handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() },
  );
  assert.equal(result.status, "LIVE");
  const create = log.find((c) => c.toolName === "application-create");
  assert.deepEqual(create?.arguments, { name: PROVISION_INPUT.name, environmentId: "env-1", sourceType: "git" });
  const planned = await runGuardianAppDeploy({ ...PROVISION_INPUT, execute: false }, { transport: fakeTransport({ log: [] }) });
  assert.equal(Object.prototype.hasOwnProperty.call(planned.plan?.provisioning ?? {}, "serverId"), false);
});

test("32F secrets continuam redacted com serverId presente; serverId NAO e tratado como secret", async () => {
  const log: VpsTransportCall[] = [];
  const result = await runGuardianAppDeploy(
    SERVER_ID_INPUT,
    { transport: fakeTransport({ handlers: provisioningHandlers(), log }), guardian: fakeGuardianCore() },
  );
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes("sk-super-secret-123"));
  assert.ok(serialized.includes("srv-destination-1"));
  assert.ok(result.plan?.envKeys.includes("API_KEY"));
});
