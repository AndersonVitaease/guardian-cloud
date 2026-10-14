// MVP EXTERNO 02 — tests for the NEW code only (deploy entry).
// Controlled mock/fake: HTTP input -> existing executor (fake) -> HTTP output.
// REAL_DEPLOY_EXECUTED=NO — the real pipeline was already proven twice (MVP 01).
import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { handleDeployRequest, normalizeRepositoryUrl } from "../src/deployEntry.ts";
import type { GuardianAppDeployResult } from "../src/guardianAppDeploy.ts";
// Guardian Cloud adaptation: the host's authenticateBearer (ENG-MCP internal policy
// module) is intentionally NOT part of this repository. A minimal local equivalent
// keeps the same contract — returns the authenticated record or THROWS { code }
// (mapped to 401 by the route) — so this suite exercises the entry exactly the way
// the production host wiring does.
type TokenRecord = {
  tokenHash: string;
  subject: string;
  scopes: string[];
  allowedRepositoryIds: string[];
  expiresAt: string;
  revokedAt?: string | null;
};

function authenticateBearer(
  authorization: string | undefined,
  registry: TokenRecord[],
  repositoryId: string,
  now: Date,
  requiredScope: string,
): TokenRecord {
  const fail = (code: string): never => { throw Object.assign(new Error(code), { code }); };
  if (typeof authorization !== "string" || !authorization.startsWith("Bearer ")) fail("AUTHENTICATION_REQUIRED");
  const bearer = authorization.slice("Bearer ".length).trim();
  if (bearer.length === 0) fail("AUTHENTICATION_REQUIRED");
  const tokenHash = createHash("sha256").update(bearer).digest("hex");
  const record = registry.find((entry) => entry.tokenHash === tokenHash);
  if (!record) fail("AUTHENTICATION_INVALID");
  if (record.revokedAt != null) fail("AUTHENTICATION_INVALID");
  if (new Date(record.expiresAt).getTime() <= now.getTime()) fail("AUTHENTICATION_INVALID");
  if (!record.scopes.includes(requiredScope)) fail("AUTHENTICATION_INVALID");
  if (!record.allowedRepositoryIds.includes(repositoryId)) fail("AUTHENTICATION_INVALID");
  return record;
}

const TOKEN = "deploy-entry-test-token";
const AUTH = { "content-type": "application/json", authorization: `Bearer ${TOKEN}` };
const tokenRegistry: TokenRecord[] = [{
  tokenHash: createHash("sha256").update(TOKEN).digest("hex"),
  subject: "deploy-entry-tester",
  scopes: ["engineering:write"],
  allowedRepositoryIds: ["memoryos"],
  expiresAt: "2099-01-01T00:00:00.000Z",
}];

function fakeResult(overrides: Partial<GuardianAppDeployResult>): GuardianAppDeployResult {
  return {
    ok: false, status: "UNKNOWN", tool: "guardian.app.deploy", name: "", detection: null, missing: [],
    plan: null, provisioning: null, guardian: null, create: null, deploy: null, health: null,
    domain: null, url: null, mutated: false, guardianGate: "test-gate", note: null,
    ...overrides,
  };
}

let fakeDeployResult: GuardianAppDeployResult = fakeResult({ ok: true, status: "LIVE", url: "https://app-live.example" });
let snapshotFiles: Record<string, string | null> = {
  "package.json": '{"name":"x","scripts":{"start":"node server.js"}}',
  ".env.example": "PORT=3000",
};
let lastDeployInput: unknown = null;

// deps.authenticate mirrors the production host wiring: an authenticateBearer
// equivalent over the fake TokenRecord registry, injected as a dependency.
const deps = {
  repositoryId: "memoryos",
  authenticate: (authorization: string | undefined): unknown => authenticateBearer(authorization, tokenRegistry, "memoryos", new Date(), "engineering:write"),
  fetchSnapshot: async (_ownerRepo: string, filePath: string): Promise<string | null> => (filePath in snapshotFiles ? snapshotFiles[filePath] ?? null : null),
  runDeploy: async (input: unknown): Promise<GuardianAppDeployResult> => { lastDeployInput = input; return fakeDeployResult; },
};

async function withDeployServer(fn: (base: string) => Promise<void>, customDeps: typeof deps = deps): Promise<void> {
  const server: Server = createServer((request, response) => {
    void (async () => {
      // mirrors the one-line dispatch added to src/server.ts: unhandled -> 404
      const handled = await handleDeployRequest(request, response, customDeps);
      if (!handled) response.writeHead(404).end();
    })().catch(() => { try { response.writeHead(500).end(); } catch { /* response already sent */ } });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const port = typeof address === "object" && address !== null ? address.port : 0;
  try {
    await fn(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
}

async function post(base: string, path: string, body: string, headers: Record<string, string> = AUTH): Promise<{ status: number; body: Record<string, unknown> }> {
  const res = await fetch(`${base}${path}`, { method: "POST", body, headers });
  const text = await res.text();
  let parsed: Record<string, unknown> = {};
  try { parsed = JSON.parse(text) as Record<string, unknown>; } catch { parsed = { raw: text }; }
  return { status: res.status, body: parsed };
}

test("requests outside POST /deploy are not handled (dispatch continues)", async () => {
  await withDeployServer(async (base) => {
    const health = await fetch(`${base}/health`);
    assert.equal(health.status, 404);
    const other = await post(base, "/other", "{}");
    assert.equal(other.status, 404);
  });
});

test("missing or invalid bearer token -> 401 FAILED (fail-closed)", async () => {
  await withDeployServer(async (base) => {
    const none = await post(base, "/deploy", "{}", { "content-type": "application/json" });
    assert.equal(none.status, 401);
    assert.equal(none.body.reason, "AUTHENTICATION_REQUIRED");
    const bad = await post(base, "/deploy", "{}", { "content-type": "application/json", authorization: "Bearer wrong" });
    assert.equal(bad.status, 401);
    assert.equal(bad.body.reason, "AUTHENTICATION_INVALID");
  });
});

test("invalid JSON body -> 400 BODY_INVALID_JSON", async () => {
  await withDeployServer(async (base) => {
    const res = await post(base, "/deploy", "{not json");
    assert.equal(res.status, 400);
    assert.equal(res.body.reason, "BODY_INVALID_JSON");
  });
});

test("caller cannot smuggle internal parameters (strict two-key body)", async () => {
  await withDeployServer(async (base) => {
    const res = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://github.com/o/r", appName: "app-x", serverId: "SRV-EVIL", environmentId: "ENV-EVIL" }));
    assert.equal(res.status, 400);
    assert.equal(res.body.reason, "BODY_KEYS_INVALID");
    assert.equal(lastDeployInput, null);
  });
});

test("non-GitHub repositoryUrl -> 400 REPOSITORY_URL_INVALID", async () => {
  await withDeployServer(async (base) => {
    const res = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://gitlab.com/o/r", appName: "app-x" }));
    assert.equal(res.status, 400);
    assert.equal(res.body.reason, "REPOSITORY_URL_INVALID");
  });
});

test("invalid appName -> 400 APP_NAME_INVALID", async () => {
  await withDeployServer(async (base) => {
    const res = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://github.com/o/r", appName: "Not Valid!" }));
    assert.equal(res.status, 400);
    assert.equal(res.body.reason, "APP_NAME_INVALID");
  });
});

test("oversized body -> 413 BODY_TOO_LARGE", async () => {
  await withDeployServer(async (base) => {
    const res = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://github.com/o/r", appName: "app-x", pad: "x".repeat(8192) }));
    assert.equal(res.status, 413);
    assert.equal(res.body.reason, "BODY_TOO_LARGE");
  });
});

test("LIVE: maps executor LIVE+url to {status:LIVE,url} with internal-only invocation", async () => {
  fakeDeployResult = fakeResult({ ok: true, status: "LIVE", url: "https://app-live.example" });
  lastDeployInput = null;
  await withDeployServer(async (base) => {
    const res = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://github.com/AndersonVitaease/guardian-cloud-mvp02.git/", appName: "guardian-cloud-mvp02" }));
    assert.equal(res.status, 200);
    assert.deepEqual(res.body, { status: "LIVE", url: "https://app-live.example" });
    assert.deepEqual(lastDeployInput, {
      name: "guardian-cloud-mvp02",
      source: "https://github.com/AndersonVitaease/guardian-cloud-mvp02", // .git/ normalized away
      approved: true,
      execute: true,
      env: { PORT: "3000" },
      environmentId: TEST_ENVIRONMENT_ID, // internal, resolved from operator env only
      serverId: TEST_SERVER_ID,           // internal, resolved from operator env only
      projectSnapshot: { packageJsonText: '{"name":"x","scripts":{"start":"node server.js"}}', files: { ".env.example": "PORT=3000" } },
    });
  });
});

test("DEPLOYED_AWAITING_DOMAIN -> {status:DEPLOYING} without url", async () => {
  fakeDeployResult = fakeResult({ status: "DEPLOYED_AWAITING_DOMAIN" });
  await withDeployServer(async (base) => {
    const res = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://github.com/o/r", appName: "app-x" }));
    assert.equal(res.status, 200);
    assert.deepEqual(res.body, { status: "DEPLOYING" });
  });
});

test("NEEDS_INPUT -> FAILED with bounded reason", async () => {
  fakeDeployResult = fakeResult({ status: "NEEDS_INPUT", missing: ["port"] });
  await withDeployServer(async (base) => {
    const res = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://github.com/o/r", appName: "app-x" }));
    assert.equal(res.status, 200);
    assert.deepEqual(res.body, { status: "FAILED", reason: "NEEDS_INPUT: port" });
  });
});

test("FAILED -> FAILED with the executor note as bounded reason", async () => {
  fakeDeployResult = fakeResult({ status: "FAILED", note: "application-create rejected" });
  await withDeployServer(async (base) => {
    const res = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://github.com/o/r", appName: "app-x" }));
    assert.equal(res.status, 200);
    assert.deepEqual(res.body, { status: "FAILED", reason: "application-create rejected" });
  });
});

test("never invents LIVE: UNKNOWN state and LIVE-without-url fail closed", async () => {
  fakeDeployResult = fakeResult({ status: "UNKNOWN", note: "transport unreachable" });
  await withDeployServer(async (base) => {
    const unknown = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://github.com/o/r", appName: "app-x" }));
    assert.equal(unknown.status, 200);
    assert.deepEqual(unknown.body, { status: "FAILED", reason: "UNEXPECTED_STATE_UNKNOWN: transport unreachable" });
  });
  fakeDeployResult = fakeResult({ ok: true, status: "LIVE", url: null });
  await withDeployServer(async (base) => {
    const liveNoUrl = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://github.com/o/r", appName: "app-x" }));
    assert.equal(liveNoUrl.status, 200);
    assert.deepEqual(liveNoUrl.body, { status: "FAILED", reason: "LIVE_WITHOUT_URL" });
  });
});

test("normalizeRepositoryUrl: accepts github URLs with optional .git/trailing slash only", () => {
  assert.equal(normalizeRepositoryUrl("https://github.com/o/r"), "https://github.com/o/r");
  assert.equal(normalizeRepositoryUrl("https://github.com/o/r.git"), "https://github.com/o/r");
  assert.equal(normalizeRepositoryUrl("https://github.com/o/r/"), "https://github.com/o/r");
  assert.equal(normalizeRepositoryUrl("http://github.com/o/r"), null);
  assert.equal(normalizeRepositoryUrl("https://github.com/o/r/tree/main"), null);
  assert.equal(normalizeRepositoryUrl("https://github.com/../etc"), null);
  assert.equal(normalizeRepositoryUrl(42), null);
});

// Fake operator identity for dispatch-reaching tests: the entry resolves the internal
// deployment identity ONLY from the operator environment at request time. The values
// are fake test identifiers and are printed nowhere.
const TEST_ENVIRONMENT_ID = "test-environment-id";
const TEST_SERVER_ID = "test-server-id";
const PREVIOUS_DEPLOY_ENV = {
  environmentId: process.env.ENG_MCP_DEPLOY_ENVIRONMENT_ID,
  serverId: process.env.ENG_MCP_DEPLOY_SERVER_ID,
};
process.env.ENG_MCP_DEPLOY_ENVIRONMENT_ID = TEST_ENVIRONMENT_ID;
process.env.ENG_MCP_DEPLOY_SERVER_ID = TEST_SERVER_ID;

test("injected deps.authenticate is used (spied) and the request proceeds", async () => {
  let seenCalls = 0;
  let seenAuthorization: string | undefined;
  const spyDeps = {
    ...deps,
    authenticate: (authorization: string | undefined): unknown => {
      seenCalls += 1;
      seenAuthorization = authorization;
      return { subject: "spy-subject" };
    },
  };
  fakeDeployResult = fakeResult({ ok: true, status: "LIVE", url: "https://app-live.example" });
  lastDeployInput = null;
  await withDeployServer(async (base) => {
    const res = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://github.com/o/r", appName: "app-x" }));
    assert.equal(res.status, 200);
    assert.deepEqual(res.body, { status: "LIVE", url: "https://app-live.example" });
    assert.equal(seenCalls, 1);
    assert.equal(seenAuthorization, `Bearer ${TOKEN}`);
  }, spyDeps);
});

test("deps.authenticate absent -> 401 AUTHENTICATION_REQUIRED (fail-closed, never open)", async () => {
  let statusCode = 0;
  let payload = "";
  const fakeResponse = {
    writeHead: (status: number): unknown => { statusCode = status; return fakeResponse; },
    end: (text?: unknown): void => { payload = typeof text === "string" ? text : ""; },
  } as unknown as ServerResponse;
  const fakeRequest = {
    method: "POST",
    url: "/deploy",
    headers: { authorization: `Bearer ${TOKEN}` },
  } as unknown as IncomingMessage;
  const handled = await handleDeployRequest(fakeRequest, fakeResponse, { ...deps, authenticate: undefined });
  assert.equal(handled, true);
  assert.equal(statusCode, 401);
  assert.deepEqual(JSON.parse(payload) as Record<string, unknown>, { status: "FAILED", reason: "AUTHENTICATION_REQUIRED" });
});

test("missing deploy env -> 500 DEPLOY_CONFIG_MISSING and runDeploy is never called", async () => {
  lastDeployInput = null;
  delete process.env.ENG_MCP_DEPLOY_ENVIRONMENT_ID;
  delete process.env.ENG_MCP_DEPLOY_SERVER_ID;
  try {
    await withDeployServer(async (base) => {
      const res = await post(base, "/deploy", JSON.stringify({ repositoryUrl: "https://github.com/o/r", appName: "app-x" }));
      assert.equal(res.status, 500);
      assert.deepEqual(res.body, { status: "FAILED", reason: "DEPLOY_CONFIG_MISSING", missing: ["ENG_MCP_DEPLOY_ENVIRONMENT_ID", "ENG_MCP_DEPLOY_SERVER_ID"] });
      assert.equal(lastDeployInput, null);
    });
  } finally {
    process.env.ENG_MCP_DEPLOY_ENVIRONMENT_ID = TEST_ENVIRONMENT_ID;
    process.env.ENG_MCP_DEPLOY_SERVER_ID = TEST_SERVER_ID;
  }
});

test("restore operator deploy env (suite teardown)", () => {
  if (PREVIOUS_DEPLOY_ENV.environmentId === undefined) delete process.env.ENG_MCP_DEPLOY_ENVIRONMENT_ID;
  else process.env.ENG_MCP_DEPLOY_ENVIRONMENT_ID = PREVIOUS_DEPLOY_ENV.environmentId;
  if (PREVIOUS_DEPLOY_ENV.serverId === undefined) delete process.env.ENG_MCP_DEPLOY_SERVER_ID;
  else process.env.ENG_MCP_DEPLOY_SERVER_ID = PREVIOUS_DEPLOY_ENV.serverId;
});
