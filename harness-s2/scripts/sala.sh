#!/usr/bin/env bash
# SALA-SH-01: agente sala 5-em-1 (status/missao/app/office/fila)
# Somente leitura; bash puro + python3 para JSON. Sem set -e; com set -u.
set -u

EV="${SALA_EVENTS_DIR:-/opt/mission-events}"

# ---------- V11: guard de interrupção (padrão mínimo do mecanico v1.1) ----------
# sala é leitura: guard mínimo — subcomando spawnado com guard_wait; se o filho
# morrer por sinal → JSON tipado {"ok":false,"error":"FILHO_MORTO"} e sair
# (nunca wait eterno).
guard_wait(){
  local pid="$1" rc=0
  if ! kill -0 "$pid" 2>/dev/null; then
    wait "$pid" 2>/dev/null; rc=$?
    [ "$rc" -eq 0 ] && return 0
    printf '{"ok":false,"error":"FILHO_MORTO"}\n'
    return 137
  fi
  wait "$pid"; rc=$?
  if [ "$rc" -ge 128 ]; then
    printf '{"ok":false,"error":"FILHO_MORTO"}\n'
    return 137
  fi
  return $rc
}
guarded(){
  "$@" &
  guard_wait "$!"; local rc=$?
  [ "$rc" -eq 137 ] && exit 0
  return $rc
}
QUEUE="${SALA_QUEUE_PATH:-$EV/orchestrator-queue.jsonl}"
APP_URL="${SALA_APP_URL:-http://127.0.0.1:8140}"
OFFICE_URL="${SALA_OFFICE_URL:-http://127.0.0.1:8113}"
RUNS_DIR="${SALA_RUNS_DIR:-/home/worker/harness-s2/runs}"
APP_JS="${SALA_APP_JS:-/home/worker/guardian-app/server.js}"
OFFICE_PY="${SALA_OFFICE_PY:-/home/worker/agent-office/run.py}"

# ---------- helpers ----------
jstr() { python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))' ;}
jnum() { python3 -c 'import json,sys;print(json.dumps(int(sys.argv[1])))' "$1" 2>/dev/null || echo null ;}
today_brt() { TZ=America/Sao_Paulo date +%Y-%m-%d ;}

# envolve stdout de um comando em string JSON segura; em erro devolve {"erro":...}
sec() { # sec "nome" "cmd..." -> imprime "nome": <json>,
  local name="$1"; shift
  local out
  if out=$("$@" 2>&1); then
    if printf '%s' "$out" | python3 -c 'import json,sys;json.load(sys.stdin)' 2>/dev/null; then
      printf '"%s": %s' "$name" "$out"
    else
      printf '"%s": %s' "$name" "$(printf '%s' "$out" | jstr)"
    fi
  else
    printf '"%s": {"erro": %s}' "$name" "$(printf '%s' "$out" | jstr)"
  fi
}

# ---------- seções (cada uma isolada; erro local não derruba o resto) ----------
secao_missoes_em_voo() {
  local today; today=$(today_brt)
  python3 - "$EV" "$today" <<'PY'
import json,sys,os,glob,datetime
ev,today=sys.argv[1],sys.argv[2]
ledger=os.path.join(ev,'ledger.jsonl')
closed=set()
if os.path.exists(ledger):
    for line in open(ledger,encoding='utf-8',errors='replace'):
        try:
            o=json.loads(line)
        except Exception: continue
        if o.get('event')=='mission_closed':
            mid=str(o.get('mission') or o.get('mission_id') or o.get('id') or '')
            ts=str(o.get('ts') or o.get('timestamp') or '')
            if mid: closed.add(mid)
runs=[]
for p in glob.glob(os.path.join(ev,'*harness-trail.jsonl')):
    try:
        lines=[l for l in open(p,encoding='utf-8',errors='replace') if l.strip()]
    except Exception: continue
    if not lines: continue
    try: first=json.loads(lines[0])
    except Exception: continue
    mid=str(first.get('mission') or first.get('mission_id') or first.get('id') or os.path.basename(p))
    ts=str(first.get('ts') or first.get('timestamp') or '')
    if ts.startswith(today) and mid not in closed:
        runs.append({'mission':mid,'trail':p,'inicio':ts})
print(json.dumps({'total':len(runs),'runs':runs},ensure_ascii=False))
PY
}

secao_pousos_hoje() {
  local today; today=$(today_brt)
  python3 - "$EV" "$today" <<'PY'
import json,sys,os
ev,today=sys.argv[1],sys.argv[2]
out=[]
for fn in ('ledger.jsonl',):
    p=os.path.join(ev,fn)
    if not os.path.exists(p): continue
    for line in open(p,encoding='utf-8',errors='replace'):
        try: o=json.loads(line)
        except Exception: continue
        if o.get('event')=='mission_closed':
            ts=str(o.get('ts') or o.get('timestamp') or '')
            if ts.startswith(today):
                out.append(o)
print(json.dumps({'total':len(out),'eventos':out},ensure_ascii=False))
PY
}

secao_vereditos_hoje() {
  local today; today=$(today_brt)
  python3 - "$EV" "$today" <<'PY'
import json,sys,os,glob
ev,today=sys.argv[1],sys.argv[2]
out=[]
for p in sorted(glob.glob(os.path.join(ev,'verify-*.json'))):
    try:
        st=os.stat(p)
        import datetime
        d=datetime.datetime.fromtimestamp(st.st_mtime,datetime.timezone(datetime.timedelta(hours=-3)))
        if d.strftime('%Y-%m-%d')!=today: continue
        o=json.load(open(p,encoding='utf-8',errors='replace'))
        out.append({'arquivo':os.path.basename(p),'veredito':o.get('verdict') or o.get('veredito') or o})
    except Exception as e:
        out.append({'arquivo':os.path.basename(p),'erro':str(e)})
print(json.dumps({'total':len(out),'vereditos':out},ensure_ascii=False))
PY
}

secao_custo_dia() {
  local today; today=$(today_brt)
  if [ -x "$RUNS_DIR/../scripts/custo_dia.py" ] || [ -f "$RUNS_DIR/../scripts/custo_dia.py" ]; then
    python3 "$RUNS_DIR/../scripts/custo_dia.py" 2>&1 || echo '{"erro":"custo_dia.py falhou"}'
  else
    echo '{"custo":null,"nota":"sem fonte local de custo (scripts/custo_dia.py ausente)"}'
  fi
}

secao_processos() {
  ps -eo pid,etime,args | grep -E 'mission_run|orchestrator-consumer|herdr' | grep -v grep || true
}

secao_servidores() {
  python3 - <<PY
import json,subprocess
def port(p):
    try:
        out=subprocess.run(['ss','-ltn'],capture_output=True,text=True,timeout=5).stdout
        open_=any((':'+str(p)+' ') in l for l in out.splitlines())
    except Exception as e:
        return {'porta':p,'aberta':None,'erro':str(e)}
    pid=None
    try:
        out=subprocess.run(['ss','-ltnp'],capture_output=True,text=True,timeout=5).stdout
        for l in out.splitlines():
            if (':%d '%p) in l and 'pid=' in l:
                pid=l.split('pid=')[1].split(',')[0].split(')')[0]
                break
    except Exception: pass
    return {'porta':p,'aberta':open_,'pid':pid}
print(json.dumps({'guardian_app':port(8140),'office':port(8113)}))
PY
}

secao_fila() {
  python3 - "$QUEUE" <<'PY'
import json,sys,os
q=sys.argv[1]
if not os.path.exists(q):
    print(json.dumps({'erro':'fila ausente: %s'%q})); raise SystemExit
lines=[l for l in open(q,encoding='utf-8',errors='replace') if l.strip()]
pend=[]
for l in lines[-50:]:
    try:
        o=json.loads(l)
        if o.get('status') in ('pending','PENDENTE','queued') or 'status' not in o:
            pend.append(o)
    except Exception: pass
print(json.dumps({'arquivo':q,'total_linhas':len(lines),'pendentes_ultimas3':pend[-3:]},ensure_ascii=False))
PY
}

secao_bloqueios() {
  python3 - "$EV" <<'PY'
import json,sys,os
ev=sys.argv[1]
def rd(p):
    try: return json.load(open(p,encoding='utf-8',errors='replace'))
    except Exception as e: return {'erro':str(e)}
breaker=rd(os.path.join(ev,'orchestrator-breaker.state.json'))
lock=os.path.exists(os.path.join(ev,'orchestrator-consumer.daemon.lock'))
pid=None
try: pid=int(open(os.path.join(ev,'orchestrator-consumer.pid')).read().strip())
except Exception: pass
alive=None
if pid:
    try:
        os.kill(pid,0); alive=True
    except Exception: alive=False
print(json.dumps({'breaker':breaker,'daemon_lock_presente':lock,'consumer_pid':pid,'consumer_pid_vivo':alive},ensure_ascii=False))
PY
}

# ---------- subcomandos ----------
cmd_status() {
  printf '{'
  sec missoes_em_voo secao_missoes_em_voo; printf ','
  sec pousos_hoje secao_pousos_hoje; printf ','
  sec vereditos_hoje secao_vereditos_hoje; printf ','
  sec custo_dia secao_custo_dia; printf ','
  sec processos secao_processos; printf ','
  sec servidores secao_servidores; printf ','
  sec fila secao_fila; printf ','
  sec bloqueios secao_bloqueios
  printf '}\n'
}

cmd_missao() {
  local id="${1:-}"
  [ -z "$id" ] && { echo '{"erro":"uso: sala.sh missao <ID>"}'; exit 0; }
  python3 - "$EV" "$RUNS_DIR" "$id" <<'PY'
import json,sys,os,glob,re
ev,runs,mid=sys.argv[1],sys.argv[2],sys.argv[3]
mil=mid.lower()
def j(o): return json.dumps(o,ensure_ascii=False)
# contrato
contrato={'id':mid,'arquivo':None,'primeiras_40_linhas':None}
for p in glob.glob(os.path.join(ev,'missao*.md')):
    try: txt=open(p,encoding='utf-8',errors='replace').read()
    except Exception: continue
    if mil in os.path.basename(p).lower() or mil in txt.lower()[:4000]:
        contrato['arquivo']=p
        contrato['primeiras_40_linhas']='\n'.join(txt.splitlines()[:40])
        break
# run dir mais recente do slug
slug=re.sub(r'[^a-z0-9]+','-',mil).strip('-')
cand=sorted(glob.glob(os.path.join(runs,'*'+slug+'*')),key=os.path.getmtime,reverse=True)
run={'slug':slug,'dir':cand[0] if cand else None,'listagem':None}
if cand:
    try: run['listagem']=sorted(os.listdir(cand[0]))[:50]
    except Exception as e: run['erro']=str(e)
# trail
trail=None
tp=os.path.join(cand[0],'harness-trail.jsonl') if cand else None
if tp and os.path.exists(tp):
    lines=[l for l in open(tp,encoding='utf-8',errors='replace') if l.strip()]
    trail=[l for l in lines[-20:]]
else:
    for p in glob.glob(os.path.join(ev,'*'+slug+'*harness-trail.jsonl')):
        lines=[l for l in open(p,encoding='utf-8',errors='replace') if l.strip()]
        trail=[l for l in lines[-20:]]; break
# veredito
veredito=None
vp=os.path.join(ev,'verify-%s.json'%mid)
if os.path.exists(vp):
    try: veredito=json.load(open(vp,encoding='utf-8',errors='replace'))
    except Exception as e: veredito={'erro':str(e)}
print(j({'contrato':contrato,'run':run,'trail':trail,'veredito':veredito}))
PY
}

cmd_app() {
  python3 - "$APP_URL" "$APP_JS" <<'PY'
import json,sys,os,subprocess,re,urllib.request
url,js=sys.argv[1],sys.argv[2]
def get(u,t=3):
    try:
        r=urllib.request.urlopen(u,timeout=t)
        return r.status,r.read().decode('utf-8','replace')
    except Exception as e:
        return None,str(e)
res={'url':url}
st,body=get(url+'/api/tasks')
try: res['tasks']=json.loads(body) if st else None
except Exception: res['tasks_raw']=body
res['tasks_http']=st
# rotas /api/* do server.js
rotas=[]
try:
    for m in re.finditer(r"(?:app\.(?:get|post|put|delete)|\.(?:get|post))\(\s*['\"]([^'\"]+)['\"]",open(js,encoding='utf-8',errors='replace').read()):
        rotas.append(m.group(1))
except Exception as e: res['rotas_erro']=str(e)
res['rotas_api']=sorted(set(r for r in rotas if r.startswith('/api')))
# health: tenta rotas candidatas
for h in ('/api/health','/health','/healthz','/api/status'):
    st,body=get(url+h)
    if st:
        res['health_rota']=h; res['health']=body[:500]; break
else:
    res['health_rota']=None; res['health']='nao encontrada entre candidatas'
print(json.dumps(res,ensure_ascii=False))
PY
}

cmd_office() {
  python3 - "$OFFICE_URL" "$OFFICE_PY" <<'PY'
import json,sys,re,urllib.request
url,py=sys.argv[1],sys.argv[2]
def get(u,t=3):
    try:
        r=urllib.request.urlopen(u,timeout=t); return r.status,r.read().decode('utf-8','replace')
    except Exception as e: return None,str(e)
res={'url':url}
st,body=get(url+'/state')
if st:
    try:
        o=json.loads(body)
        prog=o.get('progress') or {}
        res['state_resumo']={'agents_count':len(o.get('agents') or []),'rank':prog.get('rank'),'xp':prog.get('xp'),'cosmetics':o.get('cosmetics')}
        res['state_completo']=o
    except Exception: res['state_raw']=body[:2000]
else:
    res['state_erro']=body
# rotas do run.py
rotas=[]
try:
    src=open(py,encoding='utf-8',errors='replace').read()
    for m in re.finditer(r"(?:path|route)?\s*['\"](/[\w/-]*)['\"]",src):
        rotas.append(m.group(1))
except Exception as e: res['rotas_erro']=str(e)
res['rotas_candidatas']=sorted(set(rotas))[:30]
# sessoes/personagens: tenta rotas candidatas
for r in ('/sessions','/api/sessions','/characters','/api/characters','/personagens'):
    st,body=get(url+r)
    if st:
        res.setdefault('sessoes',{})[r]=body[:1000]
print(json.dumps(res,ensure_ascii=False))
PY
}

cmd_fila() {
  printf '{'
  sec fila secao_fila; printf ','
  sec bloqueios secao_bloqueios
  printf '}\n'
}

usage() {
  cat <<'EOF'
uso: sala.sh <subcomando>
  status            visão geral (missoes, pousos, vereditos, custo, processos, servidores, fila, bloqueios)
  missao <ID>       contrato, run, trail (20 linhas) e veredito da missão (case-insensitive)
  app               guardian-app (8140): tasks, health, rotas /api/*
  office            agent-office (8113): /state resumido, sessões/personagens
  fila              queue.jsonl, consumer pid/heartbeat, breaker, lock
env: SALA_QUEUE_PATH, SALA_APP_URL, SALA_OFFICE_URL, SALA_EVENTS_DIR, SALA_RUNS_DIR
EOF
}

case "${1:-}" in
  status) guarded cmd_status ;;
  missao) shift; guarded cmd_missao "$@" ;;
  app) guarded cmd_app ;;
  office) guarded cmd_office ;;
  fila) guarded cmd_fila ;;
  --help|-h|'') usage ;;
  *) usage; exit 0 ;;
esac