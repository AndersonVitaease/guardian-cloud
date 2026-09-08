// Neutral transport for Guardian Cloud extraction — no operational endpoints or IDs (host supplies them).
//
// Contents (moved VERBATIM from src/vpsChangeSafe.ts during the Guardian Cloud decoupling):
// the VpsTransport contract (VpsTransport / VpsTransportCall / VpsTransportResponse), the
// mcp_execute result normalizer (parseJsonTextIfValid + normalizeMcpResult) and the redaction
// helpers used by the transport, plus the default Base44 mcpClientCall transport factory.
// The factory is NEUTRAL: dokployServerId and endpoint come ONLY from the caller options or
// the operator environment (ENG_MCP_VPS_DOKPLOY_SERVER_ID / ENG_MCP_AGENT_MEMORY_ENDPOINT) —
// never from a compiled-in default; a missing or invalid endpoint fails closed with
// GATEWAY_ENDPOINT_INVALID (never invented, zero network egress).
import { readFile } from "node:fs/promises";

export type VpsTransportCall = {
  toolName: string;
  arguments: Record<string, unknown>;
  mutating: boolean;
  confirmation: { toolName: string };
};

export type VpsTransportResponse = {
  ok: boolean;
  status: number;
  result?: unknown;
  error?: string;
  durationMs: number;
};

export interface VpsTransport {
  name: string;
  call(request: VpsTransportCall): Promise<VpsTransportResponse>;
}

const DEFAULT_CALL_TIMEOUT_MS = 20_000;
const MAX_CALL_TIMEOUT_MS = 30_000;
const MAX_RESPONSE_BYTES = 65_536;
const REDACTED = "[REDACTED]";
// Key-based scrub only: this module never holds credential material. "env" is matched
// exactly (^env$ / envvars) so unrelated keys like "environmentId" pass through.
const SENSITIVE_KEY_PATTERN = /authorization|token|secret|api_?key|password|cookie|bearer|envvars|^env$/i;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function redactSensitive(value: unknown, depth = 0): unknown {
  if (typeof value === "string") return value;
  if (depth > 12) return null;
  if (Array.isArray(value)) return value.slice(0, 500).map((item) => redactSensitive(item, depth + 1));
  if (isRecord(value)) {
    const output: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(value)) {
      output[key] = SENSITIVE_KEY_PATTERN.test(key) ? REDACTED : redactSensitive(child, depth + 1);
    }
    return output;
  }
  return value;
}

// Accepts either a bare array or { applications: [...] } from application-search.
// SPRINT VPS-SUPERTOOLS-01D: mcp_execute returns the raw MCP callTool envelope. Unwrap it
// deterministically BEFORE the extractors run: structuredContent wins; JSON text payloads are
// parsed; plain text (e.g. logs) is preserved without invented parsing; ambiguous envelopes are
// returned unchanged so downstream extractors fail safe (UPSTREAM_ERROR). Non-records pass through.
function parseJsonTextIfValid(text: string): { json: true; value: unknown } | { json: false; value: string } {
  try {
    return { json: true, value: JSON.parse(text) };
  } catch {
    return { json: false, value: text };
  }
}

export function normalizeMcpResult(result: unknown): unknown {
  if (!isRecord(result)) return result;
  if (isRecord(result.structuredContent) || Array.isArray(result.structuredContent)) return result.structuredContent;
  if (!Array.isArray(result.content)) return result;
  const jsonValues: unknown[] = [];
  const textValues: string[] = [];
  for (const element of result.content) {
    if (!isRecord(element) || element.type !== "text" || typeof element.text !== "string") continue;
    const parsed = parseJsonTextIfValid(element.text);
    if (parsed.json) jsonValues.push(parsed.value);
    else textValues.push(parsed.value);
  }
  if (jsonValues.length === 1 && textValues.length === 0) return jsonValues[0];
  if (jsonValues.length === 0 && textValues.length > 0) return { text: textValues.join("\n") };
  return result;
}

// Default transport: the existing Base44 mcpClientCall executor, over the same
// s2s channel as engineering.memory.* (endpoint env + credential file). The token
// is attached server-side, never logged and never returned.
export function createMcpClientCallTransport(options: { dokployServerId?: string; endpoint?: string; timeoutMs?: number } = {}): VpsTransport {
  const serverId = options.dokployServerId ?? process.env.ENG_MCP_VPS_DOKPLOY_SERVER_ID;
  const timeoutMs = Math.min(Math.max(options.timeoutMs ?? DEFAULT_CALL_TIMEOUT_MS, 1), MAX_CALL_TIMEOUT_MS);
  return {
    name: "base44-mcpClientCall",
    async call(request: VpsTransportCall): Promise<VpsTransportResponse> {
      const start = Date.now();
      const endpoint = options.endpoint ?? process.env.ENG_MCP_AGENT_MEMORY_ENDPOINT;
      if (typeof endpoint !== "string" || endpoint.length === 0) {
        // Fail-closed: without an evidenced endpoint this transport never invents one.
        return { ok: false, status: 0, error: "GATEWAY_ENDPOINT_INVALID", durationMs: Date.now() - start };
      }
      let bridgeUrl: string;
      try {
        const u = new URL(endpoint);
        bridgeUrl = u.pathname.endsWith("/agentMemoryBridge") ? endpoint : `${u.origin}/functions/agentMemoryBridge`;
      } catch {
        return { ok: false, status: 0, error: "GATEWAY_ENDPOINT_INVALID", durationMs: Date.now() - start };
      }
      const headers: Record<string, string> = { "content-type": "application/json" };
      const credentialFile = process.env.ENG_MCP_AGENT_MEMORY_CREDENTIAL_FILE;
      if (credentialFile) {
        try {
          const token = (await readFile(credentialFile, "utf8")).trim();
          if (token) headers["x-agent-memory-token"] = token;
        } catch {
          /* proceed without token; the upstream channel decides authentication */
        }
      }
      let body: string;
      try {
        body = JSON.stringify({
          serverId,
          operation: "mcp_execute",
          toolName: request.toolName,
          arguments: request.arguments,
          confirmation: { toolName: request.toolName }, // UMG-3 tool-scoped confirmation
        });
      } catch {
        return { ok: false, status: 0, error: "REQUEST_BODY_INVALID", durationMs: Date.now() - start };
      }
      let response: Response;
      try {
        response = await fetch(bridgeUrl, {
          method: "POST",
          headers,
          body,
          redirect: "manual", // never follow redirects away from the allowlisted origin
          signal: AbortSignal.timeout(timeoutMs),
        });
      } catch (error) {
        return {
          ok: false,
          status: 0,
          error: error instanceof Error && error.name === "TimeoutError" ? "GATEWAY_TIMEOUT" : "GATEWAY_NETWORK_ERROR",
          durationMs: Date.now() - start,
        };
      }
      let raw = "";
      try {
        const reader = response.body?.getReader();
        if (reader) {
          const decoder = new TextDecoder("utf-8", { fatal: false });
          const chunks: Buffer[] = [];
          let bytes = 0;
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            if (value) {
              bytes += value.byteLength;
              chunks.push(Buffer.from(value));
              if (bytes >= MAX_RESPONSE_BYTES) {
                void reader.cancel().catch(() => {});
                break;
              }
            }
          }
          raw = decoder.decode(Buffer.concat(chunks));
        }
      } catch {
        /* bounded read failure -> empty body */
      }
      let parsed: unknown = null;
      if (raw) {
        try {
          parsed = JSON.parse(raw);
        } catch {
          parsed = null;
        }
      }
      const okStatus = response.status >= 200 && response.status < 300;
      const parsedOk = isRecord(parsed) && parsed.ok === true;
      const parsedFailed = isRecord(parsed) && parsed.ok === false;
      const errText = isRecord(parsed) && typeof parsed.error === "string" ? parsed.error : null;
      const errObj = isRecord(parsed) && isRecord(parsed.error) ? parsed.error : null;
      const errCode = errObj && typeof errObj.code === "string" ? errObj.code : null;
      const errMsg = errObj && typeof errObj.message === "string" ? errObj.message : null;
      const base = errCode ?? errText ?? `HTTP_${response.status}`;
      const detail = errMsg && !base.includes(errMsg) ? `${base}: ${errMsg}` : base;
      if (!okStatus || parsedFailed || errText !== null) {
        return { ok: false, status: response.status, error: detail, durationMs: Date.now() - start };
      }
      return {
        ok: true,
        status: response.status,
        result: redactSensitive(isRecord(parsed) && parsedOk ? (parsed.result ?? null) : null),
        durationMs: Date.now() - start,
      };
    },
  };
}
