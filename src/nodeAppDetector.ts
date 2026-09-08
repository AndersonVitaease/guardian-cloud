// GCLOUD-01C — engineering "node-app-detector" minimal helper.
//
// Purpose: give the future guardian.app.deploy SuperTool (GCLOUD-01D) a
// conservative, evidence-only answer to "is this a Node app, how do I start
// it, which port does it bind, which env variable NAMES does it need?".
//
// Hard rules (mission GCLOUD-01C):
// - runtime "node" is returned ONLY with clear evidence (a valid package.json).
//   No other runtime is ever attempted. Without package.json evidence the
//   result is UNSUPPORTED (nothing supplied) or NEEDS_INPUT/INVALID_PROJECT.
// - startCommand is derived ONLY from package.json evidence:
//     scripts.start             -> "npm start"          (canonical, sustained by the script)
//     one start-like script     -> "npm run <name>"     (serve | production)
//     main + evidenced entry    -> "node <main>"        (entry file must show runtime/start code)
//   "npm start" is NEVER invented without scripts.start. Two or more plausible
//   options with none clearly preferable -> NEEDS_INPUT with the alternatives.
// - port is derived ONLY from objective evidence (explicit literal in provided
//   runtime/config files or scripts, documented PORT=<n> value, or
//   process.env.PORT usage). No 3000/8080/framework default is ever assumed.
//   process.env.PORT with no evidenced value -> port:null, portStrategy:"ENV_PORT",
//   needsInput:["port"].
// - envRequirements contains variable NAMES ONLY. Values/secrets are never
//   collected, stored or returned. No giant scan: at most MAX_FILES_SCANNED files.
// - Ambiguity fails honestly (NEEDS_INPUT + alternatives/evidence); certainty
//   is never fabricated.
//
// Evidence sources (priority order, all caller-bounded):
//   1. package.json text (input.packageJsonText or files["package.json"])
//   2. its scripts
//   3. its engines
//   4. caller-provided files clearly related to runtime/start
//   5. existing port configuration in the project
//
// Status semantics:
//   DETECTED        runtime "node" evidenced AND startCommand resolved
//                   (port may still be pending -> needsInput:["port"])
//   NEEDS_INPUT     valid package.json but no usable/unique start evidence
//   UNSUPPORTED     no package.json evidence at all (Node cannot be claimed)
//   INVALID_PROJECT package.json present but unparseable / not a JSON object
//   UNKNOWN         reserved for indeterminate outcomes (not produced in normal flow)
//
// This module is an INTERNAL HELPER: zero mutation, zero transport, zero
// filesystem access, NOT registered in src/tools.ts (catalog untouched).
// Guardian gate: none — it never mutates anything.

export type NodeAppDetectorStatus =
  | "DETECTED"
  | "NEEDS_INPUT"
  | "UNSUPPORTED"
  | "INVALID_PROJECT"
  | "UNKNOWN";

export type NodeDetectorConfidence = "HIGH" | "MEDIUM" | "LOW";

export type PortStrategy = "FIXED" | "ENV_PORT" | "UNKNOWN";

export type NodeDetectorEvidence = {
  source: string;
  detail: string;
};

export type NodeAppDetectorInput = {
  /** Raw package.json text. When omitted, files["package.json"] is consulted. */
  packageJsonText?: string | null;
  /**
   * Bounded snapshot of project files relevant to runtime/start/port/env,
   * fileName -> text content. Only variable NAMES are recorded for env.
   */
  files?: Record<string, string>;
};

export type NodeAppDetectorResult = {
  /** true iff status === "DETECTED" (runtime + startCommand both resolved). */
  ok: boolean;
  status: NodeAppDetectorStatus;
  tool: "node-app-detector";
  runtime: "node" | null;
  startCommand: string | null;
  /** Plausible start options returned when resolution is ambiguous (NEEDS_INPUT). */
  startAlternatives: string[];
  port: number | null;
  portStrategy: PortStrategy;
  /** Env variable NAMES only — never values or secrets. */
  envRequirements: string[];
  /** Inputs the deploy composition must obtain before proceeding. */
  needsInput: string[];
  evidence: NodeDetectorEvidence[];
  confidence: NodeDetectorConfidence;
  note: string | null;
  mutated: false;
};

export const NODE_APP_DETECTOR_EVIDENCE_SOURCES = Object.freeze([
  "package.json",
  "package.json:scripts",
  "package.json:engines",
  "runtime/start files",
  "port configuration",
] as const);

export const NODE_DETECTOR_START_SCRIPT_CANDIDATES = Object.freeze([
  "serve",
  "production",
] as const);

export const NODE_APP_DETECTOR_GUARDIAN_GATE =
  "none (pure evidence helper; zero mutation, zero transport, zero filesystem access)";

const MAX_FILES_SCANNED = 24;
const MAX_FILE_CONTENT_CHARS = 65536;
const MAX_ENV_REQUIREMENTS = 20;
const MAX_PORT = 65535;

// A main entry file only counts as a start candidate when its content shows
// runtime/start code evidence (priority source 4) — never on the name alone.
const RUNTIME_ENTRY_EVIDENCE_PATTERN =
  /\brequire\s*\(|\bimport\s[\s\S]{0,200}?\bfrom\b|\bprocess\s*\.\s*(?:env|argv|exit|on)\b/;

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sortedUnique(values: string[]): string[] {
  return [...new Set(values)].sort();
}

function pushEvidence(evidence: NodeDetectorEvidence[], source: string, detail: string): void {
  evidence.push({ source, detail });
}

function validPortValues(values: { value: number; source: string }[]): { value: number; source: string }[] {
  return values.filter((v) => Number.isInteger(v.value) && v.value >= 1 && v.value <= MAX_PORT);
}

type PortScan = {
  fixed: { value: number; source: string }[];
  envPortValues: { value: number; source: string }[];
  envPortUsed: boolean;
  envNames: string[];
};

// Bounded content scan: fixed port literals, documented PORT values, PORT-env
// usage and env variable NAMES. Values of env variables are NEVER captured —
// only the match group holding the NAME is kept.
function scanContent(content: string, sourceLabel: string, scan: PortScan, isDotenv: boolean): void {
  if (/\bprocess\s*\.\s*env\s*\.\s*PORT\b/.test(content)) scan.envPortUsed = true;

  for (const match of content.matchAll(/\.listen\s*\(\s*(\d{2,5})\s*[,)]/g)) {
    scan.fixed.push({ value: Number(match[1]), source: `${sourceLabel}: .listen(<n>)` });
  }
  for (const match of content.matchAll(/\b["']?port["']?\s*:\s*["']?(\d{2,5})["']?\s*(?:[,}\n]|$)/gi)) {
    scan.fixed.push({ value: Number(match[1]), source: `${sourceLabel}: "port": <n>` });
  }
  for (const match of content.matchAll(/\bPORT\s*=\s*(\d{2,5})\b/g)) {
    scan.envPortValues.push({ value: Number(match[1]), source: `${sourceLabel}: PORT=<n>` });
  }
  for (const match of content.matchAll(/--port[= ](\d{2,5})\b/g)) {
    scan.fixed.push({ value: Number(match[1]), source: `${sourceLabel}: --port <n>` });
  }
  for (const match of content.matchAll(/\bprocess\s*\.\s*env\s*\.([A-Z_][A-Z0-9_]*)\b/g)) {
    scan.envNames.push(match[1]);
  }
  if (isDotenv) {
    for (const match of content.matchAll(/^([A-Z_][A-Z0-9_]*)\s*=/gm)) {
      scan.envNames.push(match[1]);
    }
  }
}

type StartResolution = {
  command: string | null;
  via: "scripts.start" | "start-like script" | "main entry file" | null;
  alternatives: string[];
  details: string[];
  ambiguous: boolean;
};

function resolveStartCommand(pkg: Record<string, unknown>, files: Record<string, string>): StartResolution {
  const scripts = isPlainObject(pkg.scripts) ? pkg.scripts : {};
  const startScript = asNonEmptyString(scripts.start);
  if (startScript !== null) {
    return {
      command: "npm start",
      via: "scripts.start",
      alternatives: [],
      details: [
        `package.json scripts.start = "${startScript}" — startCommand "npm start" is the canonical invocation sustained by this script`,
      ],
      ambiguous: false,
    };
  }

  const candidates: { command: string; detail: string }[] = [];
  for (const scriptName of NODE_DETECTOR_START_SCRIPT_CANDIDATES) {
    const raw = asNonEmptyString(scripts[scriptName]);
    if (raw !== null) {
      candidates.push({
        command: `npm run ${scriptName}`,
        detail: `package.json scripts.${scriptName} = "${raw}" — start-like script candidate`,
      });
    }
  }

  const main = asNonEmptyString(pkg.main);
  const mainContent = main !== null ? files[main] : undefined;
  if (typeof mainContent === "string" && RUNTIME_ENTRY_EVIDENCE_PATTERN.test(mainContent)) {
    candidates.push({
      command: `node ${main}`,
      detail: `package.json main = "${main}" and the entry file contains runtime/start code evidence`,
    });
  }

  if (candidates.length === 1) {
    const only = candidates[0];
    return {
      command: only.command,
      via: only.command.startsWith("npm run ") ? "start-like script" : "main entry file",
      alternatives: [],
      details: [only.detail],
      ambiguous: false,
    };
  }
  if (candidates.length >= 2) {
    return {
      command: null,
      via: null,
      alternatives: candidates.map((c) => c.command),
      details: candidates.map((c) => c.detail),
      ambiguous: true,
    };
  }
  return { command: null, via: null, alternatives: [], details: [], ambiguous: false };
}

function makeResult(overrides: Partial<NodeAppDetectorResult>): NodeAppDetectorResult {
  return {
    ok: false,
    status: "UNKNOWN",
    tool: "node-app-detector",
    runtime: null,
    startCommand: null,
    startAlternatives: [],
    port: null,
    portStrategy: "UNKNOWN",
    envRequirements: [],
    needsInput: [],
    evidence: [],
    confidence: "LOW",
    note: null,
    mutated: false,
    ...overrides,
  };
}

export function detectNodeApp(input: unknown): NodeAppDetectorResult {
  const notes: string[] = [];

  if (!isPlainObject(input)) {
    return makeResult({
      status: "NEEDS_INPUT",
      note: "detector input must be an object: { packageJsonText?: string, files?: Record<string, string> }",
    });
  }
  if (
    input.packageJsonText !== undefined &&
    input.packageJsonText !== null &&
    typeof input.packageJsonText !== "string"
  ) {
    return makeResult({ status: "NEEDS_INPUT", note: "packageJsonText must be a string when provided" });
  }

  const files: Record<string, string> = {};
  if (input.files !== undefined) {
    if (!isPlainObject(input.files)) {
      return makeResult({
        status: "NEEDS_INPUT",
        note: "files must be an object of fileName -> string content when provided",
      });
    }
    for (const [fileName, content] of Object.entries(input.files)) {
      if (typeof content === "string") files[fileName] = content;
      else notes.push(`files["${fileName}"] ignored (content is not a string)`);
    }
  }

  const packageJsonText = asNonEmptyString(input.packageJsonText) ?? asNonEmptyString(files["package.json"]);
  if (packageJsonText === null) {
    return makeResult({
      status: "UNSUPPORTED",
      note: "no package.json evidence supplied — Node runtime cannot be claimed and no other runtime is attempted",
    });
  }

  let pkg: Record<string, unknown>;
  try {
    const parsed: unknown = JSON.parse(packageJsonText);
    if (!isPlainObject(parsed)) {
      return makeResult({ status: "INVALID_PROJECT", note: "package.json parsed but is not a JSON object" });
    }
    pkg = parsed;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return makeResult({ status: "INVALID_PROJECT", note: `package.json is not valid JSON: ${message}` });
  }

  // ---- runtime evidence (priority sources 1-3) ----
  const evidence: NodeDetectorEvidence[] = [];
  pushEvidence(evidence, "package.json", "package.json parsed successfully (valid JSON object) — clear Node runtime evidence");
  const name = asNonEmptyString(pkg.name);
  if (name !== null) pushEvidence(evidence, "package.json", `name = "${name}"`);
  const engines = isPlainObject(pkg.engines) ? pkg.engines : null;
  const enginesNode = engines === null ? null : asNonEmptyString(engines.node);
  if (enginesNode !== null) pushEvidence(evidence, "package.json:engines", `engines.node = "${enginesNode}"`);

  // ---- startCommand resolution (priority sources 2 and 4) ----
  const start = resolveStartCommand(pkg, files);
  for (const detail of start.details) pushEvidence(evidence, "package.json:scripts", detail);
  if (start.ambiguous) {
    pushEvidence(
      evidence,
      "package.json:scripts",
      `${start.alternatives.length} plausible start options with none clearly preferable — failing honest (NEEDS_INPUT) with alternatives`,
    );
  } else if (start.command === null) {
    pushEvidence(
      evidence,
      "package.json:scripts",
      "no scripts.start, no start-like script and no evidenced entry file — startCommand cannot be resolved from evidence",
    );
  }

  // ---- port + env NAME scan (priority sources 4-5, bounded) ----
  const scan: PortScan = { fixed: [], envPortValues: [], envPortUsed: false, envNames: [] };

  const fileNames = Object.keys(files);
  if (fileNames.length > MAX_FILES_SCANNED) {
    notes.push(`files snapshot truncated to the first ${MAX_FILES_SCANNED} entries (no giant scan)`);
  }
  let envPortEvidenceFile: string | null = null;
  for (const fileName of fileNames.slice(0, MAX_FILES_SCANNED)) {
    const content = files[fileName];
    if (content.length > MAX_FILE_CONTENT_CHARS) {
      notes.push(`file "${fileName}" skipped (content exceeds ${MAX_FILE_CONTENT_CHARS} chars)`);
      continue;
    }
    const isDotenv = /(^|\/|\\)\.env($|\.)/.test(fileName);
    const namesBefore = scan.envNames.length;
    const envPortBefore = scan.envPortUsed;
    scanContent(content, `file "${fileName}"`, scan, isDotenv);
    if (scan.envPortUsed && !envPortBefore && envPortEvidenceFile === null) envPortEvidenceFile = fileName;
    if (scan.envNames.length > namesBefore) {
      const names = [...new Set(scan.envNames)].join(", ");
      pushEvidence(
        evidence,
        "runtime/start files",
        `env variable NAMES referenced in "${fileName}": ${names} (names only — values are never collected)`,
      );
    }
  }
  if (envPortEvidenceFile !== null) {
    pushEvidence(evidence, "port configuration", `process.env.PORT referenced in "${envPortEvidenceFile}" — binding is PORT-env driven`);
  }

  const pkgNamesBefore = scan.envNames.length;
  scanContent(packageJsonText, "package.json", scan, false);
  if (scan.envNames.length > pkgNamesBefore) {
    pushEvidence(evidence, "runtime/start files", "env variable NAMES referenced in package.json (names only — values are never collected)");
  }

  // ---- port decision: evidence only, no defaults ----
  let port: number | null = null;
  let portStrategy: PortStrategy = "UNKNOWN";
  const needsInput: string[] = [];

  const envPortCandidates = validPortValues(scan.envPortValues);
  if (scan.envPortUsed) {
    portStrategy = "ENV_PORT";
    const distinct = [...new Set(envPortCandidates.map((v) => v.value))];
    if (distinct.length === 1) {
      port = distinct[0];
      pushEvidence(
        evidence,
        "port configuration",
        `documented PORT value ${port} — evidenced by: ${envPortCandidates.map((v) => v.source).join("; ")}`,
      );
    } else if (distinct.length > 1) {
      const detail = `multiple documented PORT values (${distinct.join(", ")}) — no value adopted`;
      notes.push(detail);
      pushEvidence(evidence, "port configuration", detail);
    } else {
      const detail = "process.env.PORT is used but no fixed PORT value is evidenced — the deploy must provide PORT";
      notes.push(detail);
      pushEvidence(evidence, "port configuration", detail);
    }
  } else {
    const pool = [...validPortValues(scan.fixed), ...envPortCandidates];
    const distinct = [...new Set(pool.map((v) => v.value))];
    if (distinct.length === 1) {
      port = distinct[0];
      portStrategy = "FIXED";
      pushEvidence(
        evidence,
        "port configuration",
        `explicit port ${port} — evidenced by: ${pool.map((v) => v.source).join("; ")}`,
      );
    } else if (distinct.length > 1) {
      const detail = `multiple distinct explicit ports (${distinct.join(", ")}) — none adopted`;
      notes.push(detail);
      pushEvidence(evidence, "port configuration", detail);
    }
  }

  // ---- envRequirements: NAMES only, bounded ----
  let envRequirements = sortedUnique(scan.envNames);
  if (envRequirements.length > MAX_ENV_REQUIREMENTS) {
    envRequirements = envRequirements.slice(0, MAX_ENV_REQUIREMENTS);
    notes.push(`envRequirements truncated to the first ${MAX_ENV_REQUIREMENTS} names (no giant scan)`);
  }

  if (start.command === null) needsInput.unshift("startCommand");
  if (port === null) needsInput.push("port");

  const status: NodeAppDetectorStatus = start.command !== null ? "DETECTED" : "NEEDS_INPUT";
  const confidence: NodeDetectorConfidence =
    start.via === "scripts.start" ? "HIGH" : start.command !== null ? "MEDIUM" : "LOW";

  return makeResult({
    ok: status === "DETECTED",
    status,
    runtime: "node",
    startCommand: start.command,
    startAlternatives: start.alternatives,
    port,
    portStrategy,
    envRequirements,
    needsInput,
    evidence,
    confidence,
    note: notes.length > 0 ? notes.join(" ") : null,
  });
}
