// GCLOUD-01A — engineering "application-create" primitive (Sprint GCLOUD-01, step 2).
//
// Purpose: the MINIMAL mutating Dokploy primitive to create a NEW application,
// reusing the exact transport contract proven by src/vpsChangeSafe.ts (Base44
// mcpClientCall channel, injectable VpsTransport for offline tests).
//
// Hard rules (this sprint):
// - ONLY mutation primitive: "application-create". One attempt, no retry, no
//   fallback, no auto-recovery, no provider abstraction, no deployment engine.
// - execute defaults to false (PLAN): validation + plan only, ZERO transport
//   calls. A mutation happens ONLY when execute === true.
// - This primitive does NOT call Guardian itself. The Guardian gate will be
//   applied by the future guardian.app.deploy SuperTool (GCLOUD-01D), exactly
//   like runVpsChangeSafe wraps the redeploy mutation: executeGuardianIntent +
//   an adapter following the createGuardianVpsRedeployAdapter pattern, with
//   bind(action="create_application", approved===true) and apply = ONE dispatch
//   to "application-create". Nothing here claims governance it does not have.
// - Upstream schema honesty: the exact Dokploy field mapping for creation is
//   proven during the real E2E; an upstream refusal is surfaced verbatim as
//   UPSTREAM_ERROR / EXECUTED_FAILED — never a fabricated success.
// - Secrets: env VALUES are never echoed (values redacted in every output;
//   only env key names are observable). No SSH, no shell, no LLM.
import { normalizeMcpResult, type VpsTransport, VpsTransportCall, VpsTransportResponse } from "./vpsTransport.ts";

export const CREATE_MUTATION_ALLOWLIST = Object.freeze({
  create_application: Object.freeze({
    primitive: "application-create",
    risk: "high",
    approvalRequired: true,
  }),
} as const);

export const GUARDIAN_GATE_DOCUMENTATION = Object.freeze({
  gateOwner: "guardian.app.deploy (GCLOUD-01D SuperTool, NOT this primitive)",
  mechanism: "executeGuardianIntent (frozen memoryos-guardian-core v0.1.0) + adapter following src/guardianVpsAdapter.ts",
  bindChecks: ['action === "create_application"', "approved === true", "resolved source/name present", "no unresolved precheck conflict"],
  apply: "ONE dispatch to primitive application-create through the shared VpsTransport; revalidation read-only before dispatch",
  primitiveGuarantees: "this module never mutates ungoverned through the SuperTool path and never mutates without execute=true",
} as const);

export type ApplicationCreateInput = {
  name: string;
  source: string;
  startCommand: string;
  environmentId?: string;
  // GCLOUD-01F: optional upstream destination server (Dokploy requires serverId
  // when remoteServersOnly=true). Never hardcoded; wire-only when provided.
  serverId?: string;
  port?: number;
  env?: Record<string, string>;
};

export type ApplicationCreateOutcome =
  | "PLANNED"
  | "NEEDS_INPUT"
  | "EXECUTED_ACCEPTED"
  | "EXECUTED_FAILED"
  | "UPSTREAM_ERROR";

export type ApplicationCreateResult = {
  ok: boolean;
  outcome: ApplicationCreateOutcome;
  tool: "application-create";
  missing: string[];
  mutated: boolean;
  // PLAN echo only: env values redacted, never echoed.
  plan?: { primitive: string; redactedArguments: Record<string, unknown> };
  response?: { ok: boolean; status: number; durationMs: number; error?: string };
  createdApplicationId?: string;
  guardianGate: string;
};

const REDACTED = "[REDACTED]";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function validateApplicationCreateInput(
  input: unknown,
): { ok: true; value: ApplicationCreateInput } | { ok: false; missing: string[] } {
  const missing: string[] = [];
  if (!isRecord(input)) return { ok: false, missing: ["name", "source", "startCommand"] };
  if (!nonEmptyString(input.name)) missing.push("name");
  if (!nonEmptyString(input.source)) missing.push("source");
  if (!nonEmptyString(input.startCommand)) missing.push("startCommand");
  if (input.port !== undefined && (typeof input.port !== "number" || !Number.isInteger(input.port) || input.port < 1 || input.port > 65_535)) missing.push("port");
  if (input.serverId !== undefined && (typeof input.serverId !== "string" || input.serverId.trim().length === 0)) missing.push("serverId");
  if (input.env !== undefined && !isRecord(input.env)) missing.push("env");
  if (missing.length > 0) return { ok: false, missing };
  const value: ApplicationCreateInput = {
    name: (input.name as string).trim(),
    source: (input.source as string).trim(),
    startCommand: (input.startCommand as string).trim(),
  };
  if (input.port !== undefined) value.port = input.port as number;
  if (input.serverId !== undefined && typeof input.serverId === "string" && input.serverId.trim().length > 0) value.serverId = input.serverId.trim();
  if (input.env !== undefined) {
    value.env = {};
    for (const [key, val] of Object.entries(input.env as Record<string, unknown>)) {
      if (typeof val !== "string") return { ok: false, missing: ["env"] };
      value.env[key] = val;
    }
  }
  return { ok: true, value };
}

function redactEnv(env: Record<string, string> | undefined): Record<string, string> {
  const output: Record<string, string> = {};
  if (env) for (const key of Object.keys(env)) output[key] = REDACTED;
  return output;
}

// Bounded view of an upstream MCP tool-level failure (HTTP 200 + isError): the
// text the upstream tool returned, capped, so failures are diagnosable without echo risk.
function boundedResultError(result: unknown): string {
  const text = isRecord(result) && nonEmptyString(result.text) ? result.text : JSON.stringify(result) ?? "";
  return text.slice(0, 300);
}

function extractCreatedApplicationId(result: unknown): string | undefined {
  if (!isRecord(result)) return undefined;
  const candidate = result.applicationId ?? result.id ?? (isRecord(result.data) ? result.data.applicationId ?? result.data.id : undefined);
  return typeof candidate === "string" && candidate.length > 0 ? candidate : undefined;
}

export type ApplicationCreateDeps = {
  transport: VpsTransport;
  now?: () => number;
};

export async function runApplicationCreate(
  toolName: string,
  input: ApplicationCreateInput & { execute?: boolean },
  deps: ApplicationCreateDeps,
): Promise<ApplicationCreateResult> {
  const validated = validateApplicationCreateInput(input);
  if (!validated.ok) {
    return {
      ok: false,
      outcome: "NEEDS_INPUT",
      tool: "application-create",
      missing: validated.missing,
      mutated: false,
      guardianGate: "guardian.app.deploy (GCLOUD-01D)",
    };
  }
  // Real upstream contract (dokploy mcp_catalog, 597 tools; GCLOUD-01E real E2E):
  // application-create = POST /application.create { name, appName?, description?,
  // environmentId (required), serverId?, sourceType? } with additionalProperties:false.
  // source/startCommand/port/env are PLAN semantics of this primitive and are NOT
  // part of the upstream create schema (source/build/env configuration lives in
  // provider-specific primitives outside this allowlist).
  const createArgs: Record<string, unknown> = {
    name: validated.value.name,
    environmentId: input.environmentId,
    sourceType: "git",
  };
  // GCLOUD-01F: serverId reaches the upstream wire ONLY when the caller provided
  // it; absent -> byte-identical arguments to the pre-01F contract (exact-args test).
  if (validated.value.serverId !== undefined) createArgs.serverId = validated.value.serverId;
  const planEcho: Record<string, unknown> = {
    name: validated.value.name,
    source: validated.value.source,
    startCommand: validated.value.startCommand,
    environmentId: input.environmentId,
    sourceType: "git",
    port: validated.value.port,
    env: redactEnv(validated.value.env),
  };
  if (validated.value.serverId !== undefined) planEcho.serverId = validated.value.serverId;

  if (input.execute !== true) {
    return {
      ok: true,
      outcome: "PLANNED",
      tool: "application-create",
      missing: [],
      mutated: false,
      plan: { primitive: "application-create", redactedArguments: planEcho },
      guardianGate: "guardian.app.deploy (GCLOUD-01D)",
    };
  }

  // Upstream contract gate (GCLOUD-01E): the create schema REQUIRES environmentId.
  // Absent here -> honest NEEDS_INPUT before ANY transport call (zero mutation).
  if (!nonEmptyString(input.environmentId)) {
    return {
      ok: false,
      outcome: "NEEDS_INPUT",
      tool: "application-create",
      missing: ["environmentId"],
      mutated: false,
      guardianGate: "guardian.app.deploy (GCLOUD-01D)",
    };
  }

  const request: VpsTransportCall = {
    toolName: "application-create",
    arguments: createArgs,
    mutating: true,
    confirmation: { toolName: "application-create" },
  };
  let response: VpsTransportResponse;
  try {
    response = await deps.transport.call(request);
  } catch (error) {
    return {
      ok: false,
      outcome: "UPSTREAM_ERROR",
      tool: "application-create",
      missing: [],
      mutated: false,
      response: { ok: false, status: 0, durationMs: 0, error: error instanceof Error ? error.message : String(error) },
      guardianGate: "guardian.app.deploy (GCLOUD-01D)",
    };
  }
  // MCP tool-level failures arrive as HTTP 200 + isError (the bridge only surfaces
  // thrown transport errors): classify them honestly instead of fabricating
  // acceptance (GCLOUD-01E real E2E evidence: schema rejection came back as 200).
  const isErrorResult = isRecord(response.result) && response.result.isError === true;
  const normalizedResult = normalizeMcpResult(response.result);
  const createdApplicationId = isErrorResult ? undefined : extractCreatedApplicationId(normalizedResult);
  return {
    ok: response.ok && !isErrorResult,
    outcome: !response.ok ? (response.status >= 500 ? "UPSTREAM_ERROR" : "EXECUTED_FAILED") : isErrorResult ? "EXECUTED_FAILED" : "EXECUTED_ACCEPTED",
    tool: "application-create",
    missing: [],
    mutated: response.ok && !isErrorResult,
    response: { ok: response.ok, status: response.status, durationMs: response.durationMs, error: isErrorResult ? boundedResultError(normalizedResult) : response.error },
    createdApplicationId,
    guardianGate: "guardian.app.deploy (GCLOUD-01D)",
  };
}
