// SPIKE-DESK-CONN-01 — mini-gateway MCP com registro dinâmico REVERSO (throwaway, stdlib http).
// Contrato espelhado do mcp-gateway.js real: JSON-RPC 2.0, Bearer token, erros tipados
// MCP_SEM_TOKEN / MCP_TOKEN_INVALIDO / MCP_TOOL_DESCONHECIDA (+ CONECTOR_OFFLINE do spike).
// Rotas:
//   POST /mcp                 — initialize / tools/list / tools/call (cliente Guardian)
//   POST /conector/registrar  — conector registra tools {token, tools:[{name,description,inputSchema}]}
//   POST /conector/poll       — long-poll 1s: conector busca chamada pendente {token}
//   POST /conector/responder  — conector devolve {token, id, ok, texto|erro}
//   POST /conector/bye        — conector sai {token} -> tools saem do tools/list
'use strict';
const http = require('http');

const PORT = parseInt(process.env.SPIKE_PORT || '21001', 10);
const TOKENS = { 'tok-tenant-a': 'tenant-a' }; // token B inválido = qualquer outro

const registro = new Map(); // tenant -> Map(toolName -> {def, pending:[], online, ultimoPoll})
const respostas = new Map(); // callId -> {resolve, timer}
let seq = 0;

function jrpc(res, code, body) {
  const s = JSON.stringify(body);
  res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(s) });
  res.end(s);
}
function jrpcErr(res, code, id, tipo, message) {
  return jrpc(res, code, { jsonrpc: '2.0', id, error: { code: -32000, data: { tipo, message } } });
}
function auth(req) {
  const h = req.headers['authorization'] || '';
  const token = h.indexOf('Bearer ') === 0 ? h.slice(7).trim() : '';
  if (!token) return { err: ['MCP_SEM_TOKEN', 'Envie Authorization: Bearer <token MCP>.'] };
  if (!TOKENS[token]) return { err: ['MCP_TOKEN_INVALIDO', 'Token MCP inválido.'] };
  return { tenant: TOKENS[token], token };
}
function toolsOf(tenant) {
  const reg = registro.get(tenant);
  if (!reg) return [];
  return [...reg.values()].filter((v) => v.online).map((v) => v.def);
}
function readBody(req) {
  return new Promise((resolve) => {
    let d = '';
    req.on('data', (c) => (d += c));
    req.on('end', () => resolve(d));
  });
}

const server = http.createServer(async (req, res) => {
  const url = req.url.split('?')[0];
  if (url !== '/mcp' && !url.startsWith('/conector/')) {
    return jrpcErr(res, 404, null, 'MCP_REQUISICAO_INVALIDA', 'Rota desconhecida.');
  }

  // ---- canal do conector (reverso) ----
  if (url === '/conector/registrar') {
    const b = JSON.parse((await readBody(req)) || '{}');
    const tenant = TOKENS[b.token];
    if (!tenant) return jrpcErr(res, 401, null, 'MCP_TOKEN_INVALIDO', 'Token MCP inválido.');
    let reg = registro.get(tenant);
    if (!reg) registro.set(tenant, (reg = new Map()));
    for (const t of b.tools || []) {
      reg.set(t.name, { def: { name: t.name, description: t.description || '', inputSchema: t.inputSchema || { type: 'object', properties: {} } }, pending: [], online: true, ultimoPoll: Date.now() });
    }
    return jrpc(res, 200, { ok: true });
  }
  if (url === '/conector/poll') {
    const b = JSON.parse((await readBody(req)) || '{}');
    const tenant = TOKENS[b.token];
    if (!tenant) return jrpcErr(res, 401, null, 'MCP_TOKEN_INVALIDO', 'Token MCP inválido.');
    const reg = registro.get(tenant);
    if (reg) for (const v of reg.values()) { v.online = true; v.ultimoPoll = Date.now(); }
    const call = await new Promise((resolve) => {
      const t0 = Date.now();
      const iv = setInterval(() => {
        const r2 = registro.get(tenant);
        if (r2) for (const v of r2.values()) {
          const p = v.pending.shift();
          if (p) { clearInterval(iv); return resolve(p); }
        }
        if (Date.now() - t0 > 1000) { clearInterval(iv); return resolve(null); }
      }, 20);
    });
    return jrpc(res, 200, call ? { call: { id: call.id, name: call.name, arguments: call.arguments } } : {});
  }
  if (url === '/conector/responder') {
    const b = JSON.parse((await readBody(req)) || '{}');
    const tenant = TOKENS[b.token];
    if (!tenant) return jrpcErr(res, 401, null, 'MCP_TOKEN_INVALIDO', 'Token MCP inválido.');
    const w = respostas.get(b.id);
    if (w) { respostas.delete(b.id); clearTimeout(w.timer); w.resolve(b); }
    return jrpc(res, 200, { ok: true });
  }
  if (url === '/conector/bye') {
    const b = JSON.parse((await readBody(req)) || '{}');
    const tenant = TOKENS[b.token];
    if (tenant && registro.get(tenant)) for (const v of registro.get(tenant).values()) v.online = false;
    return jrpc(res, 200, { ok: true });
  }

  // ---- canal do cliente Guardian (/mcp) ----
  const a = auth(req);
  if (a.err) return jrpcErr(res, 401, null, a.err[0], a.err[1]);
  let msg = null;
  try { msg = JSON.parse(await readBody(req)); } catch (e) {}
  if (!msg || msg.jsonrpc !== '2.0' || !msg.method) {
    return jrpcErr(res, 400, msg && msg.id, 'MCP_REQUISICAO_INVALIDA', 'Corpo JSON-RPC 2.0 inválido.');
  }
  const id = msg.id == null ? null : msg.id;
  const method = String(msg.method);

  if (method === 'initialize') {
    return jrpc(res, 200, { jsonrpc: '2.0', id, result: { protocolVersion: '2024-11-05', capabilities: { tools: {} }, serverInfo: { name: 'spike-desk-conn', version: '0.0.1' } } });
  }
  if (method === 'tools/list') {
    return jrpc(res, 200, { jsonrpc: '2.0', id, result: { tools: toolsOf(a.tenant) } });
  }
  if (method === 'tools/call') {
    const name = msg.params && msg.params.name;
    const reg = registro.get(a.tenant);
    const entry = reg && reg.get(name);
    if (!entry) return jrpcErr(res, 200, id, 'MCP_TOOL_DESCONHECIDA', 'Tool desconhecida: ' + String(name));
    if (!entry.online) return jrpcErr(res, 200, id, 'CONECTOR_OFFLINE', 'Conector desktop offline para tool ' + String(name));
    const callId = 'c' + (++seq);
    const resp = await new Promise((resolve) => {
      const w = { resolve, timer: setTimeout(() => { respostas.delete(callId); entry.online = false; resolve({ ok: false }); }, 5000) };
      respostas.set(callId, w);
      entry.pending.push({ id: callId, name, arguments: (msg.params && msg.params.arguments) || {} });
    });
    if (!resp.ok) return jrpcErr(res, 200, id, 'CONECTOR_OFFLINE', 'Conector não respondeu (timeout) — tool ' + String(name));
    return jrpc(res, 200, { jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: resp.texto || '' }] } });
  }
  return jrpcErr(res, 200, id, 'MCP_METODO_DESCONHECIDO', 'Método não suportado: ' + method);
});

// watchdog: conector sem poll por >3s -> offline (tools saem do tools/list)
setInterval(() => {
  const agora = Date.now();
  for (const reg of registro.values()) for (const v of reg.values()) {
    if (v.online && agora - v.ultimoPoll > 3000) v.online = false;
  }
}, 500);

server.listen(PORT, () => console.log('spike-gateway :' + PORT));