// GCLOUD-01F — minimal provisioning primitives for the Guardian Cloud first-app flow.
//
// Purpose: complete the smallest provisioning path required by the REAL upstream
// contracts (package @dokploy/mcp@0.30.5 — generated/tools.js — matching the live
// 597-tool catalog observed via mcp_catalog in GCLOUD-01E):
//   project-all             (read)     -> list projects (reuse lookup by name)
//   project-create          (mutating) -> { name, description?, env? } -> projectId
//   environment-byProjectId (read)     -> list environments of one project (reuse lookup)
//   environment-create      (mutating) -> { name, projectId, description? } -> environmentId
//   application-saveGitProvider   (mutating) -> custom Git URL/branch/buildPath/watchPaths
//   application-saveBuildType     (mutating) -> buildType enum + nullable build fields
//   application-saveEnvironment   (mutating) -> env string + buildArgs/buildSecrets/createEnvFile
//
// Hard rules (mission GCLOUD-01F):
// - Wire arguments mirror the EXACT upstream zod schemas. Nullable required
//   fields are sent as null; no field outside the declared schema is sent.
// - ONE attempt per primitive: no retry, no fallback, no auto-recovery.
// - Honest classification: HTTP-level failures split 5xx -> UPSTREAM_ERROR vs
//   other -> EXECUTED_FAILED; MCP tool-level failures (HTTP 200 + isError:true,
//   the documented bridge swallow shape) are classified EXECUTED_FAILED with the
//   bounded upstream text. Success is never fabricated; an accepted create whose
//   ID cannot be extracted fails closed ("accepted but id absent").
// - Reuse-before-create: project/environment are looked up by the SuperTool-
//   defined identity (name) BEFORE any mutating call, so a rerun does not
//   arbitrarily duplicate resources. No exactly-once promise, no locks, no
//   database.
// - Secrets: env VALUES travel ONLY inside the application-saveEnvironment env
//   string (the actual upstream contract for container env). They are NEVER
//   echoed in results, steps, plans or logs — steps carry tool/outcome/error
//   metadata only.
// - No Guardian logic here: these primitives are consumed ONLY inside the
//   Guardian mutating boundary of engineering.guardian.app.deploy.
import { normalizeMcpResult, type VpsTransport, VpsTransportCall, VpsTransportResponse } from "./vpsTransport.ts";

// SuperTool-defined provisioning identity (overridable by the caller input).
export const PROVISION_IDENTITY_DEFAULTS = Object.freeze({
  projectName: "guardian-cloud",
  environmentName: "production",
  branch: "main",
  buildType: "nixpacks",
} as const);

// Real upstream enum (application-saveBuildType.buildType, @dokploy/mcp@0.30.5).
export const DOKPLOY_BUILD_TYPES = Object.freeze([
  "dockerfile",
  "heroku_buildpacks",
  "paketo_buildpacks",
  "nixpacks",
  "static",
  "railpack",
] as const);

export type DokployBuildType = (typeof DOKPLOY_BUILD_TYPES)[number];

// Real upstream customGitBranch pattern (application-saveGitProvider.customGitBranch).
export const DOKPLOY_BRANCH_PATTERN = /^[a-zA-Z0-9._\-/#]+$/;

export type ProvisionDeps = {
  transport: VpsTransport;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function boundedResultError(result: unknown): string {
  const text = isRecord(result) && nonEmptyString(result.text) ? result.text : JSON.stringify(result) ?? "";
  return text.slice(0, 300);
}

// Deterministic env text for application-saveEnvironment (sorted keys; the ONLY
// place env values are serialized — sent upstream, never echoed back).
export function buildEnvText(env: Record<string, string> | undefined): string {
  if (!env) return "";
  return Object.keys(env)
    .sort()
    .map((key) => `${key}=${env[key]}`)
    .join("\n");
}

export type PrimitiveCallResult = {
  ok: boolean;
  outcome: "EXECUTED_ACCEPTED" | "EXECUTED_FAILED" | "UPSTREAM_ERROR";
  status: number;
  durationMs: number;
  error: string | null;
  normalized: unknown;
  isError: boolean;
};

// Single-dispatch classifier shared by every provisioning primitive. `mutating`
// selects UMG-3 confirmation semantics at the transport layer (reads pass
// mutating:false exactly like the application-search revalidation).
export async function callProvisionPrimitive(
  deps: ProvisionDeps,
  toolName: string,
  args: Record<string, unknown>,
  mutating: boolean,
): Promise<PrimitiveCallResult> {
  const request: VpsTransportCall = {
    toolName,
    arguments: args,
    mutating,
    confirmation: { toolName },
  };
  let response: VpsTransportResponse;
  try {
    response = await deps.transport.call(request);
  } catch (error) {
    return {
      ok: false,
      outcome: "UPSTREAM_ERROR",
      status: 0,
      durationMs: 0,
      error: error instanceof Error ? error.message : String(error),
      normalized: null,
      isError: false,
    };
  }
  const isError = isRecord(response.result) && response.result.isError === true;
  const normalized = normalizeMcpResult(response.result);
  const outcome: PrimitiveCallResult["outcome"] = !response.ok
    ? response.status >= 500
      ? "UPSTREAM_ERROR"
      : "EXECUTED_FAILED"
    : isError
      ? "EXECUTED_FAILED"
      : "EXECUTED_ACCEPTED";
  return {
    ok: response.ok && !isError,
    outcome,
    status: response.status,
    durationMs: response.durationMs,
    error: isError ? boundedResultError(normalized) : response.error ?? null,
    normalized,
    isError,
  };
}

// Deterministic array extraction over the observed upstream wrapper shapes:
// plain array | { data: [...] } | { data: { items: [...] } } | { items: [...] }.
// success:false never becomes a valid list (null -> READ_FAILED).
function extractArrayPayload(payload: unknown): Record<string, unknown>[] | null {
  if (Array.isArray(payload)) return payload.filter(isRecord);
  if (!isRecord(payload)) return null;
  if (payload.success === false) return null;
  if (Array.isArray(payload.data)) return (payload.data as unknown[]).filter(isRecord);
  if (isRecord(payload.data)) {
    const data = payload.data as Record<string, unknown>;
    if (Array.isArray(data.items)) return (data.items as unknown[]).filter(isRecord);
    if (data.items !== undefined) return null;
  }
  if (Array.isArray(payload.items)) return (payload.items as unknown[]).filter(isRecord);
  if (payload.items !== undefined) return null;
  return null;
}

// Fail-closed ID extraction over the observed success wrappers
// ({success,message,data:{<field>}} or a direct record).
function extractIdField(normalized: unknown, field: "projectId" | "environmentId"): string | undefined {
  if (!isRecord(normalized)) return undefined;
  const candidates = [
    normalized[field],
    normalized.id,
    isRecord(normalized.data) ? (normalized.data as Record<string, unknown>)[field] : undefined,
    isRecord(normalized.data) ? (normalized.data as Record<string, unknown>).id : undefined,
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.length > 0) return candidate;
  }
  return undefined;
}

export type ProjectProvisionResult = {
  ok: boolean;
  reused: boolean;
  projectId: string | null;
  outcome: "REUSED" | "CREATED" | "READ_FAILED" | "EXECUTED_FAILED" | "UPSTREAM_ERROR";
  error: string | null;
};

export async function resolveOrCreateProject(
  deps: ProvisionDeps,
  input: { projectName: string; description?: string },
): Promise<ProjectProvisionResult> {
  const lookup = await callProvisionPrimitive(deps, "project-all", {}, false);
  if (!lookup.ok) {
    return { ok: false, reused: false, projectId: null, outcome: "READ_FAILED", error: lookup.error ?? `project-all outcome=${lookup.outcome} status=${lookup.status}` };
  }
  const records = extractArrayPayload(lookup.normalized);
  if (records === null) {
    return { ok: false, reused: false, projectId: null, outcome: "READ_FAILED", error: "project-all returned an unrecognized list shape" };
  }
  const match = records.find((record) => record.name === input.projectName && nonEmptyString(record.projectId));
  if (match) {
    return { ok: true, reused: true, projectId: String(match.projectId), outcome: "REUSED", error: null };
  }
  const createArgs: Record<string, unknown> = { name: input.projectName };
  if (nonEmptyString(input.description)) createArgs.description = input.description;
  const create = await callProvisionPrimitive(deps, "project-create", createArgs, true);
  const projectId = create.ok ? extractIdField(create.normalized, "projectId") : undefined;
  if (!create.ok) {
    return { ok: false, reused: false, projectId: null, outcome: create.outcome, error: create.error ?? `project-create outcome=${create.outcome}` };
  }
  if (projectId === undefined) {
    return { ok: false, reused: false, projectId: null, outcome: "EXECUTED_FAILED", error: "project-create accepted but projectId absent (fail-closed; no fabrication)" };
  }
  return { ok: true, reused: false, projectId, outcome: "CREATED", error: null };
}

export type EnvironmentProvisionResult = {
  ok: boolean;
  reused: boolean;
  environmentId: string | null;
  outcome: "REUSED" | "CREATED" | "READ_FAILED" | "EXECUTED_FAILED" | "UPSTREAM_ERROR";
  error: string | null;
};

export async function resolveOrCreateEnvironment(
  deps: ProvisionDeps,
  input: { projectId: string; environmentName: string },
): Promise<EnvironmentProvisionResult> {
  const lookup = await callProvisionPrimitive(deps, "environment-byProjectId", { projectId: input.projectId }, false);
  if (!lookup.ok) {
    return { ok: false, reused: false, environmentId: null, outcome: "READ_FAILED", error: lookup.error ?? `environment-byProjectId outcome=${lookup.outcome} status=${lookup.status}` };
  }
  const records = extractArrayPayload(lookup.normalized);
  if (records === null) {
    return { ok: false, reused: false, environmentId: null, outcome: "READ_FAILED", error: "environment-byProjectId returned an unrecognized list shape" };
  }
  const match = records.find((record) => record.name === input.environmentName && nonEmptyString(record.environmentId));
  if (match) {
    return { ok: true, reused: true, environmentId: String(match.environmentId), outcome: "REUSED", error: null };
  }
  const create = await callProvisionPrimitive(
    deps,
    "environment-create",
    { name: input.environmentName, projectId: input.projectId },
    true,
  );
  const environmentId = create.ok ? extractIdField(create.normalized, "environmentId") : undefined;
  if (!create.ok) {
    return { ok: false, reused: false, environmentId: null, outcome: create.outcome, error: create.error ?? `environment-create outcome=${create.outcome}` };
  }
  if (environmentId === undefined) {
    return { ok: false, reused: false, environmentId: null, outcome: "EXECUTED_FAILED", error: "environment-create accepted but environmentId absent (fail-closed; no fabrication)" };
  }
  return { ok: true, reused: false, environmentId, outcome: "CREATED", error: null };
}

export type SourceConfigStep = {
  step: "git" | "build" | "env";
  tool: string;
  ok: boolean;
  outcome: string;
  error: string | null;
};

export type SourceConfigResult = {
  ok: boolean;
  steps: SourceConfigStep[];
  failedStep: "git" | "build" | "env" | null;
  error: string | null;
};

// Sequential source configuration for a sourceType:"git" application. Each step
// is ONE dispatch; the sequence stops on the first failure (later steps are
// never attempted after a failed step — the deploy decision is upstream of
// this module and also gated on ok).
export async function configureApplicationSource(
  deps: ProvisionDeps,
  input: { applicationId: string; repoUrl: string; branch: string; buildPath: string | null; buildType: string; envText: string },
): Promise<SourceConfigResult> {
  const steps: SourceConfigStep[] = [];
  const fail = (step: SourceConfigStep, call: PrimitiveCallResult): SourceConfigResult => ({
    ok: false,
    steps,
    failedStep: step.step,
    error: step.error ?? `step=${step.step} outcome=${call.outcome} status=${call.status}`,
  });

  // 1. Git provider — schema: { applicationId, customGitBuildPath (string|null),
  //    customGitUrl (string|null), watchPaths (string[]|null), customGitBranch
  //    (pattern, min 1), enableSubmodules?, customGitSSHKeyId? }.
  const gitArgs: Record<string, unknown> = {
    applicationId: input.applicationId,
    customGitUrl: input.repoUrl,
    customGitBranch: input.branch,
    customGitBuildPath: input.buildPath ?? null,
    watchPaths: null,
  };
  const git = await callProvisionPrimitive(deps, "application-saveGitProvider", gitArgs, true);
  const gitStep: SourceConfigStep = { step: "git", tool: "application-saveGitProvider", ok: git.ok, outcome: git.outcome, error: git.error };
  steps.push(gitStep);
  if (!git.ok) return fail(gitStep, git);

  // 2. Build type — schema: { applicationId, buildType (enum), dockerfile,
  //    dockerContextPath, dockerBuildStage, herokuVersion, railpackVersion all
  //    string|null; publishDirectory?, isStaticSpa? }. Non-selected fields are
  //    null (nixpacks needs none of them).
  const build = await callProvisionPrimitive(
    deps,
    "application-saveBuildType",
    {
      applicationId: input.applicationId,
      buildType: input.buildType,
      dockerfile: null,
      dockerContextPath: null,
      dockerBuildStage: null,
      herokuVersion: null,
      railpackVersion: null,
    },
    true,
  );
  const buildStep: SourceConfigStep = { step: "build", tool: "application-saveBuildType", ok: build.ok, outcome: build.outcome, error: build.error };
  steps.push(buildStep);
  if (!build.ok) return fail(buildStep, build);

  // 3. Environment — schema: { applicationId, env (string|null), buildArgs
  //    (string|null), buildSecrets (string|null), createEnvFile (boolean) }.
  //    env carries the container env (including PORT evidence from the node
  //    detector); empty env is sent as null, never as an empty string.
  const env = await callProvisionPrimitive(
    deps,
    "application-saveEnvironment",
    {
      applicationId: input.applicationId,
      env: input.envText.length > 0 ? input.envText : null,
      buildArgs: null,
      buildSecrets: null,
      createEnvFile: false,
    },
    true,
  );
  const envStep: SourceConfigStep = { step: "env", tool: "application-saveEnvironment", ok: env.ok, outcome: env.outcome, error: env.error };
  steps.push(envStep);
  if (!env.ok) return fail(envStep, env);

  return { ok: true, steps, failedStep: null, error: null };
}

// GCLOUD-01F (LIVE chain): real HTTPS domain for the first app. Read evidence
// first (runApplicationDomain in the caller); when NO domain is evidenced, this
// composes the two real upstream mutations: domain-generateDomain {appName, serverId?} (serverId embeds the REAL destination IP — GCLOUD-01F finding)
// (idempotentHint; generates the traefik.me host for the app) then domain-create
// {host, applicationId, https:true, certificateType:'letsencrypt',
// domainType:'application'}. The host is taken ONLY from the upstream generate
// response (never invented); an unresolvable host or appName fails closed.
export type EnsureDomainResult = {
  ok: boolean;
  outcome: "GENERATED_AND_CREATED" | "APP_NAME_UNRESOLVED" | "GENERATE_FAILED" | "CREATE_FAILED";
  host: string | null;
  error: string | null;
};

export async function ensureApplicationDomain(
  deps: ProvisionDeps,
  input: { applicationId: string; appName: string | null; serverId?: string | null },
): Promise<EnsureDomainResult> {
  if (!nonEmptyString(input.appName)) {
    return { ok: false, outcome: "APP_NAME_UNRESOLVED", host: null, error: "application record carries no appName; refusing to invent a domain host" };
  }
  const generate = await callProvisionPrimitive(deps, "domain-generateDomain", nonEmptyString(input.serverId) ? { appName: input.appName, serverId: input.serverId } : { appName: input.appName }, true);
  if (!generate.ok) {
    return { ok: false, outcome: "GENERATE_FAILED", host: null, error: generate.error ?? `domain-generateDomain outcome=${generate.outcome}` };
  }
  // Deterministic host extraction over the observed success wrapper shapes.
  const hostCandidates: unknown[] = [];
  const push = (value: unknown): void => { hostCandidates.push(value); };
  push(generate.normalized);
  if (isRecord(generate.normalized)) {
    push((generate.normalized as Record<string, unknown>).host);
    push((generate.normalized as Record<string, unknown>).domain);
    push((generate.normalized as Record<string, unknown>).domainName);
    const data = (generate.normalized as Record<string, unknown>).data;
    push(data);
    if (isRecord(data)) {
      push((data as Record<string, unknown>).host);
      push((data as Record<string, unknown>).domain);
      push((data as Record<string, unknown>).domainName);
    }
  }
  let host: string | null = null;
  for (const candidate of hostCandidates) {
    if (typeof candidate === "string" && candidate.trim().length > 0) { host = candidate.trim(); break; }
  }
  if (host === null) {
    return { ok: false, outcome: "GENERATE_FAILED", host: null, error: "domain-generateDomain accepted but no host field could be extracted (fail-closed)" };
  }
  const create = await callProvisionPrimitive(
    deps,
    "domain-create",
    { host, applicationId: input.applicationId, https: true, certificateType: "letsencrypt", domainType: "application" },
    true,
  );
  if (!create.ok) {
    return { ok: false, outcome: "CREATE_FAILED", host, error: create.error ?? `domain-create outcome=${create.outcome}` };
  }
  return { ok: true, outcome: "GENERATED_AND_CREATED", host, error: null };
}
