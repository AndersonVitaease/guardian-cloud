// MVP EXTERNO 02 — GUARDIAN CLOUD minimal external entry (front door ONLY).
//
// POST /deploy  body: { "repositoryUrl": "https://github.com/<owner>/<repo>", "appName": "<name>" }
//        -> 200 { "status": "LIVE",     "url": "https://..." }
//        -> 200 { "status": "FAILED",   "reason": "<bounded>" }
//        -> 200 { "status": "DEPLOYING" }
//
// Smallest possible external entry in front of the EXISTING Guardian Cloud
// capability. It reuses, without any new service/queue/database/framework:
// - the existing HTTP process (src/server.ts dispatch, next to image/auth routes);
// - the exact executor the registered tool uses: runGuardianAppDeploy (with the
//   host-injected VpsTransport when provided) — the full Guardian bind/apply gate
//   still runs;
// - the existing bearer-token model, injected by the host as deps.authenticate
//   (authenticateBearer, engineering:write) — this route never imports policy.
//
// Security contract (fail-closed):
// - body accepts EXACTLY {repositoryUrl, appName} — any other key (serverId,
//   environmentId, applicationId, shell, edge config...) is rejected before
//   any work happens;
// - repositoryUrl must be a https://github.com/<owner>/<repo> URL (GitHub only);
// - the internal deployment identity (environmentId/serverId/env) is resolved from
//   the operator environment HERE (ENG_MCP_DEPLOY_*; 500 DEPLOY_CONFIG_MISSING when
//   absent), never by the caller; no secrets are accepted via the request;
// - Guardian Core is untouched: approval semantics stay inside the executor.
// No new infrastructure: the existing async HTTP handler simply holds the
// request open until the existing function resolves (no queue/job system).

import type { IncomingMessage, ServerResponse } from "node:http";
import type { VpsTransport } from "./vpsTransport.ts";
import { runGuardianAppDeploy, type GuardianAppDeployResult } from "./guardianAppDeploy.ts";

export const DEPLOY_ENTRY = {
  path: "/deploy",
  maxBodyBytes: 4096,
  maxReasonChars: 200,
  maxFileChars: 65536,
  fetchTimeoutMs: 10_000,
  // GitHub only in this phase.
  githubUrlPattern: /^https:\/\/github\.com\/[A-Za-z0-9][A-Za-z0-9_.-]{0,38}\/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/,
  appNamePattern: /^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$/,
  // INTERNAL deployment identity (environmentId/serverId) is NOT stored here and has
  // NO compiled default: it is resolved ONLY from ENG_MCP_DEPLOY_ENVIRONMENT_ID /
  // ENG_MCP_DEPLOY_SERVER_ID at request time (fail-closed 500 DEPLOY_CONFIG_MISSING
  // when absent; never caller-supplied, never echoed).
  env: { PORT: "3000" },
  // Bounded detection-evidence fetch (exactly what nodeAppDetector can use:
  // package.json startCommand + documented PORT + common entry files).
  snapshotPaths: [".env.example", "server.js", "index.js", "app.js", "main.js", "index.ts", "server.ts", "app.ts", "src/index.js", "src/server.js", "src/app.js", "src/index.ts", "src/server.ts", "src/main.js"],
} as const;

export type DeployEntryDeps = {
  repositoryId: string;
  // Host-supplied authentication: returns the authenticated subject or THROWS an
  // error carrying a stable .code (same EngineeringError contract as before).
  // Absent authenticate -> fail-closed 401 AUTHENTICATION_REQUIRED (never open).
  authenticate?: (authorization: string | undefined) => unknown;
  // Optional host-injected transport; when absent runGuardianAppDeploy self-wires
  // the neutral transport from the operator environment (no literals here).
  transport?: VpsTransport;
  // Injectable for tests only (mock/fake validation of this new code).
  fetchSnapshot?: (ownerRepo: string, filePath: string) => Promise<string | null>;
  runDeploy?: typeof runGuardianAppDeploy;
};

export function normalizeRepositoryUrl(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  let url = raw.trim();
  while (url.endsWith("/")) url = url.slice(0, -1);
  if (url.toLowerCase().endsWith(".git")) url = url.slice(0, -4);
  return DEPLOY_ENTRY.githubUrlPattern.test(url) ? url : null;
}

async function defaultFetchSnapshot(ownerRepo: string, filePath: string): Promise<string | null> {
  try {
    const res = await fetch(`https://raw.githubusercontent.com/${ownerRepo}/HEAD/${filePath}`, { signal: AbortSignal.timeout(DEPLOY_ENTRY.fetchTimeoutMs) });
    if (!res.ok) return null;
    const text = await res.text();
    return text.length > DEPLOY_ENTRY.maxFileChars ? null : text;
  } catch {
    return null;
  }
}

function respondJson(response: ServerResponse, status: number, payload: unknown): void {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(payload));
}

function boundedReason(reason: string): string {
  const trimmed = reason.replace(/\s+/g, " ").trim();
  return trimmed.length > DEPLOY_ENTRY.maxReasonChars ? `${trimmed.slice(0, DEPLOY_ENTRY.maxReasonChars - 3)}...` : trimmed;
}

// Deterministic mapping from the executor's honest statuses to the minimal
// public contract. LIVE is never invented: LIVE requires an evidenced URL.
export function mapDeployResultToHttp(result: GuardianAppDeployResult): { status: string; url?: string; reason?: string } {
  switch (result.status) {
    case "LIVE":
      return result.url ? { status: "LIVE", url: result.url } : { status: "FAILED", reason: "LIVE_WITHOUT_URL" };
    case "DEPLOYING":
    case "DEPLOYED_AWAITING_DOMAIN":
      return { status: "DEPLOYING" };
    case "NEEDS_INPUT":
      return { status: "FAILED", reason: boundedReason(`NEEDS_INPUT: ${result.missing.join(", ")}`) };
    case "FAILED":
      return { status: "FAILED", reason: boundedReason(result.note ?? "deploy failed") };
    default:
      // PLANNED / APPROVAL_REQUIRED / UNKNOWN — fail closed, never LIVE.
      return { status: "FAILED", reason: boundedReason(`UNEXPECTED_STATE_${result.status}${result.note ? `: ${result.note}` : ""}`) };
  }
}

// Dispatch hook for src/server.ts: returns false when the request is not for
// this route (the caller then continues its normal dispatch / 404).
export async function handleDeployRequest(request: IncomingMessage, response: ServerResponse, deps: DeployEntryDeps): Promise<boolean> {
  if (request.method !== "POST" || request.url?.split("?")[0] !== DEPLOY_ENTRY.path) return false;
  // Host-supplied authentication (same bearer model as /mcp; deploy requires the
  // write scope). Fail-closed: when the host injects no authenticate function the
  // route is NEVER open — 401 AUTHENTICATION_REQUIRED.
  if (typeof deps.authenticate !== "function") {
    respondJson(response, 401, { status: "FAILED", reason: "AUTHENTICATION_REQUIRED" });
    return true;
  }
  try {
    deps.authenticate(request.headers.authorization);
  } catch (error) {
    const code = typeof error === "object" && error !== null && "code" in error ? (error as { code: unknown }).code : null;
    respondJson(response, 401, { status: "FAILED", reason: typeof code === "string" ? code : "AUTHENTICATION_REQUIRED" });
    return true;
  }
  let text: string;
  try {
    const chunks: Buffer[] = [];
    let size = 0;
    for await (const chunk of request) {
      size += (chunk as Buffer).length;
      if (size > DEPLOY_ENTRY.maxBodyBytes) {
        respondJson(response, 413, { status: "FAILED", reason: "BODY_TOO_LARGE" });
        return true;
      }
      chunks.push(chunk as Buffer);
    }
    text = Buffer.concat(chunks).toString("utf8");
  } catch {
    respondJson(response, 400, { status: "FAILED", reason: "BODY_READ_FAILED" });
    return true;
  }
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    respondJson(response, 400, { status: "FAILED", reason: "BODY_INVALID_JSON" });
    return true;
  }
  // STRICT public contract: exactly {repositoryUrl, appName}. Anything else —
  // including internal identifiers — is refused before any work happens.
  if (typeof body !== "object" || body === null || Array.isArray(body) || Object.keys(body).sort().join(",") !== "appName,repositoryUrl") {
    respondJson(response, 400, { status: "FAILED", reason: "BODY_KEYS_INVALID" });
    return true;
  }
  const record = body as Record<string, unknown>;
  const repositoryUrl = normalizeRepositoryUrl(record.repositoryUrl);
  const appName = typeof record.appName === "string" ? record.appName.trim() : "";
  if (repositoryUrl === null) {
    respondJson(response, 400, { status: "FAILED", reason: "REPOSITORY_URL_INVALID" });
    return true;
  }
  if (!DEPLOY_ENTRY.appNamePattern.test(appName)) {
    respondJson(response, 400, { status: "FAILED", reason: "APP_NAME_INVALID" });
    return true;
  }
  try {
    // Fail-closed configuration: the internal deployment identity is resolved
    // from the operator environment at request time — never caller-supplied,
    // never defaulted, never echoed.
    const environmentId = process.env.ENG_MCP_DEPLOY_ENVIRONMENT_ID;
    const serverId = process.env.ENG_MCP_DEPLOY_SERVER_ID;
    const missingConfig: string[] = [];
    if (typeof environmentId !== "string" || environmentId.length === 0) missingConfig.push("ENG_MCP_DEPLOY_ENVIRONMENT_ID");
    if (typeof serverId !== "string" || serverId.length === 0) missingConfig.push("ENG_MCP_DEPLOY_SERVER_ID");
    if (missingConfig.length > 0) {
      respondJson(response, 500, { status: "FAILED", reason: "DEPLOY_CONFIG_MISSING", missing: missingConfig });
      return true;
    }
    const ownerRepo = repositoryUrl.slice("https://github.com/".length);
    const fetchSnapshot = deps.fetchSnapshot ?? defaultFetchSnapshot;
    const runDeploy = deps.runDeploy ?? runGuardianAppDeploy;
    const [packageJsonText, ...contents] = await Promise.all([
      fetchSnapshot(ownerRepo, "package.json"),
      ...DEPLOY_ENTRY.snapshotPaths.map((filePath) => fetchSnapshot(ownerRepo, filePath)),
    ]);
    const files: Record<string, string> = {};
    DEPLOY_ENTRY.snapshotPaths.forEach((filePath, index) => {
      const content = contents[index];
      if (typeof content === "string") files[filePath] = content;
    });
    // INTERNAL invocation — same shape as the proven MVP 01 SuperTool run; the
    // caller never supplies (or even sees) any of these values. The full
    // Guardian gate (bind/apply + revalidation) still runs inside the executor.
    const result = await runDeploy({
      name: appName,
      source: repositoryUrl,
      approved: true,
      execute: true,
      env: { ...DEPLOY_ENTRY.env },
      environmentId,
      serverId,
      projectSnapshot: { packageJsonText, files },
    }, { transport: deps.transport });
    respondJson(response, 200, mapDeployResultToHttp(result));
  } catch (error) {
    respondJson(response, 500, { status: "FAILED", reason: boundedReason(`DEPLOY_ENTRY_ERROR: ${error instanceof Error ? error.message : String(error)}`) });
  }
  return true;
}
