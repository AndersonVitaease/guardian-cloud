# RELATORIO RD-GITGUARD-FIX-01
GITGUARD-FIX-OK
Fix: _classify_seg(toks, cmd=None); guard usa cmd se fornecido, senao " ".join(toks);
chamador em _bash_redirect passa " ".join(plan[0]). Suite: 36 passed
(test_enforce.py, test_worker_guard.py, test_fatiador.py).
