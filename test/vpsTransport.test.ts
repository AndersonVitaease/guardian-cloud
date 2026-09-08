// Neutral transport module tests (vpsTransport.ts) — no operational endpoints or IDs.
// The endpoint-absent case must fail closed with ZERO network egress; the explicit
// endpoint case is proven against a local 127.0.0.1 loopback server.
import test from "node:test";
import assert from "node:assert/strict";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { createMcpClientCallTransport, normalizeMcpResult } from "../src/vpsTransport.ts";

test("normalizeMcpResult: structuredContent wins when present", () => {
  const structured = { items: [1, 2] };
  assert.equal(normalizeMcpResult({ structuredContent: structured, content: [{ type: "text", text: "ignored" }] }), structured);
});

test("normalizeMcpResult: single JSON text element is parsed", () => {
  const parsed = normalizeMcpResult({ content: [{ type: "text", text: '{"a":1}' }] });
  assert.deepEqual(parsed, { a: 1 });
});

test("normalizeMcpResult: plain text elements are preserved as {text} without invented parsing", () => {
  const parsed = normalizeMcpResult({ content: [{ type: "text", text: "hello" }, { type: "text", text: "world" }] });
  assert.deepEqual(parsed, { text: "hello\nworld" });
});

test("normalizeMcpResult: ambiguous envelope and non-records pass through unchanged", () => {
  const ambiguous = { content: [{ type: "text", text: '{"a":1}' }, { type: "text", text: "plain" }] };
  assert.equal(normalizeMcpResult(ambiguous), ambiguous);
  assert.equal(normalizeMcpResult("scalar"), "scalar");
  assert.equal(normalizeMcpResult(42), 42);
});

test("factory: endpoint absent -> call fails closed with GATEWAY_ENDPOINT_INVALID and no network egress", async () => {
  const originalEndpoint = process.env.ENG_MCP_AGENT_MEMORY_ENDPOINT;
  delete process.env.ENG_MCP_AGENT_MEMORY_ENDPOINT;
  let fetchCalled = false;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    fetchCalled = true;
    throw new Error("network egress attempted");
  }) as typeof fetch;
  try {
    const transport = createMcpClientCallTransport({ dokployServerId: "test-server-id" });
    const response = await transport.call({
      toolName: "application-one",
      arguments: { applicationId: "x" },
      mutating: false,
      confirmation: { toolName: "application-one" },
    });
    assert.equal(response.ok, false);
    assert.equal(response.status, 0);
    assert.equal(response.error, "GATEWAY_ENDPOINT_INVALID");
    assert.equal(fetchCalled, false); // no network egress: the endpoint is never invented
  } finally {
    globalThis.fetch = originalFetch;
    if (originalEndpoint === undefined) delete process.env.ENG_MCP_AGENT_MEMORY_ENDPOINT;
    else process.env.ENG_MCP_AGENT_MEMORY_ENDPOINT = originalEndpoint;
  }
});

test("factory: an explicitly provided endpoint is used (local loopback, full contract)", async () => {
  const server: Server = createServer((request: IncomingMessage, response: ServerResponse) => {
    let body = "";
    request.on("data", (chunk: Buffer) => { body += chunk.toString("utf8"); });
    request.on("end", () => {
      const parsed = JSON.parse(body) as { serverId?: string; operation?: string; toolName?: string; confirmation?: { toolName?: string } };
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: true, result: { echo: parsed } }));
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const port = typeof address === "object" && address !== null ? address.port : 0;
  try {
    const transport = createMcpClientCallTransport({ dokployServerId: "test-server-id", endpoint: `http://127.0.0.1:${port}/agentMemoryBridge` });
    const response = await transport.call({
      toolName: "application-one",
      arguments: { applicationId: "x" },
      mutating: false,
      confirmation: { toolName: "application-one" },
    });
    assert.equal(response.ok, true);
    assert.equal(response.status, 200);
    const echo = (response.result as { echo?: { serverId?: string; operation?: string; toolName?: string; confirmation?: { toolName?: string } } })?.echo;
    assert.equal(echo?.serverId, "test-server-id"); // options.dokployServerId is used verbatim
    assert.equal(echo?.operation, "mcp_execute");
    assert.equal(echo?.toolName, "application-one");
    assert.equal(echo?.confirmation?.toolName, "application-one"); // UMG-3 tool-scoped confirmation
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test("factory: invalid endpoint string -> GATEWAY_ENDPOINT_INVALID (fail-closed)", async () => {
  const transport = createMcpClientCallTransport({ dokployServerId: "test-server-id", endpoint: "not-a-url" });
  const response = await transport.call({ toolName: "application-one", arguments: {}, mutating: false, confirmation: { toolName: "application-one" } });
  assert.equal(response.ok, false);
  assert.equal(response.status, 0);
  assert.equal(response.error, "GATEWAY_ENDPOINT_INVALID");
});
