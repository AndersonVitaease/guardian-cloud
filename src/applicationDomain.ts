// GCLOUD-01B — engineering "application-domain" primitive (Sprint GCLOUD-01, step 3).
//
// Purpose: the MINIMAL READ-ONLY Dokploy primitive to resolve the REAL public
// domain/URL of an EXISTING application, reusing the exact transport contract
// proven by src/vpsChangeSafe.ts (Base44 mcpClientCall channel, injectable
// VpsTransport for offline tests).
//
// Evidence base (REAL, gathered 2026-09-07):
// - Bridge allowlist (Base44 agentMemoryBridge entry.ts — the channel the default
//   transport actually uses): MCP_EXECUTE_READ_TOOLS contains NO "domain-*"
//   primitive. A domain read via GET /domain.byApplicationId would be rejected
//   403 TOOL_NOT_ALLOWLISTED before any connection. The ONLY allowlisted read
//   primitive that returns application data is "application-one".
// - Official upstream catalog @dokploy/mcp@0.30.2 (build/generated/tools.js):
//   "application-one" = GET /application.one, schema { applicationId }, annotations
//   readOnlyHint:true, idempotentHint:true. "domain-byApplicationId" = GET
//   /domain.byApplicationId (readOnlyHint:true) proves domains are served by a
//   SEPARATE upstream primitive. Domain record fields evidenced by the
//   domain-create / domain-update input schemas: host (required), https (boolean),
//   certificateType (letsencrypt|none|custom), domainType (compose|application|
//   preview), applicationId, domainId.
// - The domain container field INSIDE the application-one response could NOT be
//   observed live yet (zero applications exist on the managed Dokploy). This
//   module therefore scans ONLY the documented candidate containers ("domain",
//   "domains") and parses items ONLY through the evidenced host/https/domainType
//   contract. When no candidate matches, the result is honest DOMAIN_PENDING /
//   UNKNOWN — never an invented domain or URL.
//
// Hard rules (this sprint):
// - ZERO mutation: mutating:false on every transport call; toolName comes ONLY
//   from APPLICATION_DOMAIN_READ_PRIMITIVES — never from caller input. Exactly
//   ONE read call per invocation: no retry, no fallback, no second primitive.
// - GUARDIAN: NOT integrated (read-only; GUARDIAN_GATED=NO). Guardian Core is
//   untouched.
// - URL construction is EVIDENCE-ONLY: "https://{host}" only when the record says
//   https === true; "http://{host}" only when https === false; https missing =>
//   url:null and https:null (HTTPS is never assumed).
// - Multiple domains: a primary is selected ONLY with evidence (exactly one item
//   carrying domainType "application" — the official enum value for an
//   application's own domain; a single entry is also determinate). Otherwise the
//   result is AMBIGUOUS with the full domains[] list — never an arbitrary choice.
// - Upstream failures surface verbatim as UPSTREAM_ERROR — never a fabricated
//   success. No SSH, no shell, no LLM. No secrets read or echoed.

import {
  normalizeMcpResult,
  type VpsTransport,
  type VpsTransportCall,
  type VpsTransportResponse,
} from "./vpsTransport.ts";

export const APPLICATION_DOMAIN_READ_PRIMITIVES = Object.freeze(["application-one"] as const);
export const GUARDIAN_GATE = "none (read-only primitive; GUARDIAN_GATED=NO)";

// Container names scanned for domain evidence. These relation names are NOT yet
// live-verified (zero applications exist); only the item contract (host/https/
// certificateType/domainType) is verified against the official upstream catalog.
const DOMAIN_CONTAINER_CANDIDATES = ["domain", "domains"] as const;

export type ApplicationDomainStatus =
  | "READY"
  | "NOT_FOUND"
  | "DOMAIN_PENDING"
  | "AMBIGUOUS"
  | "UNKNOWN"
  | "NEEDS_INPUT"
  | "UPSTREAM_ERROR";

export type ApplicationDomainInput = { applicationId: string };

export type ApplicationDomainEvidence = {
  host: string;
  https: boolean | null;
  url: string | null;
  certificateType: string | null;
  domainType: string | null;
};

export type ApplicationDomainResult = {
  ok: boolean;
  status: ApplicationDomainStatus;
  tool: "application-domain";
  applicationId: string | null;
  domain: string | null;
  url: string | null;
  https: boolean | null;
  domains: ApplicationDomainEvidence[];
  missing: string[];
  mutated: boolean;
  readPrimitives: readonly string[];
  transport: string | null;
  response?: { ok: boolean; status: number; durationMs: number; error?: string };
  primaryEvidence?: string;
  note?: string;
  guardianGate: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function validateApplicationDomainInput(
  input: unknown,
): { ok: true; value: ApplicationDomainInput } | { ok: false; missing: string[] } {
  if (!isRecord(input) || !nonEmptyString(input.applicationId)) return { ok: false, missing: ["applicationId"] };
  const applicationId = (input.applicationId as string).trim();
  if (applicationId.length > 200) return { ok: false, missing: ["applicationId"] };
  return { ok: true, value: { applicationId } };
}

type AppRecordResolution =
  | { kind: "app"; record: Record<string, unknown> }
  | { kind: "missing"; reason: string }
  | { kind: "unrecognized"; reason: string };

function hasApplicationIdentity(record: Record<string, unknown>): boolean {
  const candidate = record.applicationId ?? record.id;
  return typeof candidate === "string" && candidate.length > 0;
}

// Deterministic resolution of the application-one payload (after normalizeMcpResult):
// success:false + "not found" message => NOT_FOUND; any identity field (applicationId
// or id, possibly nested in a data wrapper) => app record; empty record => NOT_FOUND;
// anything else is insufficient evidence => UNKNOWN (never guessed).
function resolveApplicationRecord(result: unknown): AppRecordResolution {
  if (!isRecord(result)) return { kind: "unrecognized", reason: "RESPONSE_NOT_A_RECORD" };
  if (result.success === false) {
    const message = typeof result.message === "string" ? result.message : "";
    if (/not found/i.test(message)) return { kind: "missing", reason: "UPSTREAM_REPORTED_NOT_FOUND" };
    return { kind: "unrecognized", reason: "UPSTREAM_SUCCESS_FALSE_WITHOUT_NOT_FOUND" };
  }
  if (hasApplicationIdentity(result)) return { kind: "app", record: result };
  if (isRecord(result.data) && hasApplicationIdentity(result.data)) return { kind: "app", record: result.data };
  if (Object.keys(result).length === 0) return { kind: "missing", reason: "EMPTY_APPLICATION_RECORD" };
  return { kind: "unrecognized", reason: "NO_APPLICATION_IDENTITY_FIELDS" };
}

// Parses ONE domain item through the OFFICIALLY evidenced field contract only.
// Record items must carry "host" (the official required field); "https" is used
// ONLY when it is a boolean. String items carry their own evidence: a value with
// an explicit http(s):// prefix proves the scheme; a bare value proves only the
// host (https stays null and no URL is built).
function parseDomainItem(item: unknown): ApplicationDomainEvidence | null {
  if (typeof item === "string") {
    const trimmed = item.trim();
    if (trimmed.length === 0) return null;
    const schemeMatch = /^(https?):\/\//i.exec(trimmed);
    if (schemeMatch) {
      const scheme = schemeMatch[1].toLowerCase();
      const rest = trimmed.slice(schemeMatch[0].length);
      const host = rest.split("/")[0].trim();
      if (host.length === 0) return null;
      const https = scheme === "https";
      return { host, https, url: `${scheme}://${host}`, certificateType: null, domainType: null };
    }
    return { host: trimmed, https: null, url: null, certificateType: null, domainType: null };
  }
  if (!isRecord(item)) return null;
  const host = nonEmptyString(item.host) ? (item.host as string).trim() : null;
  if (host === null) return null;
  const https = typeof item.https === "boolean" ? item.https : null;
  const certificateType = typeof item.certificateType === "string" ? item.certificateType : null;
  const domainTypeRaw = item.domainType;
  const domainType =
    typeof domainTypeRaw === "string" && (domainTypeRaw === "compose" || domainTypeRaw === "application" || domainTypeRaw === "preview")
      ? domainTypeRaw
      : null;
  let url: string | null = null;
  if (https === true) url = `https://${host}`;
  else if (https === false) url = `http://${host}`;
  return { host, https, url, certificateType, domainType };
}

function extractDomainEvidence(record: Record<string, unknown>): ApplicationDomainEvidence[] {
  const items: unknown[] = [];
  for (const key of DOMAIN_CONTAINER_CANDIDATES) {
    const value = record[key];
    if (value === undefined) continue;
    if (Array.isArray(value)) items.push(...value);
    else items.push(value);
  }
  const evidence: ApplicationDomainEvidence[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    const parsed = parseDomainItem(item);
    if (parsed === null) continue;
    const dedupeKey = `${parsed.host}|${parsed.url ?? ""}|${String(parsed.https)}`;
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    evidence.push(parsed);
  }
  return evidence;
}

export type ApplicationDomainDeps = {
  transport: VpsTransport;
};

export async function runApplicationDomain(input: unknown, deps: ApplicationDomainDeps): Promise<ApplicationDomainResult> {
  const base = {
    tool: "application-domain" as const,
    domains: [] as ApplicationDomainEvidence[],
    missing: [] as string[],
    mutated: false,
    readPrimitives: APPLICATION_DOMAIN_READ_PRIMITIVES,
    guardianGate: GUARDIAN_GATE,
  };
  const validated = validateApplicationDomainInput(input);
  if (!validated.ok) {
    // Rejected BEFORE any transport call: zero reads, zero writes.
    return { ...base, ok: false, status: "NEEDS_INPUT", applicationId: null, domain: null, url: null, https: null, transport: null, missing: validated.missing };
  }
  const applicationId = validated.value.applicationId;

  // Exactly ONE read call. toolName is a module constant, mutating:false always.
  const request: VpsTransportCall = {
    toolName: "application-one",
    arguments: { applicationId },
    mutating: false,
    confirmation: { toolName: "application-one" },
  };
  let response: VpsTransportResponse;
  try {
    response = await deps.transport.call(request);
  } catch (error) {
    return {
      ...base,
      ok: false,
      status: "UPSTREAM_ERROR",
      applicationId,
      domain: null,
      url: null,
      https: null,
      transport: deps.transport.name,
      response: { ok: false, status: 0, durationMs: 0, error: error instanceof Error ? error.message : String(error) },
      note: "transport threw before any response; preserved honestly",
    };
  }
  if (!response.ok) {
    return {
      ...base,
      ok: false,
      status: "UPSTREAM_ERROR",
      applicationId,
      domain: null,
      url: null,
      https: null,
      transport: deps.transport.name,
      response: { ok: response.ok, status: response.status, durationMs: response.durationMs, error: response.error },
      note: "upstream read failure preserved verbatim; nothing invented",
    };
  }

  const resolution = resolveApplicationRecord(normalizeMcpResult(response.result));
  if (resolution.kind === "unrecognized") {
    return {
      ...base,
      ok: false,
      status: "UNKNOWN",
      applicationId,
      domain: null,
      url: null,
      https: null,
      transport: deps.transport.name,
      response: { ok: response.ok, status: response.status, durationMs: response.durationMs },
      note: `insufficient evidence to classify the application-one payload: ${resolution.reason}`,
    };
  }
  if (resolution.kind === "missing") {
    return {
      ...base,
      ok: true,
      status: "NOT_FOUND",
      applicationId,
      domain: null,
      url: null,
      https: null,
      transport: deps.transport.name,
      response: { ok: response.ok, status: response.status, durationMs: response.durationMs },
      note: resolution.reason,
    };
  }

  // Application exists. Domain evidence is taken ONLY from the application-one
  // response; absence of evidence is DOMAIN_PENDING (a domain may simply not be
  // attached yet — never fabricated).
  const evidence = extractDomainEvidence(resolution.record);
  if (evidence.length === 0) {
    return {
      ...base,
      ok: true,
      status: "DOMAIN_PENDING",
      applicationId,
      domain: null,
      url: null,
      https: null,
      transport: deps.transport.name,
      response: { ok: response.ok, status: response.status, durationMs: response.durationMs },
      note: "application resolved but no domain evidence found in the application-one response",
    };
  }

  // Multiple domains: primary ONLY with evidence (exactly one domainType
  // "application"), otherwise AMBIGUOUS with the full list — never arbitrary.
  const applicationTyped = evidence.filter((entry) => entry.domainType === "application");
  let selected: ApplicationDomainEvidence | null = null;
  let primaryEvidence: string | undefined;
  if (evidence.length === 1) {
    selected = evidence[0];
    primaryEvidence = "single domain entry in the application-one response";
  } else if (applicationTyped.length === 1) {
    selected = applicationTyped[0];
    primaryEvidence = "exactly one entry with domainType 'application' (official enum value for an application's own domain)";
  }

  if (selected === null) {
    return {
      ...base,
      ok: true,
      status: "AMBIGUOUS",
      applicationId,
      domain: null,
      url: null,
      https: null,
      domains: evidence,
      transport: deps.transport.name,
      response: { ok: response.ok, status: response.status, durationMs: response.durationMs },
      note: "multiple domains without primary evidence; full list returned, no arbitrary choice",
    };
  }

  return {
    ...base,
    ok: true,
    status: "READY",
    applicationId,
    domain: selected.host,
    url: selected.url,
    https: selected.https,
    domains: evidence,
    transport: deps.transport.name,
    response: { ok: response.ok, status: response.status, durationMs: response.durationMs },
    primaryEvidence,
    note: selected.https === null ? "domain evidenced; https flag absent so url is withheld (HTTPS never assumed)" : undefined,
  };
}
