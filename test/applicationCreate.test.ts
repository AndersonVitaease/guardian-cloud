import { test } from "node:test";
import assert from "node:assert/strict";
import { runApplicationCreate, validateApplicationCreateInput } from "../src/applicationCreate.ts";
import type { VpsTransport, VpsTransportCall, VpsTransportResponse } from "../src/vpsTransport.ts";

// GCLOUD-01A — application-create primitive tests. FAKE transport only: no
// network, no production, no real Dokploy calls, no Guardian (gate is applied
// by the future guardian.app.deploy SuperTool — documented, not claimed here).

const BASE = 1_760_000_000_000;
const now = (): number => BASE;

type Log = VpsTransportCall[];

function fakeTransport(log: Log, response?: Partial<VpsTransportResponse>, handler?: (args: Record<string, unknown>) => unknown): VpsTransport {
  return {
    name: "fake",
    async call(request: VpsTransportCall): Promise<VpsTransportResponse> {
      log.push(request);
      if (handler) return { ok: true, status: 200, result: handler(request.arguments), durationMs: 1 };
      if (response && response.ok === false) return { ok: false, status: response.status ?? 502, error: response.error ?? "FAKE_UPSTREAM_FAILURE", durationMs: 1 };
      return { ok: true, status: 200, result: { applicationId: "app-created-1" }, durationMs: 1 };
    },
  };
}

const VALID = { name: "gcloud-fixture", source: "github:AndersonVitaease/gcloud-fixture-node", startCommand: "node server.js", environmentId: "env-fixture-1", port: 3000, env: { NODE_ENV: "production" } };

test("01 - valid input, execute=false => PLANNED, zero transport calls, env values redacted", async () => {
  const log: Log = [];
  const result = await runApplicationCreate("test", { ...VALID, execute: false }, { transport: fakeTransport(log), now });
  assert.equal(result.ok, true);
  assert.equal(result.outcome, "PLANNED");
  assert.equal(result.mutated, false);
  assert.equal(log.length, 0);
  assert.equal(JSON.stringify(result).includes("production"), false); // env value never echoed
  assert.deepEqual(result.plan?.redactedArguments.env, { NODE_ENV: "[REDACTED]" });
});

test("02 - execute=true => ONE mutating call forwarded to application-create with full arguments + confirmation", async () => {
  const log: Log = [];
  let received: Record<string, unknown> | null = null;
  const result = await runApplicationCreate("test", { ...VALID, execute: true }, { transport: fakeTransport(log, undefined, (args) => { received = args; return { applicationId: "app-created-1" }; }), now });
  assert.equal(result.ok, true);
  assert.equal(result.outcome, "EXECUTED_ACCEPTED");
  assert.equal(result.mutated, true);
  assert.equal(log.length, 1);
  assert.equal(log[0].toolName, "application-create");
  assert.equal(log[0].mutating, true);
  assert.equal(log[0].confirmation.toolName, "application-create");
  assert.deepEqual(received, { name: VALID.name, environmentId: "env-fixture-1", sourceType: "git" });
  assert.equal(result.createdApplicationId, "app-created-1");
});

test("03 - missing critical inputs => NEEDS_INPUT, honest missing list, zero mutation", async () => {
  const log: Log = [];
  const result = await runApplicationCreate("test", { name: "", source: "", startCommand: "" } as never, { transport: fakeTransport(log), now });
  assert.equal(result.ok, false);
  assert.equal(result.outcome, "NEEDS_INPUT");
  assert.deepEqual(result.missing.sort(), ["name", "source", "startCommand"]);
  assert.equal(result.mutated, false);
  assert.equal(log.length, 0);
});

test("04 - upstream failure preserved honestly, no throw, no fabricated success", async () => {
  const log: Log = [];
  const result = await runApplicationCreate("test", { ...VALID, execute: true }, { transport: fakeTransport(log, { ok: false, status: 502, error: "FAKE_UPSTREAM_FAILURE:application-create" }), now });
  assert.equal(result.ok, false);
  assert.equal(result.outcome, "UPSTREAM_ERROR");
  assert.equal(result.mutated, false);
  assert.equal(result.response?.error, "FAKE_UPSTREAM_FAILURE:application-create");
  assert.equal(result.createdApplicationId, undefined);
  assert.equal(log.length, 1);
});

test("05 - validation catches bad port/env before any dispatch; validator unit-checks", () => {
  const log: Log = [];
  const bad = validateApplicationCreateInput({ name: "x", source: "y", startCommand: "z", port: 99_999, env: "nope" });
  assert.equal(bad.ok, false);
  if (!bad.ok) assert.deepEqual(bad.missing.sort(), ["env", "port"]);
  const good = validateApplicationCreateInput(VALID);
  assert.equal(good.ok, true);
  assert.equal(log.length, 0);
});
