// GCLOUD-01D — engineering "guardian.app.deploy" SuperTool (composition only).
//
// Purpose: compose the MINIMAL governed path proven by GCLOUD-01A/01B/01C:
//   project snapshot -> detectNodeApp() -> PLAN -> Guardian approval ->
//   application-create (single mutating boundary) -> application-deploy ->
//   post-validation (application-one health) -> application-domain -> LIVE + URL.
//
// Hard rules (mission GCLOUD-01D):
// - NO new deployment engine, no build engine, no queue, no database, no
//   control plane: existing capabilities are REUSED (application-create,
//   application-deploy via the shared VpsTransport allowlist, application-one
//   health read, application-domain read, nodeAppDetector evidence logic).
// - Creation happens ONLY inside the Guardian mutating boundary (apply),
//   mirroring createGuardianVpsRedeployAdapter: bind = read-only fail-closed
//   eligibility over a data-only intent; apply = ONE application-create
//   dispatch after re-proving the precheck with a read-only application-search.
//   applicationCreate(execute=true) is NEVER reached before the Guardian.
// - execute defaults to false (PLAN): detect + plan only, ZERO transport.
// - execute=true with approved!==true -> Guardian bind refuses
//   (APPROVAL_GATE_NOT_SATISFIED) -> status APPROVAL_REQUIRED, zero mutation.
// - Honest states: LIVE requires create accepted + deploy ok + health evidence
//   (applicationStatus running) + domain READY with an evidenced URL.
//   Healthy app with pending domain -> DEPLOYED_AWAITING_DOMAIN (url:null —
//   NEVER an invented URL). Guardian Core is NEVER modified here.
// - Secrets: env VALUES never appear in plan or output (keys only + [REDACTED]).
// - Idempotency honesty: no exactly-once. A read-only application-search
//   precheck refuses when the same name is already evidenced; the residual
//   race window is documented, not hidden.
import type { VpsTransport, VpsTransportResponse } from "./vpsTransport.ts";
import { createMcpClientCallTransport, normalizeMcpResult } from "./vpsTransport.ts";
import { detectNodeApp, type NodeAppDetectorResult } from "./nodeAppDetector.ts";
import { runApplicationCreate } from "./applicationCreate.ts";
import { runApplicationDomain } from "./applicationDomain.ts";
import { buildEnvText, configureApplicationSource, DOKPLOY_BRANCH_PATTERN, DOKPLOY_BUILD_TYPES, ensureApplicationDomain, PROVISION_IDENTITY_DEFAULTS, resolveOrCreateEnvironment, resolveOrCreateProject } from "./appProvision.ts";
import {
  loadGuardianCore,
  type DomainAdapter,
  type GuardianCoreModule,
  type GuardianResult,
} from "./guardianCoreLoad.ts";

export type GuardianAppDeployStatus =
  | "PLANNED"
  | "NEEDS_INPUT"
  | "APPROVAL_REQUIRED"
  | "DEPLOYING"
  | "DEPLOYED_AWAITING_DOMAIN"
  | "FAILED"
  | "LIVE"
  | "UNKNOWN";

export type GuardianAppDeployInput = {
  name: string;
  source: string;
  projectSnapshot?: { packageJsonText?: string | null; files?: Record<string, string> };
  env?: Record<string, string>;
  environmentId?: string;
  // GCLOUD-01F: optional destination server for application-create (required
  // upstream when remoteServersOnly=true). Caller-supplied only — never
  // hardcoded, never auto-discovered; part of the Guardian-bound intent.
  serverId?: string;
  projectName?: string;
  environmentName?: string;
  branch?: string;
  buildType?: string;
  approved?: boolean;
  execute?: boolean;
};

// GCLOUD-01F: honest summary of the governed provisioning sequence.
export type GuardianAppDeployProvisioningSummary = {
  projectId: string | null;
  projectReused: boolean | null;
  environmentId: string | null;
  environmentReused: boolean | null;
  sourceConfigured: boolean | null;
  buildConfigured: boolean | null;
  envConfigured: boolean | null;
  domainGenerated: boolean | null;
  domainHost: string | null;
  steps: { step: string; tool: string; ok: boolean; outcome: string; error: string | null }[];
};

export type GuardianAppDeployResult = {
  ok: boolean;
  status: GuardianAppDeployStatus;
  tool: "guardian.app.deploy";
  name: string;
  detection: NodeAppDetectorResult | null;
  missing: string[];
  plan: { primitive: "application-create"; startCommand: string; port: number | null; portStrategy: string; envKeys: string[]; provisioning: { mode: string; projectName: string; environmentName: string; branch: string; buildType: string; source: string; serverId?: string } } | null;
  provisioning: GuardianAppDeployProvisioningSummary | null;
  guardian: { outcome: string; stage?: string; refusal?: string; reasons: string[] } | null;
  create: { outcome: string; applicationId?: string; response?: { ok: boolean; status: number; error?: string } } | null;
  deploy: { dispatched: boolean; ok: boolean; status: number; error?: string } | null;
  health: { evidence: string; healthy: boolean } | null;
  domain: { status: string; url: string | null; https: boolean | null; host: string | null } | null;
  url: string | null;
  mutated: boolean;
  guardianGate: string;
  note: string | null;
};

export const GUARDIAN_APP_DEPLOY_GATE =
  "executeGuardianIntent (frozen memoryos-guardian-core v0.1.0) + adapter following src/guardianVpsAdapter.ts; bind(action='create_application', approved===true); apply = the governed provisioning sequence (project/environment reuse-or-create, application-create, git/build/env configuration) followed by ONE application-deploy OUTSIDE the boundary — a documented multi-mutation sequence with partial-result points, never presented as one atomic mutation";

const REDACTED = "[REDACTED]";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asNonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function redactEnv(env: Record<string, string> | undefined): Record<string, string> | undefined {
  if (env === undefined) return undefined;
  const redacted: Record<string, string> = {};
  for (const key of Object.keys(env)) redacted[key] = REDACTED;
  return redacted;
}

function envKeys(env: Record<string, string> | undefined): string[] {
  return env === undefined ? [] : Object.keys(env).sort();
}

function makeResult(overrides: Partial<GuardianAppDeployResult>): GuardianAppDeployResult {
  return {
    ok: false,
    status: "UNKNOWN",
    tool: "guardian.app.deploy",
    name: "",
    detection: null,
    missing: [],
    plan: null,
    guardian: null,
    create: null,
    deploy: null,
    health: null,
    domain: null,
    url: null,
    mutated: false,
    guardianGate: GUARDIAN_APP_DEPLOY_GATE,
    note: null,
    ...overrides,
  };
}

// GCLOUD-01F: deterministic projection of the provisioning dispatch record into
// the honest result summary (never echoes env values; steps carry metadata only).
function provisioningSummary(record: NonNullable<GuardianAppDeployDispatchRecord["provisioning"]>): GuardianAppDeployProvisioningSummary {
  const stepOk = (step: string): boolean | null => {
    const found = record.sourceSteps.find((entry) => entry.step === step);
    return found === undefined ? null : found.ok;
  };
  return {
    projectId: record.projectId,
    projectReused: record.projectReused,
    environmentId: record.environmentId,
    environmentReused: record.environmentReused,
    sourceConfigured: stepOk("git"),
    buildConfigured: stepOk("build"),
    envConfigured: stepOk("env"),
    domainGenerated: record.domainGenerated ?? null,
    domainHost: record.domainHost ?? null,
    steps: record.sourceSteps,
  };
}

// Data-only intent: nothing that could expand authority flows through bind.
export type GuardianAppDeployIntent = {
  action: "create_application";
  approved: boolean;
  name: string;
  source: string;
  // GCLOUD-01F: the destination server is part of the approved intent — bind
  // forges the proposal from it, so the destination cannot be silently swapped
  // between approval and execution.
  serverId?: string;
  observedAt: number;
};

export type GuardianAppDeployProposal = {
  name: string;
  source: string;
  startCommand: string;
  environmentId?: string;
  serverId?: string;
  projectName?: string;
  environmentName?: string;
  branch?: string;
  buildType?: string;
  port: number | null;
  env: Record<string, string> | undefined;
};

export type GuardianAppDeployDispatchRecord = {
  create: { outcome: string; ok: boolean; applicationId?: string; response?: { ok: boolean; status: number; error?: string } } | null;
  revalidation: { ok: boolean; status: number; error: string | null } | null;
  provisioning: {
    projectId: string | null;
    projectReused: boolean | null;
    projectOutcome: string | null;
    environmentId: string | null;
    environmentReused: boolean | null;
    environmentOutcome: string | null;
    sourceSteps: { step: string; tool: string; ok: boolean; outcome: string; error: string | null }[];
    failedStep: string | null;
    domainGenerated?: boolean | null;
    domainHost?: string | null;
  } | null;
};

export type GuardianAppDeployAdapterDeps = {
  transport: VpsTransport;
  now: () => number;
  dispatchRecord: GuardianAppDeployDispatchRecord;
};

export function createGuardianAppDeployAdapter(deps: GuardianAppDeployAdapterDeps): DomainAdapter<GuardianAppDeployIntent, GuardianAppDeployProposal> {
  return {
    async bind(intent: GuardianAppDeployIntent) {
      // READ-ONLY, fail-closed eligibility. No I/O.
      const reasons: string[] = [];
      if (intent.action !== "create_application") reasons.push("ACTION_NOT_ALLOWLISTED");
      if (intent.approved !== true) reasons.push("APPROVAL_GATE_NOT_SATISFIED");
      if (asNonEmptyString(intent.name) === null) reasons.push("TARGET_NAME_NOT_RESOLVED");
      if (asNonEmptyString(intent.source) === null) reasons.push("SOURCE_NOT_RESOLVED");
      if (reasons.length > 0) {
        return { outcome: "NOT_EXECUTED", stage: "ELIGIBILITY", refusal: "BLOCKED", effect: { dispatched: false, state: "NONE_PROVEN" }, reasons };
      }
      // proposal carries ONLY plan data (no transport, no adapter, no secrets handling).
      // GCLOUD-01F: the destination serverId travels ONLY through this bind-forged
      // proposal — apply consumes it from here, never from late-mutable input.
      return { status: "BOUND", proposal: { name: intent.name, source: intent.source, startCommand: "", port: null, env: undefined, serverId: intent.serverId } as GuardianAppDeployProposal };
    },
    async apply(proposal: GuardianAppDeployProposal): Promise<GuardianResult> {
      // Read-only re-proof (precheck from PLAN time still holds: name still absent).
      let search: VpsTransportResponse;
      try {
        search = await deps.transport.call({ toolName: "application-search", arguments: {}, mutating: false, confirmation: { toolName: "application-search" } });
      } catch (error) {
        deps.dispatchRecord.revalidation = { ok: false, status: 0, error: error instanceof Error ? error.message : String(error) };
        return { outcome: "INDETERMINATE", effect: { dispatched: false, state: "NONE_PROVEN" }, reasons: ["REVALIDATION_READ_FAILED", "application-search revalidation threw before the mutating boundary; zero mutation"] };
      }
      deps.dispatchRecord.revalidation = { ok: search.ok, status: search.status, error: search.error ?? null };
      if (!search.ok) {
        return { outcome: "INDETERMINATE", effect: { dispatched: false, state: "NONE_PROVEN" }, reasons: ["REVALIDATION_READ_FAILED", `application-search status=${search.status}`, "fail-closed: the mutating boundary is never reached without a trustworthy re-proof"] };
      }
      const normalized = normalizeMcpResult(search.result);
      const applications = findApplicationArray(normalized);
      const duplicate = applications.find((app) => asNonEmptyString(app.name) === proposal.name);
      if (duplicate) {
        return { outcome: "NOT_EXECUTED", stage: "COMPATIBILITY", refusal: "BLOCKED", effect: { dispatched: false, state: "NONE_PROVEN" }, reasons: ["STATE_CHANGED_SINCE_PRECHECK", "an application with the same name is already evidenced at dispatch time; zero mutation"] };
      }
      // ---- GCLOUD-01F: governed provisioning (reuse-before-create) ----
      // Caller-provided environmentId -> upstream identity already resolved;
      // provisioning is skipped entirely (backward compatible). Otherwise the
      // project/environment identity defined by this SuperTool (defaults in
      // PROVISION_IDENTITY_DEFAULTS) is resolved INSIDE this mutating boundary,
      // BEFORE application-create. Each step is ONE dispatch; a failure stops
      // the sequence and is reported honestly as INDETERMINATE with the
      // observed partial state — never presented as one atomic mutation.
      let provisioningEnvironmentId: string | null = asNonEmptyString(proposal.environmentId);
      if (provisioningEnvironmentId === null) {
        const projectName = asNonEmptyString(proposal.projectName) ?? PROVISION_IDENTITY_DEFAULTS.projectName;
        const environmentName = asNonEmptyString(proposal.environmentName) ?? PROVISION_IDENTITY_DEFAULTS.environmentName;
        const project = await resolveOrCreateProject({ transport: deps.transport }, { projectName });
        if (!project.ok || project.projectId === null) {
          deps.dispatchRecord.provisioning = { projectId: project.projectId, projectReused: project.ok ? project.reused : null, projectOutcome: project.outcome, environmentId: null, environmentReused: null, environmentOutcome: null, sourceSteps: [], failedStep: "project" };
          const dispatched = project.outcome === "CREATED" || project.outcome === "UPSTREAM_ERROR";
          return { outcome: "INDETERMINATE", effect: { dispatched, state: dispatched ? "UNDETERMINED" : "NONE_PROVEN" }, reasons: ["PROJECT_PROVISIONING_FAILED", `outcome=${project.outcome}`, project.error ?? "", "stopped before environment resolution and application create"] };
        }
        const environment = await resolveOrCreateEnvironment({ transport: deps.transport }, { projectId: project.projectId, environmentName });
        if (!environment.ok || environment.environmentId === null) {
          deps.dispatchRecord.provisioning = { projectId: project.projectId, projectReused: project.reused, projectOutcome: project.outcome, environmentId: environment.environmentId, environmentReused: environment.ok ? environment.reused : null, environmentOutcome: environment.outcome, sourceSteps: [], failedStep: "environment" };
          const dispatched = project.outcome === "CREATED" || environment.outcome === "CREATED" || project.outcome === "UPSTREAM_ERROR" || environment.outcome === "UPSTREAM_ERROR";
          return { outcome: "INDETERMINATE", effect: { dispatched, state: dispatched ? "UNDETERMINED" : "NONE_PROVEN" }, reasons: ["ENVIRONMENT_PROVISIONING_FAILED", `outcome=${environment.outcome}`, environment.error ?? "", "project is provisioned/reused but the application was NOT created; stopped before application create"] };
        }
        provisioningEnvironmentId = environment.environmentId;
        deps.dispatchRecord.provisioning = { projectId: project.projectId, projectReused: project.reused, projectOutcome: project.outcome, environmentId: environment.environmentId, environmentReused: environment.reused, environmentOutcome: environment.outcome, sourceSteps: [], failedStep: null };
      } else {
        deps.dispatchRecord.provisioning = { projectId: null, projectReused: null, projectOutcome: null, environmentId: provisioningEnvironmentId, environmentReused: null, environmentOutcome: null, sourceSteps: [], failedStep: null };
      }
      // NOTE: proposal.startCommand/port/env are filled by the SuperTool before
      // executeGuardianIntent via a closure-bound payload (see runGuardianAppDeploy):
      // the adapter dispatch uses deps-bound plan values, keeping the proposal data-only.
      const create = await runApplicationCreate(
        "application-create",
        { name: proposal.name, source: proposal.source, startCommand: (proposal as GuardianAppDeployProposal & { planStartCommand?: string }).planStartCommand ?? proposal.startCommand, environmentId: provisioningEnvironmentId ?? undefined, serverId: asNonEmptyString(proposal.serverId) ?? undefined, port: proposal.port ?? undefined, env: proposal.env, execute: true },
        { transport: deps.transport },
      );
      deps.dispatchRecord.create = { outcome: create.outcome, ok: create.ok, applicationId: create.createdApplicationId, response: create.response };
      if (create.ok && create.outcome === "EXECUTED_ACCEPTED" && create.createdApplicationId !== undefined) {
        // GCLOUD-01F: git/build/env configuration INSIDE the governed boundary,
        // after create acceptance. Stop-on-first-failure; the application may
        // exist with incomplete configuration (honest partial state) — the
        // deploy step is never attempted in that case.
        const sourceConfig = await configureApplicationSource(
          { transport: deps.transport },
          {
            applicationId: create.createdApplicationId,
            repoUrl: proposal.source,
            branch: asNonEmptyString(proposal.branch) ?? PROVISION_IDENTITY_DEFAULTS.branch,
            buildPath: null,
            buildType: asNonEmptyString(proposal.buildType) ?? PROVISION_IDENTITY_DEFAULTS.buildType,
            envText: buildEnvText(proposal.env),
          },
        );
        const record = deps.dispatchRecord.provisioning ?? { projectId: null, projectReused: null, projectOutcome: null, environmentId: null, environmentReused: null, environmentOutcome: null, sourceSteps: [], failedStep: null };
        deps.dispatchRecord.provisioning = { ...record, sourceSteps: sourceConfig.steps, failedStep: sourceConfig.failedStep };
        if (!sourceConfig.ok) {
          return { outcome: "INDETERMINATE", effect: { dispatched: true, state: "UNDETERMINED" }, reasons: [`SOURCE_CONFIG_FAILED at step=${sourceConfig.failedStep}`, sourceConfig.error ?? "", "application exists but git/build/env configuration is incomplete; deploy is never attempted"] };
        }
        return { outcome: "EXECUTED", effect: { dispatched: true, state: "MUTATION_ACCEPTED_PROVEN" }, reasons: ["application-create accepted and git/build/env configuration applied inside the Guardian mutating boundary"] };
      }
      if (create.ok && create.outcome === "EXECUTED_ACCEPTED") {
        return { outcome: "EXECUTED", effect: { dispatched: true, state: "MUTATION_ACCEPTED_PROVEN" }, reasons: ["application-create accepted inside the Guardian mutating boundary"] };
      }
      return { outcome: "INDETERMINATE", effect: { dispatched: true, state: "UNDETERMINED" }, reasons: [`application-create outcome=${create.outcome}`, create.response?.error ?? "UNKNOWN upstream outcome"] };
    },
  };
}

function findApplicationArray(payload: unknown): Record<string, unknown>[] {
  if (Array.isArray(payload)) return payload.filter(isRecord);
  if (!isRecord(payload)) return [];
  const data = payload.data;
  if (Array.isArray(data)) return data.filter(isRecord);
  if (isRecord(data) && Array.isArray((data as Record<string, unknown>).items)) return ((data as Record<string, unknown>).items as unknown[]).filter(isRecord);
  if (Array.isArray(payload.items)) return (payload.items as unknown[]).filter(isRecord);
  return [];
}

function extractApplicationRecord(payload: unknown): Record<string, unknown> | null {
  if (isRecord(payload) && (asNonEmptyString(payload.applicationId) !== null || asNonEmptyString(payload.id) !== null)) return payload;
  if (isRecord(payload) && isRecord(payload.data)) return payload.data;
  return null;
}

export type GuardianAppDeployDeps = {
  transport?: VpsTransport;
  guardian?: GuardianCoreModule;
  now?: () => number;
};

export async function runGuardianAppDeploy(input: unknown, deps: GuardianAppDeployDeps): Promise<GuardianAppDeployResult> {
  const notes: string[] = [];
  const transport = deps.transport ?? createMcpClientCallTransport({ dokployServerId: process.env.ENG_MCP_VPS_DOKPLOY_SERVER_ID, endpoint: process.env.ENG_MCP_AGENT_MEMORY_ENDPOINT });
  if (!isRecord(input) || asNonEmptyString(input.name) === null || asNonEmptyString(input.source) === null) {
    const missing: string[] = [];
    if (!isRecord(input)) missing.push("input");
    else {
      if (asNonEmptyString(input.name) === null) missing.push("name");
      if (asNonEmptyString(input.source) === null) missing.push("source");
    }
    return makeResult({ status: "NEEDS_INPUT", missing, name: isRecord(input) ? String(input.name ?? "") : "" });
  }
  const name = String(input.name);
  const source = String(input.source);
  const env = isRecord(input.env) ? (Object.fromEntries(Object.entries(input.env).filter(([, v]) => typeof v === "string")) as Record<string, string>) : undefined;
  if (env !== undefined && Object.keys(env).length !== Object.keys(input.env as Record<string, unknown>).length) {
    notes.push("env entries with non-string values ignored");
  }
  const snapshot = isRecord(input.projectSnapshot) ? input.projectSnapshot : {};

  // ---- 1. evidence-only detection (GCLOUD-01C) ----
  const detection = detectNodeApp({ packageJsonText: (snapshot as Record<string, unknown>).packageJsonText, files: (snapshot as Record<string, unknown>).files as Record<string, string> | undefined });
  if (detection.status !== "DETECTED" || detection.startCommand === null) {
    return makeResult({
      status: "NEEDS_INPUT",
      name,
      detection,
      missing: [...detection.needsInput],
      note: `node detector did not reach DETECTED (status=${detection.status}); stopped before any transport call`,
    });
  }
  if (detection.port === null) {
    return makeResult({
      status: "NEEDS_INPUT",
      name,
      detection,
      missing: ["port"],
      note: `port unresolved (portStrategy=${detection.portStrategy}); a deploy target must have an evidenced or user-provided port`,
    });
  }

  // ---- upstream contract resolution (GCLOUD-01E/01F) ----
  // application-create REQUIRES environmentId (dokploy schema). GCLOUD-01F: it is
  // resolved INSIDE the governed boundary — either the caller provides it directly
  // or the project/environment provisioning (reuse-before-create) resolves it.
  // Optional identity inputs are validated here fail-closed BEFORE any transport call.
  const inputProjectName = asNonEmptyString(input.projectName);
  const inputEnvironmentName = asNonEmptyString(input.environmentName);
  const inputBranch = asNonEmptyString(input.branch);
  const inputBuildType = asNonEmptyString(input.buildType);
  // GCLOUD-01F: destination server (optional). Caller-supplied only; never
  // hardcoded, never auto-discovered; travels into the Guardian-bound intent.
  const inputServerId = asNonEmptyString(input.serverId) ?? undefined;
  if (input.serverId !== undefined && inputServerId === undefined) {
    notes.push("serverId provided but not usable (non-empty string expected); ignored");
  }
  if (inputBranch !== null && !DOKPLOY_BRANCH_PATTERN.test(inputBranch)) {
    return makeResult({ status: "NEEDS_INPUT", name, detection, missing: ["branch"], note: `branch does not match the upstream customGitBranch pattern ${String(DOKPLOY_BRANCH_PATTERN)}` });
  }
  if (inputBuildType !== null && !(DOKPLOY_BUILD_TYPES as readonly string[]).includes(inputBuildType)) {
    return makeResult({ status: "NEEDS_INPUT", name, detection, missing: ["buildType"], note: `buildType is not part of the upstream enum (${DOKPLOY_BUILD_TYPES.join(", ")})` });
  }

  const envForCreate: Record<string, string> = env === undefined ? {} : { ...env };
  if (detection.portStrategy === "ENV_PORT" && envForCreate.PORT === undefined) {
    envForCreate.PORT = String(detection.port);
    notes.push("PORT env entry added from documented PORT evidence (value redacted in all outputs)");
  }
  const provisioningPlan = {
    mode: asNonEmptyString(input.environmentId) === null ? "project/environment provisioning (reuse-before-create)" : "environmentId provided; provisioning skipped",
    projectName: inputProjectName ?? PROVISION_IDENTITY_DEFAULTS.projectName,
    environmentName: inputEnvironmentName ?? PROVISION_IDENTITY_DEFAULTS.environmentName,
    branch: inputBranch ?? PROVISION_IDENTITY_DEFAULTS.branch,
    buildType: inputBuildType ?? PROVISION_IDENTITY_DEFAULTS.buildType,
    source,
    ...(inputServerId !== undefined ? { serverId: inputServerId } : {}),
  };
  const plan = {
    primitive: "application-create" as const,
    startCommand: detection.startCommand,
    port: detection.port,
    portStrategy: detection.portStrategy,
    envKeys: envKeys(envForCreate),
    provisioning: provisioningPlan,
  };

  // ---- 2. PLAN mode: zero transport, zero mutation ----
  if (input.execute !== true) {
    return makeResult({
      ok: true,
      status: "PLANNED",
      name,
      detection,
      plan,
      guardian: { outcome: "NOT_EXECUTED", stage: "PLAN", refusal: "PLAN_MODE", reasons: ["execute!==true: plan only; no transport call, no mutation"] },
      note: notes.length > 0 ? notes.join(" ") : null,
    });
  }

  // ---- 3. Guardian-gated execution ----
  let core = deps.guardian ?? null;
  let guardianLoadError: string | null = null;
  if (core === null) {
    const loaded = await loadGuardianCore();
    core = loaded.core;
    guardianLoadError = loaded.error;
  }
  if (core === null) {
    return makeResult({
      status: "UNKNOWN",
      name,
      detection,
      plan,
      note: `fail-closed: Guardian Core unavailable (${guardianLoadError ?? "null core"}); zero mutation`,
    });
  }

  const now = deps.now ?? (() => Date.now());
  const dispatchRecord: GuardianAppDeployDispatchRecord = { create: null, revalidation: null, provisioning: null };
  const adapterDeps: GuardianAppDeployAdapterDeps = { transport, now, dispatchRecord };
  // Bind the resolved plan into the single mutating boundary WITHOUT putting
  // transport/authority into the intent: the closure-bound payload travels
  // through the proposal (data-only), consumed only by apply.
  const planPayload = { planStartCommand: detection.startCommand, port: detection.portStrategy === "ENV_PORT" ? null : detection.port, env: envForCreate };
  const adapter = createGuardianAppDeployAdapter(adapterDeps);
  // Closure-bound plan payload (data-only, fixed before bind): the same values
  // proven at bind time. NOTE: serverId is intentionally NOT part of this
  // payload — GCLOUD-01F dispatches the destination server exclusively from the
  // bind-forged proposal (approved intent data), so a late change of the raw
  // input between approval and execution can never silently swap the
  // destination.
  const planProposal = {
    name,
    source,
    startCommand: planPayload.planStartCommand,
    environmentId: asNonEmptyString(input.environmentId) ?? undefined,
    projectName: inputProjectName ?? undefined,
    environmentName: inputEnvironmentName ?? undefined,
    branch: inputBranch ?? undefined,
    buildType: inputBuildType ?? undefined,
    port: planPayload.port,
    env: planPayload.env,
  } as GuardianAppDeployProposal;
  const governedAdapter: DomainAdapter<GuardianAppDeployIntent, Record<string, never>> = {
    async bind(intent: GuardianAppDeployIntent) {
      return adapter.bind(intent);
    },
    async apply(bound: Record<string, never>): Promise<GuardianResult> {
      // apply() receives the bind-forged proposal; plan values come from the
      // closure-bound payload and the destination serverId comes ONLY from the
      // proposal the Guardian forged at bind time (approved intent data).
      const serverId = asNonEmptyString(isRecord(bound) ? (bound as Record<string, unknown>).serverId : null) ?? undefined;
      return adapter.apply({ ...planProposal, serverId } as GuardianAppDeployProposal);
    },
  };

  const intent: GuardianAppDeployIntent = {
    action: "create_application",
    approved: input.approved === true,
    name,
    source,
    serverId: inputServerId,
    observedAt: now(),
  };
  const guardianResult = await core.executeGuardianIntent(intent, governedAdapter);
  const guardianSummary = {
    outcome: String(guardianResult.outcome),
    stage: (guardianResult as Record<string, unknown>).stage as string | undefined,
    refusal: (guardianResult as Record<string, unknown>).refusal as string | undefined,
    reasons: Array.isArray((guardianResult as Record<string, unknown>).reasons) ? ((guardianResult as Record<string, unknown>).reasons as unknown[]).map(String) : [],
  };

  if (guardianSummary.outcome === "NOT_EXECUTED" && guardianSummary.stage === "ELIGIBILITY") {
    return makeResult({
      status: "APPROVAL_REQUIRED",
      name,
      detection,
      plan,
      guardian: guardianSummary,
      note: "Guardian bind refused (fail-closed); zero transport calls, zero mutation",
    });
  }
  if (guardianSummary.outcome === "NOT_EXECUTED") {
    return makeResult({
      status: "FAILED",
      name,
      detection,
      plan,
      guardian: guardianSummary,
      note: "Guardian refused at a later stage; zero mutation",
    });
  }
  if (guardianSummary.outcome === "INDETERMINATE" && dispatchRecord.create === null) {
    const provisioning = dispatchRecord.provisioning;
    if (provisioning !== null && provisioning.failedStep !== null) {
      return makeResult({
        status: "FAILED",
        name,
        detection,
        plan,
        guardian: guardianSummary,
        provisioning: provisioningSummary(provisioning),
        mutated: provisioning.projectOutcome === "CREATED" || provisioning.environmentOutcome === "CREATED",
        note: `provisioning failed at step=${provisioning.failedStep} before application create; deploy never attempted; partial state reported honestly`,
      });
    }
    return makeResult({
      status: "UNKNOWN",
      name,
      detection,
      plan,
      guardian: guardianSummary,
      note: "Guardian stopped before the mutating boundary (revalidation failed); zero mutation",
    });
  }

  const create = dispatchRecord.create;
  if (create === null) {
    return makeResult({ status: "UNKNOWN", name, detection, plan, guardian: guardianSummary, provisioning: dispatchRecord.provisioning === null ? null : provisioningSummary(dispatchRecord.provisioning), note: "no create record after a governed execution; refusing to continue" });
  }
  if (!create.ok || create.outcome !== "EXECUTED_ACCEPTED" || create.applicationId === undefined) {
    return makeResult({
      status: "FAILED",
      name,
      detection,
      plan,
      guardian: guardianSummary,
      create,
      provisioning: dispatchRecord.provisioning === null ? null : provisioningSummary(dispatchRecord.provisioning),
      mutated: true,
      note: "application-create did not prove acceptance; deploy is never attempted after a failed create",
    });
  }
  if (guardianSummary.outcome !== "EXECUTED") {
    // GCLOUD-01F: INDETERMINATE after create acceptance = git/build/env
    // configuration failed inside the boundary. The application exists with
    // incomplete configuration (honest partial state); deploy is NEVER attempted.
    return makeResult({
      status: "FAILED",
      name,
      detection,
      plan,
      guardian: guardianSummary,
      create,
      provisioning: dispatchRecord.provisioning === null ? null : provisioningSummary(dispatchRecord.provisioning),
      mutated: true,
      note: "governed sequence incomplete (source/build/env configuration failed); deploy is never attempted after an incomplete provisioning sequence",
    });
  }
  const applicationId = create.applicationId;

  // ---- 4. deploy: reuse the allowlisted mutating primitive, ONE attempt ----
  let deploy: GuardianAppDeployResult["deploy"];
  try {
    const response = await transport.call({ toolName: "application-deploy", arguments: { applicationId }, mutating: true, confirmation: { toolName: "application-deploy" } });
    deploy = { dispatched: true, ok: response.ok, status: response.status, error: response.error };
  } catch (error) {
    deploy = { dispatched: true, ok: false, status: 0, error: error instanceof Error ? error.message : String(error) };
  }
  if (!deploy.ok) {
    return makeResult({
      status: "FAILED",
      name,
      detection,
      plan,
      guardian: guardianSummary,
      create,
      deploy,
      provisioning: dispatchRecord.provisioning === null ? null : provisioningSummary(dispatchRecord.provisioning),
      mutated: true,
      note: "deploy failed; LIVE is never claimed after a failed deploy",
    });
  }

  // ---- 5. post-validation: health via read-only application-one ----
  let health: GuardianAppDeployResult["health"] = null;
  let applicationRecord: Record<string, unknown> | null = null;
  try {
    // Health read MUST use the session transport: deps.transport is optional and is
    // undefined for MCP-handler callers (runGuardianAppDeploy(input, {})); a late
    // deref here previously broke the live health evidence path (GCLOUD-01F E2E).
    const response = await transport.call({ toolName: "application-one", arguments: { applicationId }, mutating: false, confirmation: { toolName: "application-one" } });
    if (response.ok) {
      const record = extractApplicationRecord(normalizeMcpResult(response.result));
      applicationRecord = record;
      const status = record === null ? null : asNonEmptyString(record.applicationStatus) ?? asNonEmptyString(record.status);
      health = { evidence: status === null ? `application-one returned no applicationStatus (keys preserved)` : `applicationStatus=${status}`, healthy: status !== null && /running/i.test(status) };
    } else {
      health = { evidence: `application-one health read failed (status=${response.status})`, healthy: false };
    }
  } catch (error) {
    health = { evidence: `application-one health read threw: ${error instanceof Error ? error.message : String(error)}`, healthy: false };
  }

  // ---- 6. domain via GCLOUD-01B read-only primitive; GCLOUD-01F: when NO domain
  // is evidenced, compose the real upstream domain mutations (domain-generateDomain
  // + domain-create letsencrypt traefik.me) and re-read the evidence — the host
  // comes ONLY from the upstream generate response and is never invented.
  let domainResult = await runApplicationDomain({ applicationId }, { transport });
  if (domainResult.status !== "READY" || domainResult.url === null) {
    const ensured = await ensureApplicationDomain(
      { transport },
      { applicationId, appName: applicationRecord === null ? null : asNonEmptyString(applicationRecord.appName), serverId: inputServerId ?? null },
    );
    if (dispatchRecord.provisioning !== null) {
      dispatchRecord.provisioning.domainGenerated = ensured.ok;
      dispatchRecord.provisioning.domainHost = ensured.host;
    }
    if (ensured.ok) {
      domainResult = await runApplicationDomain({ applicationId }, { transport });
    } else {
      notes.push(`domain auto-provisioning failed (${ensured.outcome}): ${ensured.error ?? "unknown"}`);
    }
  }
  const domain: GuardianAppDeployResult["domain"] = {
    status: domainResult.status,
    url: domainResult.url,
    https: domainResult.https,
    host: domainResult.domain ?? null,
  };

  const mutated = true; // create dispatched (accepted); deploy dispatched (ok)
  if (!health.healthy) {
    return makeResult({
      status: "DEPLOYING",
      ok: false,
      name,
      detection,
      plan,
      guardian: guardianSummary,
      create,
      deploy,
      health,
      domain,
      provisioning: dispatchRecord.provisioning === null ? null : provisioningSummary(dispatchRecord.provisioning),
      mutated,
      note: "deploy accepted but health evidence is insufficient; LIVE is never claimed without health",
    });
  }
  if (domainResult.status !== "READY" || domainResult.url === null || domainResult.https !== true) {
    return makeResult({
      status: "DEPLOYED_AWAITING_DOMAIN",
      ok: false,
      name,
      detection,
      plan,
      guardian: guardianSummary,
      create,
      deploy,
      health,
      domain,
      mutated,
      provisioning: dispatchRecord.provisioning === null ? null : provisioningSummary(dispatchRecord.provisioning),
      url: null,
      note: `application is healthy but the domain is not evidenced (application-domain status=${domainResult.status}); url stays null — never invented${notes.length > 0 ? ` | ${notes.join(" ")}` : ""}`,
    });
  }

  return makeResult({
    ok: true,
    status: "LIVE",
    name,
    detection,
    plan,
    guardian: guardianSummary,
    create,
    deploy,
    health,
    domain,
    mutated,
    provisioning: dispatchRecord.provisioning === null ? null : provisioningSummary(dispatchRecord.provisioning),
    url: domainResult.url,
  });
}
