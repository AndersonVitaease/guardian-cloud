import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildEnvText,
  callProvisionPrimitive,
  resolveOrCreateProject,
  resolveOrCreateEnvironment,
  configureApplicationSource,
  ensureApplicationDomain,
  PROVISION_IDENTITY_DEFAULTS,
  DOKPLOY_BUILD_TYPES,
} from "../src/appProvision.ts";
import type { VpsTransport, VpsTransportCall, VpsTransportResponse } from "../src/vpsTransport.ts";

// Transport fake: sem rede. Registra as chamadas e responde por toolName.
function fakeTransport(
  handler: (call: VpsTransportCall) => VpsTransportResponse | Promise<VpsTransportResponse>,
): { transport: VpsTransport; calls: VpsTransportCall[] } {
  const calls: VpsTransportCall[] = [];
  const transport: VpsTransport = {
    name: "fake-transport",
    async call(request: VpsTransportCall): Promise<VpsTransportResponse> {
      calls.push(request);
      return handler(request);
    },
  };
  return { transport, calls };
}

function okResponse(result: unknown): VpsTransportResponse {
  return { ok: true, status: 200, durationMs: 5, error: undefined, result };
}

test("buildEnvText: undefined -> vazio; chaves ordenadas deterministicamente", () => {
  assert.equal(buildEnvText(undefined), "");
  assert.equal(buildEnvText({}), "");
  assert.equal(buildEnvText({ B: "2", A: "1" }), "A=1\nB=2");
  assert.equal(buildEnvText({ B: "2", A: "1" }), buildEnvText({ A: "1", B: "2" }));
});

test("callProvisionPrimitive: happy path EXECUTED_ACCEPTED com mutating flag preservada", async () => {
  const { transport, calls } = fakeTransport(() => okResponse({ success: true, data: { id: "x" } }));
  const result = await callProvisionPrimitive({ transport }, "project-all", {}, false);
  assert.equal(result.ok, true);
  assert.equal(result.outcome, "EXECUTED_ACCEPTED");
  assert.equal(result.isError, false);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].mutating, false);
});

test("callProvisionPrimitive: erro de transporte (throw) -> UPSTREAM_ERROR sem lançar", async () => {
  const { transport } = fakeTransport(() => {
    throw new Error("CONEXAO_RECUSADA");
  });
  const result = await callProvisionPrimitive({ transport }, "project-all", {}, false);
  assert.equal(result.ok, false);
  assert.equal(result.outcome, "UPSTREAM_ERROR");
  assert.equal(result.status, 0);
  assert.equal(result.error, "CONEXAO_RECUSADA");
});

test("callProvisionPrimitive: isError upstream -> EXECUTED_FAILED com erro limitado a 300 chars", async () => {
  const longText = "E".repeat(500);
  const { transport } = fakeTransport(() => okResponse({ isError: true, text: longText }));
  const result = await callProvisionPrimitive({ transport }, "project-create", { name: "p" }, true);
  assert.equal(result.ok, false);
  assert.equal(result.outcome, "EXECUTED_FAILED");
  assert.equal(result.isError, true);
  assert.equal((result.error ?? "").length, 300);
});

test("callProvisionPrimitive: status 500 -> UPSTREAM_ERROR; status 400 -> EXECUTED_FAILED", async () => {
  const a = fakeTransport(() => ({ ok: false, status: 500, durationMs: 1, error: "boom", result: null }));
  const ra = await callProvisionPrimitive({ transport: a.transport }, "t", {}, false);
  assert.equal(ra.outcome, "UPSTREAM_ERROR");
  const b = fakeTransport(() => ({ ok: false, status: 400, durationMs: 1, error: "bad", result: null }));
  const rb = await callProvisionPrimitive({ transport: b.transport }, "t", {}, false);
  assert.equal(rb.outcome, "EXECUTED_FAILED");
});

test("resolveOrCreateProject: REUSED quando projeto já existe", async () => {
  const { transport, calls } = fakeTransport(() =>
    okResponse({ data: [{ name: "meu-projeto", projectId: "proj-1" }] }),
  );
  const result = await resolveOrCreateProject({ transport }, { projectName: "meu-projeto" });
  assert.equal(result.ok, true);
  assert.equal(result.reused, true);
  assert.equal(result.projectId, "proj-1");
  assert.equal(result.outcome, "REUSED");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].toolName, "project-all");
});

test("resolveOrCreateProject: CREATED com description propagada", async () => {
  const { transport, calls } = fakeTransport((call) => {
    if (call.toolName === "project-all") return okResponse({ data: [] });
    assert.equal(call.toolName, "project-create");
    assert.equal(call.mutating, true);
    assert.equal(call.arguments.description, "desc");
    return okResponse({ data: { projectId: "proj-2" } });
  });
  const result = await resolveOrCreateProject({ transport }, { projectName: "novo", description: "desc" });
  assert.equal(result.ok, true);
  assert.equal(result.outcome, "CREATED");
  assert.equal(result.projectId, "proj-2");
});

test("resolveOrCreateProject: borda — project-all com shape desconhecido -> READ_FAILED fail-closed", async () => {
  const { transport } = fakeTransport(() => okResponse({ data: { items: "nao-lista" } }));
  const result = await resolveOrCreateProject({ transport }, { projectName: "x" });
  assert.equal(result.ok, false);
  assert.equal(result.outcome, "READ_FAILED");
  assert.equal(result.error, "project-all returned an unrecognized list shape");
});

test("resolveOrCreateProject: borda — create aceito sem projectId -> EXECUTED_FAILED (sem fabricar id)", async () => {
  const { transport } = fakeTransport((call) =>
    call.toolName === "project-all" ? okResponse({ data: [] }) : okResponse({ success: true, message: "ok" }),
  );
  const result = await resolveOrCreateProject({ transport }, { projectName: "x" });
  assert.equal(result.ok, false);
  assert.equal(result.outcome, "EXECUTED_FAILED");
  assert.match(result.error ?? "", /projectId absent/);
});

test("resolveOrCreateEnvironment: REUSED e CREATED", async () => {
  const reused = fakeTransport(() => okResponse({ data: [{ name: "prod", environmentId: "env-1" }] }));
  const r1 = await resolveOrCreateEnvironment({ transport: reused.transport }, { projectId: "p1", environmentName: "prod" });
  assert.equal(r1.ok, true);
  assert.equal(r1.environmentId, "env-1");
  assert.equal(r1.outcome, "REUSED");

  const created = fakeTransport((call) =>
    call.toolName === "environment-byProjectId"
      ? okResponse({ data: [] })
      : okResponse({ data: { environmentId: "env-2" } }),
  );
  const r2 = await resolveOrCreateEnvironment({ transport: created.transport }, { projectId: "p1", environmentName: "staging" });
  assert.equal(r2.ok, true);
  assert.equal(r2.outcome, "CREATED");
  assert.equal(r2.environmentId, "env-2");
});

test("resolveOrCreateEnvironment: borda — lookup falha -> READ_FAILED", async () => {
  const { transport } = fakeTransport(() => ({ ok: false, status: 500, durationMs: 1, error: "down", result: null }));
  const result = await resolveOrCreateEnvironment({ transport }, { projectId: "p1", environmentName: "prod" });
  assert.equal(result.ok, false);
  assert.equal(result.outcome, "READ_FAILED");
  assert.equal(result.error, "down");
});

test("configureApplicationSource: happy path executa 3 passos em ordem", async () => {
  const { transport, calls } = fakeTransport(() => okResponse({ success: true }));
  const result = await configureApplicationSource({ transport }, {
    applicationId: "app-1",
    repoUrl: "https://git.example/repo.git",
    branch: "main",
    buildPath: null,
    buildType: "nixpacks",
    envText: "PORT=3000",
  });
  assert.equal(result.ok, true);
  assert.equal(result.failedStep, null);
  assert.deepEqual(result.steps.map((s) => s.step), ["git", "build", "env"]);
  assert.deepEqual(calls.map((c) => c.toolName), [
    "application-saveGitProvider",
    "application-saveBuildType",
    "application-saveEnvironment",
  ]);
  assert.equal(calls[2].arguments.env, "PORT=3000");
});

test("configureApplicationSource: borda — falha no passo git interrompe sequência", async () => {
  const { transport, calls } = fakeTransport((call) =>
    call.toolName === "application-saveGitProvider"
      ? { ok: false, status: 400, durationMs: 1, error: "branch invalida", result: null }
      : okResponse({ success: true }),
  );
  const result = await configureApplicationSource({ transport }, {
    applicationId: "app-1",
    repoUrl: "https://git.example/repo.git",
    branch: "",
    buildPath: null,
    buildType: "nixpacks",
    envText: "",
  });
  assert.equal(result.ok, false);
  assert.equal(result.failedStep, "git");
  assert.equal(calls.length, 1);
});

test("configureApplicationSource: env vazio é enviado como null, nunca string vazia", async () => {
  const { transport, calls } = fakeTransport(() => okResponse({ success: true }));
  const result = await configureApplicationSource({ transport }, {
    applicationId: "app-1",
    repoUrl: "u",
    branch: "main",
    buildPath: null,
    buildType: "nixpacks",
    envText: "",
  });
  assert.equal(result.ok, true);
  assert.equal(calls[2].arguments.env, null);
});

test("ensureApplicationDomain: APP_NAME_UNRESOLVED quando appName vazio (entrada inválida)", async () => {
  const { transport, calls } = fakeTransport(() => okResponse({ success: true }));
  const result = await ensureApplicationDomain({ transport }, { applicationId: "a1", appName: "" });
  assert.equal(result.ok, false);
  assert.equal(result.outcome, "APP_NAME_UNRESOLVED");
  assert.equal(calls.length, 0);
});

test("ensureApplicationDomain: happy path gera host e cria domínio https", async () => {
  const { transport, calls } = fakeTransport((call) => {
    if (call.toolName === "domain-generateDomain") return okResponse({ data: { host: "app.traefik.me" } });
    assert.equal(call.toolName, "domain-create");
    assert.equal(call.arguments.https, true);
    return okResponse({ success: true });
  });
  const result = await ensureApplicationDomain({ transport }, { applicationId: "a1", appName: "app", serverId: "srv-1" });
  assert.equal(result.ok, true);
  assert.equal(result.outcome, "GENERATED_AND_CREATED");
  assert.equal(result.host, "app.traefik.me");
  assert.equal(calls[0].arguments.serverId, "srv-1");
});

test("ensureApplicationDomain: borda — generate sem host extraível -> GENERATE_FAILED fail-closed", async () => {
  const { transport, calls } = fakeTransport(() => okResponse({ success: true, message: "ok" }));
  const result = await ensureApplicationDomain({ transport }, { applicationId: "a1", appName: "app" });
  assert.equal(result.ok, false);
  assert.equal(result.outcome, "GENERATE_FAILED");
  assert.equal(calls.length, 1);
});

test("constantes exportadas: defaults de identidade e build types", () => {
  assert.ok(Object.isFrozen(PROVISION_IDENTITY_DEFAULTS));
  assert.ok(Object.isFrozen(DOKPLOY_BUILD_TYPES));
  assert.ok(DOKPLOY_BUILD_TYPES.includes("nixpacks"));
});
