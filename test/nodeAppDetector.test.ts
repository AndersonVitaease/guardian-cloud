import { test } from "node:test";
import assert from "node:assert/strict";
import { detectNodeApp } from "../src/nodeAppDetector.ts";

// GCLOUD-01C — minimal offline tests for the evidence-only Node app detector.
// Pure functions: no network, no filesystem, no transport, no LLM, zero
// mutation. Fixtures are obviously synthetic. Evidence-only semantics are
// asserted directly (no invented start defaults, no invented ports, env NAMES
// only, honest NEEDS_INPUT/UNSUPPORTED/INVALID_PROJECT failures).

const PKG_UNAMBIGUOUS_START = JSON.stringify({
  name: "svc-a",
  version: "1.0.0",
  scripts: { start: "node server.js" },
});

test("01 package.json with unambiguous scripts.start -> DETECTED with npm start and no invented port", () => {
  const result = detectNodeApp({ packageJsonText: PKG_UNAMBIGUOUS_START });
  assert.equal(result.ok, true);
  assert.equal(result.status, "DETECTED");
  assert.equal(result.runtime, "node");
  assert.equal(result.startCommand, "npm start");
  assert.equal(result.confidence, "HIGH");
  assert.deepEqual(result.startAlternatives, []);
  // No port evidence anywhere -> no assumed 3000/8080, honest pending input.
  assert.equal(result.port, null);
  assert.equal(result.portStrategy, "UNKNOWN");
  assert.deepEqual(result.needsInput, ["port"]);
  assert.equal(result.mutated, false);
  assert.ok(result.evidence.some((e) => e.source === "package.json:scripts" && e.detail.includes("node server.js")));
});

test("02 valid package.json without usable start evidence -> NEEDS_INPUT (npm start NOT invented)", () => {
  const result = detectNodeApp({
    packageJsonText: JSON.stringify({ name: "svc-b", scripts: { build: "tsc" } }),
  });
  assert.equal(result.ok, false);
  assert.equal(result.status, "NEEDS_INPUT");
  // Runtime IS evidenced by the valid package.json...
  assert.equal(result.runtime, "node");
  // ...but no start command may be fabricated from nothing.
  assert.equal(result.startCommand, null);
  assert.deepEqual(result.startAlternatives, []);
  assert.deepEqual(result.needsInput, ["startCommand", "port"]);
  assert.equal(result.confidence, "LOW");
});

test("03 two ambiguous start options -> NEEDS_INPUT with alternatives, no arbitrary pick", () => {
  const result = detectNodeApp({
    packageJsonText: JSON.stringify({
      name: "svc-c",
      scripts: { serve: "node server.js", production: "NODE_ENV=production node index.js" },
    }),
  });
  assert.equal(result.ok, false);
  assert.equal(result.status, "NEEDS_INPUT");
  assert.equal(result.startCommand, null);
  assert.equal(result.startAlternatives.length, 2);
  assert.ok(result.startAlternatives.includes("npm run serve"));
  assert.ok(result.startAlternatives.includes("npm run production"));
  assert.deepEqual(result.needsInput, ["startCommand", "port"]);
  assert.ok(result.evidence.some((e) => e.detail.includes("none clearly preferable")));
});

test("04 explicit port evidenced in entry file -> FIXED port, no pending port input", () => {
  const result = detectNodeApp({
    packageJsonText: PKG_UNAMBIGUOUS_START,
    files: {
      "server.js": "const http = require('http');\nhttp.createServer(handler).listen(4040);\n",
    },
  });
  assert.equal(result.ok, true);
  assert.equal(result.status, "DETECTED");
  assert.equal(result.startCommand, "npm start");
  assert.equal(result.port, 4040);
  assert.equal(result.portStrategy, "FIXED");
  assert.deepEqual(result.needsInput, []);
  assert.ok(result.evidence.some((e) => e.source === "port configuration" && e.detail.includes("4040")));
});

test("05 process.env.PORT without evidenced value -> ENV_PORT + needsInput ['port']", () => {
  const result = detectNodeApp({
    packageJsonText: PKG_UNAMBIGUOUS_START,
    files: {
      "server.js": "const server = http.createServer();\nserver.listen(process.env.PORT);\n",
    },
  });
  assert.equal(result.ok, true);
  assert.equal(result.status, "DETECTED");
  assert.equal(result.port, null);
  assert.equal(result.portStrategy, "ENV_PORT");
  assert.deepEqual(result.needsInput, ["port"]);
  assert.ok(result.evidence.some((e) => e.source === "port configuration" && e.detail.includes("process.env.PORT")));
});

test("06 env requirements appear as NAMES only, values/secrets never returned", () => {
  const result = detectNodeApp({
    packageJsonText: PKG_UNAMBIGUOUS_START,
    files: {
      "server.js":
        "const client = createClient(process.env.DATABASE_URL);\ninit(process.env.API_KEY);\n",
      ".env.example":
        "DATABASE_URL=postgres://user:super-secret@db.internal:5432/app\nAPI_KEY=sk-live-0000000000\n",
    },
  });
  assert.equal(result.status, "DETECTED");
  assert.deepEqual(result.envRequirements, ["API_KEY", "DATABASE_URL"]);
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes("postgres://"), "env VALUES must never leak");
  assert.ok(!serialized.includes("super-secret"), "env VALUES must never leak");
  assert.ok(!serialized.includes("sk-live-0000000000"), "env VALUES must never leak");
  for (const requirement of result.envRequirements) {
    assert.ok(!requirement.includes("="), "env requirements are NAMES only");
  }
  for (const item of result.evidence) {
    assert.ok(!item.detail.includes("DATABASE_URL="), "no key=value pairs in evidence");
    assert.ok(!item.detail.includes("API_KEY="), "no key=value pairs in evidence");
  }
});

test("07 no package.json evidence -> UNSUPPORTED, runtime stays null, no other runtime attempted", () => {
  const result = detectNodeApp({ files: { "main.py": "print('hi')\n" } });
  assert.equal(result.ok, false);
  assert.equal(result.status, "UNSUPPORTED");
  assert.equal(result.runtime, null);
  assert.equal(result.startCommand, null);
  assert.equal(result.mutated, false);
  // Empty input behaves the same way.
  const empty = detectNodeApp({});
  assert.equal(empty.status, "UNSUPPORTED");
});

test("08 invalid package.json -> INVALID_PROJECT with honest note", () => {
  const result = detectNodeApp({ packageJsonText: '{ "name": "broken", scripts: }' });
  assert.equal(result.ok, false);
  assert.equal(result.status, "INVALID_PROJECT");
  assert.equal(result.runtime, null);
  assert.equal(result.startCommand, null);
  assert.ok(result.note !== null && result.note.includes("not valid JSON"));
});
