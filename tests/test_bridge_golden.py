"""FORTIFY-01B — golden tests da ponte (source-scan, sem tocar na ponte).

Caso real de origem: audit da bridge tinha `model: ROLE_MODEL.worker`
hardcoded em 3 pontos do stream — corrigido à mão, sem teste anti-regressão.
Lê o source de /opt/gpu-bridge/proxy.mjs e trava os invariantes.
"""
import os
import unittest

PROXY = "/opt/gpu-bridge/proxy.mjs"


@unittest.skipUnless(os.access(PROXY, os.R_OK), "proxy.mjs inacessível")
class TestBridgeGolden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(PROXY, encoding="utf-8") as f:
            cls.lines = f.read().splitlines()

    def test_audit_sem_model_worker_hardcoded(self):
        """1. Nenhuma linha com audit( contém model: ROLE_MODEL.worker."""
        bad = [l for l in self.lines
               if "audit(" in l and "model: ROLE_MODEL.worker" in l]
        self.assertEqual(bad, [], f"audit com model hardcoded: {bad}")

    def test_message_start_sem_model_worker_hardcoded(self):
        """2. Nenhuma linha message_start contém model: ROLE_MODEL.worker."""
        bad = [l for l in self.lines
               if "message_start" in l and "model: ROLE_MODEL.worker" in l]
        self.assertEqual(bad, [], f"message_start com model hardcoded: {bad}")

    def test_escada_ok_honra_glm53(self):
        """3. ESCADA_OK honra z-ai/glm-5.3."""
        escada = [l for l in self.lines
                  if "ESCADA_OK" in l and "=" in l]
        self.assertTrue(escada, "definição de ESCADA_OK não encontrada")
        self.assertTrue(any("'z-ai/glm-5.3'" in l for l in escada),
                        f"ESCADA_OK não honra z-ai/glm-5.3: {escada}")

    def test_model_payload_model_em_audit_e_resp(self):
        """4. ≥2 ocorrências de model: payload.model em contextos audit/resp."""
        n = sum(1 for l in self.lines
                if "model: payload.model" in l
                and ("audit(" in l or "resp" in l or "send(" in l))
        self.assertGreaterEqual(n, 2, f"apenas {n} ocorrências de "
                                      "model: payload.model")


if __name__ == "__main__":
    unittest.main()
