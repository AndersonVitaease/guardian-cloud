// Guardian Core loader shim (neutral) — extracted VERBATIM from src/guardianVpsAdapter.ts
// so Guardian Cloud composition files can load the frozen Core without importing the
// redeploy adapter. Nothing in this module knows about applications, deployments or any
// operational identifier.
//
// Dependency resolution (honest): the frozen v0.1.0 package manifest has no
// "main" and no "exports" field, so the bare specifier is not Node-resolvable;
// the operator-side convention (same as memoryos-vps-guardian consumers) is
// the explicit source subpath. The load is DYNAMIC and cached: a runtime where
// the package is absent (e.g. images built from this context before the pinned
// dependency is declared in the eng-mcp manifest/Dockerfile) degrades
// FAIL-CLOSED (zero mutation) instead of crashing the server at import time.
import type { DomainAdapter, GuardianResult } from "memoryos-guardian-core/src/guardianCore.ts";

export type { DomainAdapter, GuardianResult } from "memoryos-guardian-core/src/guardianCore.ts";

export type GuardianCoreModule = {
  executeGuardianIntent: <I, B>(intent: I, adapter: DomainAdapter<I, B>) => Promise<GuardianResult>;
};

let guardianCoreCache: Promise<{ core: GuardianCoreModule | null; error: string | null }> | null = null;

// Load the frozen Guardian Core. Never throws: a missing package is an honest,
// structured unavailability (fail-closed), never a crash and never a mutation.
export function loadGuardianCore(): Promise<{ core: GuardianCoreModule | null; error: string | null }> {
  if (guardianCoreCache === null) {
    guardianCoreCache = import("memoryos-guardian-core/src/guardianCore.ts")
      .then((module) => ({ core: module as GuardianCoreModule, error: null }))
      .catch((error: unknown) => ({
        core: null,
        error: `GUARDIAN_CORE_IMPORT_FAILED: ${error instanceof Error ? error.message : String(error)}`,
      }));
  }
  return guardianCoreCache;
}
