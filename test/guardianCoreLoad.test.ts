import { test } from "node:test";
import assert from "node:assert/strict";
import { loadGuardianCore } from "../src/guardianCoreLoad.ts";

// Happy path: o pacote memoryos-guardian-core está instalado; o loader dinâmico
// resolve o módulo com executeGuardianIntent e error:null (nunca lança).
test("loadGuardianCore: carregamento ok — módulo com executeGuardianIntent e error null", async () => {
  const result = await loadGuardianCore();
  assert.equal(result.error, null);
  assert.ok(result.core, "core deve estar presente quando o pacote resolve");
  assert.equal(typeof result.core?.executeGuardianIntent, "function");
});

test("loadGuardianCore: cache — segunda chamada retorna a MESMA promise (import único)", () => {
  const a = loadGuardianCore();
  const b = loadGuardianCore();
  assert.equal(a, b, "loader deve cachear a promise (uma única tentativa de import)");
});

test("loadGuardianCore: contrato do tipo GuardianCoreModule respeitado no módulo carregado", async () => {
  const { core } = await loadGuardianCore();
  assert.ok(core);
  // executeGuardianIntent é assíncrona (retorna Promise<GuardianResult>)
  const probe = core!.executeGuardianIntent as unknown as (...args: unknown[]) => unknown;
  assert.ok(probe.length >= 2, "executeGuardianIntent recebe (intent, adapter)");
});
