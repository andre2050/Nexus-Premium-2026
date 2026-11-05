const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode');
const pino = require('pino');
const { spawn } = require('child_process');
let ffmpegPath = null;
let mime = null;
try { ffmpegPath = require('ffmpeg-static'); } catch (_) {}
try { mime = require('mime-types'); } catch (_) {}
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  fetchLatestWaWebVersion,
  Browsers,
  downloadContentFromMessage,
  makeCacheableSignalKeyStore,
  BufferJSON,
  initAuthCreds,
  proto,
  isJidBroadcast,
  isJidNewsletter,
  WAMessageStatus,
} = require('@whiskeysockets/baileys');
// Cache dos pedidos de reenvio (13/10/2026): o mesmo do Baileys, criado UMA vez
// por processo para sobreviver as reconexoes. Sem o pacote, um Map simples.
let NodeCache = null;
try { const m = require('@cacheable/node-cache'); NodeCache = m.default || m.NodeCache || null; } catch (_) {}

const PORT = Number(process.env.MARKXLVIII_WA_PORT || process.env.CYBERBOT_WA_PORT || 8765);
const ROOT = __dirname;
const AUTH_DIR = path.join(ROOT, 'auth');
const CREDS_FILE = path.join(AUTH_DIR, 'creds.json');
const QR_FILE = path.join(ROOT, 'wa_qr.png');
const STATUS_FILE = path.join(ROOT, 'status.json');
const LOG_FILE = path.join(ROOT, 'bridge.log');
const BAILEYS_LOG_FILE = path.join(ROOT, 'baileys.log');
const LAST_DISCONNECT_FILE = path.join(ROOT, 'last_disconnect.json');
const DB_FILE = path.join(ROOT, 'mark_xlviii_whatsapp_db.json');
const DB_BAK_FILE = DB_FILE + '.bak';
const MEDIA_DIR = path.join(ROOT, 'media');
const VERSION = '2026-10-13-ponte-estavel-39';
const BOOT_AT = new Date().toISOString();
const MAX_SEND_BYTES = Number(process.env.MARKXLVIII_WHATSAPP_MAX_FILE_MB || process.env.CYBERBOT_WHATSAPP_MAX_FILE_MB || 100) * 1024 * 1024;
try { fs.mkdirSync(MEDIA_DIR, { recursive: true }); } catch (_) {}

// ARQUIVOS DE LOG RODAM NO START (13/10/2026): acima de 5 MB o atual vira .1
// (o .1 velho some). Roda antes do primeiro log() deste processo.
function rodarLogSeGrande(arquivo, limite = 5 * 1024 * 1024) {
  try {
    const st = fs.statSync(arquivo);
    if (st.size > limite) fs.renameSync(arquivo, arquivo + '.1');
  } catch (_) {}
}
rodarLogSeGrande(LOG_FILE);
rodarLogSeGrande(BAILEYS_LOG_FILE);

// GRAVACAO ATOMICA (13/10/2026). O JARVIS mata a ponte a qualquer hora; quem
// lia o arquivo no meio da gravacao pegava JSON cortado. Agora grava em .tmp e
// troca pelo nome certo (rename). No Windows o rename pode dar EPERM/EBUSY
// (antivirus, alguem lendo): tenta 3 vezes e, se nao der, grava direto.
function dormirSync(ms) { try { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms); } catch (_) {} }
function renomearComRetentativaSync(origem, destino) {
  for (let i = 0; i < 3; i++) {
    try { fs.renameSync(origem, destino); return true; }
    catch (e) {
      if (!['EPERM', 'EBUSY', 'EACCES'].includes(e.code)) throw e;
      dormirSync(15 * (i + 1));
    }
  }
  return false;
}
function gravarArquivoAtomicoSync(arquivo, texto) {
  const tmp = arquivo + '.tmp';
  fs.writeFileSync(tmp, texto);
  if (renomearComRetentativaSync(tmp, arquivo)) return;
  fs.writeFileSync(arquivo, texto);
  try { fs.unlinkSync(tmp); } catch (_) {}
}
function lerJsonSeguro(arquivo) {
  try { return JSON.parse(fs.readFileSync(arquivo, 'utf8')); } catch (_) { return null; }
}
const dormir = (ms) => new Promise(r => setTimeout(r, ms));
// Sai com o codigo pedido mesmo se um ouvinte de 'exit' de alguma biblioteca
// quebrar (o erro voltava pelo process.exit e a ponte ficava viva).
function sairCom(codigo) {
  process.exitCode = codigo;
  try { process.exit(codigo); } catch (e) { try { fs.appendFileSync(LOG_FILE, `[${new Date().toISOString()}] exit handler failed ${e && e.message}\n`); } catch (_) {} }
  try { process.reallyExit(codigo); } catch (_) {}
}

// LOGGER DO BAILEYS (13/10/2026). Era 'silent': o motivo real do 401 de 06/10
// e das quedas 500 se perdeu. Agora 'warn' num arquivo proprio (baileys.log),
// sem segurar o node (sync:false). Criado UMA vez por processo.
// O arquivo e aberto AQUI, sincrono: com o caminho, o pino abre depois, e um
// process.exit logo no comeco (porta ocupada) quebrava no flush de saida do
// pino ("sonic boom is not ready yet") e o processo nao saia.
let baileysDestino = null;
function criarLoggerBaileys() {
  try {
    const fd = fs.openSync(BAILEYS_LOG_FILE, 'a');
    baileysDestino = pino.destination({ dest: fd, sync: false });
    // Sem ouvinte, um erro do arquivo (travado, disco cheio) derrubaria o node.
    if (baileysDestino && baileysDestino.on) baileysDestino.on('error', () => {});
    return pino({ level: 'warn', timestamp: pino.stdTimeFunctions ? pino.stdTimeFunctions.isoTime : undefined }, baileysDestino);
  } catch (_) {
    return pino({ level: 'silent' });
  }
}
const baileysLogger = criarLoggerBaileys();

// Mapa simples no lugar do NodeCache, se o pacote nao existir.
class CacheSimples {
  constructor(max = 5000) { this.mapa = new Map(); this.max = max; }
  get(k) { return this.mapa.get(k); }
  set(k, v) { this.mapa.set(k, v); while (this.mapa.size > this.max) this.mapa.delete(this.mapa.keys().next().value); return true; }
  del(k) { return this.mapa.delete(k); }
  flushAll() { this.mapa.clear(); }
}
const msgRetryCounterCache = NodeCache ? new NodeCache({ stdTTL: 3600, useClones: false }) : new CacheSimples();

// MENSAGENS ENVIADAS NA MEMORIA (13/10/2026). Quando o celular do destinatario
// nao consegue decifrar, ele pede reenvio; o Baileys so reenvia se o getMessage
// devolver a mensagem. Sem isso a pessoa ficava com "Aguardando mensagem".
// LRU de 1000: o mais velho sai primeiro.
const enviadasCache = new Map();
const LIMITE_ENVIADAS = 1000;
function guardarEnviada(key, message) {
  const id = key && key.id;
  if (!id || !message) return;
  enviadasCache.delete(id);
  enviadasCache.set(id, message);
  while (enviadasCache.size > LIMITE_ENVIADAS) enviadasCache.delete(enviadasCache.keys().next().value);
}
async function getMessageGuardada(key) {
  const id = key && key.id;
  if (!id || !enviadasCache.has(id)) return undefined;
  const m = enviadasCache.get(id);
  enviadasCache.delete(id); enviadasCache.set(id, m);
  return m;
}
function ignorarJid(jid) {
  const j = String(jid || '');
  if (typeof isJidBroadcast === 'function' ? isJidBroadcast(j) : j.endsWith('@broadcast')) return true;
  if (typeof isJidNewsletter === 'function' ? isJidNewsletter(j) : j.endsWith('@newsletter')) return true;
  return false;
}

let sock = null;
let connected = false;
let lastQr = '';
let lastEvent = 'starting';
let startedAt = new Date().toISOString();
let contacts = {};
let chats = {};
let groups = {};
let aliases = {};
let messages = [];
let starting = false;
let qrWatchdog = null;
// UMA CONEXAO SO (23/09/2026, "estou conectado e o JARVIS diz que nao").
//
// O bridge.log de 22/09 mostrou DUAS conexoes do Baileys vivas no mesmo
// processo: o botao "GERAR QR NOVO" (/reset) encerrava a conexao atual e
// agendava uma nova — e o evento de fechamento DESSA MESMA conexao agendava
// outra ("reconnect"), 3 s depois. Uma conectava de verdade; a outra ficava
// gerando QR Code a cada minuto e escrevendo `connected:false, has_qr:true` por
// cima. O JARVIS lia isso e respondia "o WhatsApp ainda nao esta conectado,
// escaneie o QR". Depois as duas se derrubavam em laco (codigo 440: "outra
// sessao substituiu esta"), e a cada queda nascia mais uma.
//
// Agora cada conexao tem um NUMERO (`geracao`). So a conexao da geracao atual
// pode mudar o estado, gravar credencial e pedir reconexao; a antiga e
// encerrada antes de a nova nascer, e o que ela disser depois disso e ignorado.
// E so existe UMA reconexao agendada por vez.
let geracao = 0;
let reconexao = null;
// Estado da religacao (13/10/2026):
// - socketVivo: existe um socket desta geracao esperando o 'open' (ou aberto);
// - falhasSeguidas: quedas sem 'open' no meio (espera 3 s, 6 s, 12 s... 60 s);
// - paradoMotivo: codigo que pede acao do usuario (banned, qr_expired,
//   version_rejected, user_logged_out, multidevice_mismatch). Com ele a ponte
//   NAO religa sozinha; so /reset ou /start tiram daqui;
// - desligando: /shutdown em andamento, nada mais religa.
let socketVivo = false;
let falhasSeguidas = 0;
let falhasStart = 0;
let paradoMotivo = '';
let tentouVersaoNova = false;
let desligando = false;
let finalizado = false;
let startPendente = null;
let authAtual = null;
// VERSAO DO WHATSAPP WEB UMA VEZ POR PROCESSO (13/10/2026). Era buscada no
// GitHub a cada reconexao (de 50 em 50 min): se o GitHub demorasse, o start
// caia; se falhasse, o Baileys usava a versao embutida de 2025 e o WhatsApp
// recusava (405). Agora: GitHub com teto de 5 s, nunca abaixo do PISO.
const PISO_VERSAO_WA = [2, 3000, 1043857760];
let versaoWa = null;
let versaoOrigem = '';
function cancelarReconexao() { if (reconexao) clearTimeout(reconexao); reconexao = null; }
function encerrarConexaoAtual() {
  geracao += 1;                 // o que a conexao velha disser daqui em diante nao vale
  cancelarReconexao();
  socketVivo = false;
  const velho = sock;
  sock = null;
  if (velho) { try { if (velho.end) velho.end(undefined); } catch (_) {} }
}
function agendarReconexao(minha, espera) {
  if (minha !== geracao || reconexao || desligando) return false;
  log('Reconnect scheduled in', `${espera}ms`);
  reconexao = setTimeout(() => {
    reconexao = null;
    if (minha !== geracao || desligando) return;
    start({ fresh: false }).catch(err => log('Reconnect failed', err?.stack || err));
  }, espera);
  return true;
}
// START QUE FALHOU TENTA DE NOVO (13/10/2026): 10 s, 20 s, 40 s, ate 60 s.
// Antes o catch so registrava e a ponte ficava parada ate reiniciar o JARVIS.
function agendarNovoStart() {
  if (reconexao || desligando || paradoMotivo) return;
  falhasStart += 1;
  const espera = Math.min(60000, 10000 * Math.pow(2, falhasStart - 1));
  const minha = geracao;
  log('Start retry scheduled in', `${espera}ms`);
  reconexao = setTimeout(() => {
    reconexao = null;
    if (minha !== geracao || desligando) return;
    start({ fresh: false }).catch(err => log('Start retry failed', err?.stack || err));
  }, espera);
}
function sessaoSalva() { try { return fs.existsSync(CREDS_FILE); } catch (_) { return false; } }
// Ha uma conexao a caminho (start rodando, religacao agendada ou socket
// esperando o 'open') com sessao salva e nada pedindo acao do usuario.
function reconectandoAgora() {
  if (currentConnected() || desligando || paradoMotivo || freshLoginRequired || lastQr) return false;
  if (!sessaoSalva()) return false;
  return Boolean(starting || reconexao || socketVivo);
}
let lastFailedName = '';
let pendingLeaveGroup = null;
let recentDeleteBatch = { signature: '', at: 0, response: null };
let lastDisconnectReason = '';
let watchConfig = { enabled: false, mode: 'off', contacts: [], include_groups: true, target_type: 'all', updated_at: '' };
let alertQueue = [];
let alertSeen = {};
let agentQueue = [];
let agentSeen = {};
let mediaDownloadActive = new Set();
let freshLoginRequired = false;
let manualLogoutInProgress = false;
let contactSyncInFlight = false;
let ultimaAgendaSob = 0;   // 6.1.5: last on-demand address book fetch
let ultimoErro = '';
let ultimoErroEm = '';
let dbBloqueado = false;
// ULTIMO DESLIGAMENTO EM ARQUIVO (13/10/2026). O motivo do 401 de 06/10 vivia
// so na memoria: a ponte reiniciava e o status voltava sem explicar que o
// celular tinha derrubado a sessao. Agora fica em last_disconnect.json.
let ultimoDesligamento = lerJsonSeguro(LAST_DISCONNECT_FILE);
if (ultimoDesligamento && typeof ultimoDesligamento !== 'object') ultimoDesligamento = null;
if (ultimoDesligamento && ultimoDesligamento.logged_out && !fs.existsSync(CREDS_FILE)) {
  lastDisconnectReason = String(ultimoDesligamento.reason || 'user_logged_out');
  freshLoginRequired = true;
}



// SO O ARQUIVO (13/10/2026). O Python mandava o stdout do node para o MESMO
// bridge.log e cada linha saia dobrada (ou cortada). Agora o console so
// recebe a linha quando e um terminal de verdade.
function log(...args) {
  const line = `[${new Date().toISOString()}] ` + args.map(a => {
    try { return typeof a === 'string' ? a : JSON.stringify(a); } catch (_) { return String(a); }
  }).join(' ');
  if (process.stdout && process.stdout.isTTY) console.log(line);
  try { fs.appendFileSync(LOG_FILE, line + '\n'); } catch (_) {}
}
function withTimeout(promise, ms, label) {
  return Promise.race([
    promise,
    new Promise((_resolve, reject) => setTimeout(() => reject(new Error(`${label} timeout after ${ms}ms`)), ms))
  ]);
}
// BANCO QUEBRADO NAO VIRA BANCO VAZIO (13/10/2026). Antes, um JSON cortado
// (ponte morta no meio da gravacao) deixava tudo vazio na memoria e o proximo
// saveDb gravava o vazio POR CIMA: sumiam contatos e apelidos. Agora tenta o
// .bak; o quebrado e guardado como .quebrado-<data> e nunca e sobrescrito.
function loadDb() {
  let d = null;
  let quebrado = false;
  if (fs.existsSync(DB_FILE)) {
    try { d = JSON.parse(fs.readFileSync(DB_FILE, 'utf8') || '{}'); }
    catch (e) { quebrado = true; log('loadDb error', e.message); }
  }
  if (!d && fs.existsSync(DB_BAK_FILE)) {
    try { d = JSON.parse(fs.readFileSync(DB_BAK_FILE, 'utf8') || '{}'); log('loadDb: usando a copia', DB_BAK_FILE); }
    catch (e) { log('loadDb: copia .bak tambem quebrada', e.message); }
  }
  if (quebrado) {
    const guardado = `${DB_FILE}.quebrado-${new Date().toISOString().replace(/[:.]/g, '-')}`;
    try { fs.renameSync(DB_FILE, guardado); log('loadDb: banco quebrado guardado em', guardado); }
    catch (e) {
      // Nao deu para tirar o quebrado do caminho: nao grava nada por cima dele.
      dbBloqueado = true;
      log('loadDb: nao consegui guardar o banco quebrado; gravacao do banco suspensa', e.message);
    }
  }
  try {
    if (d) {
      contacts = d.contacts || {};
      chats = d.chats || {};
      groups = d.groups || {};
      aliases = d.aliases || {};
      messages = Array.isArray(d.messages) ? d.messages : [];
      // LIMPEZA DOS REGISTROS VAZIOS (23/09/2026). O banco do Diego tinha 3.000
      // mensagens e 2.958 eram "[unknown]": avisos sem conteudo (mensagem que o
      // WhatsApp nao deixou decifrar, sincronizacao de chave) que entraram em
      // rajada de madrugada e empurraram as conversas de verdade para fora do
      // teto de 3.000. "Ve minhas ultimas mensagens" nao achava o privado.
      const antes = messages.length;
      messages = messages.filter(x => x && !REGISTRO_VAZIO.has(String(x.type || '')) && x.text !== '[unknown]');
      if (messages.length !== antes) log(`[db] ${antes - messages.length} registros vazios removidos`);
      watchConfig = d.watchConfig || watchConfig;
      alertQueue = Array.isArray(d.alertQueue) ? d.alertQueue : [];
      alertSeen = d.alertSeen || {};
      agentQueue = Array.isArray(d.agentQueue) ? d.agentQueue : [];
      agentSeen = d.agentSeen || {};
      pendingLeaveGroup = d.pendingLeaveGroup || pendingLeaveGroup;
      podarFilas();
      limparNomesVoce();   // 6.1.5: chats wrongly named "Você"
    }
  } catch (e) { log('loadDb error', e.message); }
}
// FILAS E "JA VISTOS" COM TETO (13/10/2026): agentSeen/alertSeen cresciam para
// sempre e a fila do agente ficava presa em 500 itens de semanas atras.
function podarVistos(obj, max = 3000) {
  const chaves = Object.keys(obj || {});
  if (chaves.length <= max) return obj || {};
  const novo = {};
  for (const k of chaves.slice(-max)) novo[k] = obj[k];
  return novo;
}
function podarFilas() {
  alertSeen = podarVistos(alertSeen);
  agentSeen = podarVistos(agentSeen);
  const limite = Date.now() - 24 * 3600 * 1000;
  agentQueue = agentQueue.filter(x => {
    const t = Date.parse(x?.created_at || '') || (Number(x?.timestamp || 0) * 1000);
    return !t || t >= limite;
  });
}
// Gravacao atomica + .bak (13/10/2026): o atual vira .bak e o .tmp novo entra
// no lugar. Se a ponte morrer no meio, sobra o banco inteiro (ou o .bak).
// Sem indentacao: o arquivo (2,7 MB no PC do Diego) fica menor e grava mais rapido.
function saveDbAgora() {
  if (saveDbTimer) { clearTimeout(saveDbTimer); saveDbTimer = null; }
  if (dbBloqueado) return;
  try {
    if (messages.length > 3000) messages = messages.slice(-3000);
    podarFilas();
    const texto = JSON.stringify({ contacts, chats, groups, aliases, messages, watchConfig, alertQueue, alertSeen, agentQueue, agentSeen, pendingLeaveGroup, updated_at: new Date().toISOString() });
    const tmp = DB_FILE + '.tmp';
    fs.writeFileSync(tmp, texto);
    try { if (fs.existsSync(DB_FILE)) renomearComRetentativaSync(DB_FILE, DB_BAK_FILE); } catch (_) {}
    if (!renomearComRetentativaSync(tmp, DB_FILE)) {
      fs.writeFileSync(DB_FILE, texto);
      try { fs.unlinkSync(tmp); } catch (_) {}
    }
  } catch (e) { log('saveDb error', e.message); }
}
// GRAVAR O BANCO NO MAXIMO A CADA 1,5 s (23/09/2026). Era a cada mensagem,
// contato e grupo: um arquivo de ~3 MB escrito de uma vez, com o Node parado
// esperando. Numa sincronizacao chegam centenas de eventos por minuto, a ponte
// deixava de atender a porta e o JARVIS entendia "WhatsApp desconectado". Os
// dados continuam na memoria na hora; so o arquivo e que espera 1,5 s.
let saveDbTimer = null;
function saveDb() {
  if (saveDbTimer) return;
  saveDbTimer = setTimeout(() => { saveDbTimer = null; saveDbAgora(); }, 1500);
}
// Sinal de fechar: o mesmo caminho do POST /shutdown (13/10/2026), que espera
// as credenciais terminarem de gravar antes de sair.
for (const sinal of ['SIGINT', 'SIGTERM', 'SIGBREAK']) {
  try { process.on(sinal, () => { encerrarComCalma(sinal); }); } catch (_) {}
}
// Aviso de protocolo, sem nada para ler: nao entra no banco. Ver loadDb.
const REGISTRO_VAZIO = new Set(['unknown', 'senderKeyDistributionMessage', 'messageContextInfo']);
loadDb();
function currentConnected() { return Boolean(connected && sock && sock.user); }
function contactCount() { return Object.keys(contacts || {}).length; }
function chatCount() { return Object.keys(chats || {}).length; }
function groupCount() { return Object.keys(groups || {}).length; }
function msgCount() { return Array.isArray(messages) ? messages.length : 0; }
function lastMessage() { return messages.length ? messages[messages.length - 1] : null; }
// STATUS COM DONO E PULSO (13/10/2026). O status.json da ponte MORTA era lido
// como verdade por ate 45 s. Agora diz quem gravou (writer/pid/boot_at), se ha
// sessao salva, se precisa de QR, se esta religando e qual foi o ultimo
// desligamento. Gravacao atomica (.tmp + rename): quem le nunca pega metade.
function saveStatus(extra = {}) {
  const isConnected = currentConnected();
  const salva = sessaoSalva();
  const hasQr = Boolean(lastQr && !isConnected && fs.existsSync(QR_FILE));
  const data = {
    ok: true,
    bridge: 'mark-xlviii-whatsapp-baileys',
    version: VERSION,
    writer: 'node',
    pid: process.pid,
    boot_at: BOOT_AT,
    bridge_root: ROOT,
    connected: isConnected,
    session_saved: salva,
    needs_qr: false,
    reconnecting: false,
    last_disconnect: ultimoDesligamento || null,
    wa_version: versaoWa ? versaoWa.join('.') : '',
    wa_version_source: versaoOrigem,
    last_error: ultimoErro,
    last_error_at: ultimoErroEm,
    has_qr: hasQr,
    qr_file: QR_FILE,
    status_file: STATUS_FILE,
    log_file: LOG_FILE,
    db_file: DB_FILE,
    port: PORT,
    contacts: contactCount(),
    chats: chatCount(),
    groups: groupCount(),
    messages: msgCount(),
    safe_sync: true,
    full_history_forced: false,
    note: 'Modo seguro: lê novas mensagens e qualquer histórico que o WhatsApp liberar sem derrubar a conexão.',
    last_message: lastMessage(),
    alert_watch: watchConfig,
    alert_queue: alertQueue.length,
    agent_queue: agentQueue.length,
    pending_leave_group: pendingLeaveGroup,
    disconnect_reason: lastDisconnectReason,
    fresh_login_required: Boolean(freshLoginRequired),
    last_event: lastEvent,
    started_at: startedAt,
    updated_at: new Date().toISOString(),
    ...extra,
  };
  if (extra.connected !== undefined) data.connected = extra.connected;
  // Calculados depois do `extra`, com o estado final deste status.
  data.writer = 'node';
  data.pid = process.pid;
  data.boot_at = BOOT_AT;
  data.session_saved = salva;
  data.last_disconnect = ultimoDesligamento || null;
  data.reconnecting = Boolean(!data.connected && reconectandoAgora());
  data.needs_qr = Boolean(!data.connected && !desligando && (
    data.has_qr || !salva || freshLoginRequired ||
    ['qr_expired', 'user_logged_out', 'multidevice_mismatch'].includes(paradoMotivo)));
  try { gravarArquivoAtomicoSync(STATUS_FILE, JSON.stringify(data, null, 2)); } catch (_) {}
  return data;
}
// GET /status com a mesma frase do arquivo (13/10/2026): antes a resposta HTTP
// vinha sem `message` (so o timer de 2,5 s a punha no status.json).
function statusPayload(extra = {}) { return saveStatus({ message: mensagemDeEstado(), ...extra }); }
function digitsOnly(text) { return String(text || '').replace(/\D/g, ''); }
function normalizeBrazilNumber(n) { let d = digitsOnly(n); if (!d) return ''; if (d.length === 10 || d.length === 11) d = '55' + d; return d; }
function foldFancyChars(text) {
  // Converte letras matemáticas/negrito/itálico usadas em nomes de grupos para ASCII.
  // Ex.: 𝙂𝙤𝙢𝙮𝙯 𝙎𝙩𝙤𝙧𝙚 -> Gomyz Store.
  const ranges = [
    [0x1D400, 'A'.charCodeAt(0), 26], [0x1D41A, 'a'.charCodeAt(0), 26],
    [0x1D434, 'A'.charCodeAt(0), 26], [0x1D44E, 'a'.charCodeAt(0), 26],
    [0x1D468, 'A'.charCodeAt(0), 26], [0x1D482, 'a'.charCodeAt(0), 26],
    [0x1D49C, 'A'.charCodeAt(0), 26], [0x1D4B6, 'a'.charCodeAt(0), 26],
    [0x1D4D0, 'A'.charCodeAt(0), 26], [0x1D4EA, 'a'.charCodeAt(0), 26],
    [0x1D504, 'A'.charCodeAt(0), 26], [0x1D51E, 'a'.charCodeAt(0), 26],
    [0x1D538, 'A'.charCodeAt(0), 26], [0x1D552, 'a'.charCodeAt(0), 26],
    [0x1D56C, 'A'.charCodeAt(0), 26], [0x1D586, 'a'.charCodeAt(0), 26],
    [0x1D5A0, 'A'.charCodeAt(0), 26], [0x1D5BA, 'a'.charCodeAt(0), 26],
    [0x1D5D4, 'A'.charCodeAt(0), 26], [0x1D5EE, 'a'.charCodeAt(0), 26],
    [0x1D608, 'A'.charCodeAt(0), 26], [0x1D622, 'a'.charCodeAt(0), 26],
    [0x1D63C, 'A'.charCodeAt(0), 26], [0x1D656, 'a'.charCodeAt(0), 26],
    [0x1D670, 'A'.charCodeAt(0), 26], [0x1D68A, 'a'.charCodeAt(0), 26],
    [0x1D7CE, '0'.charCodeAt(0), 10], [0x1D7D8, '0'.charCodeAt(0), 10],
    [0x1D7E2, '0'.charCodeAt(0), 10], [0x1D7EC, '0'.charCodeAt(0), 10],
    [0x1D7F6, '0'.charCodeAt(0), 10],
  ];
  let out = '';
  for (const ch of String(text || '')) {
    const cp = ch.codePointAt(0);
    let mapped = '';
    for (const [start, base, len] of ranges) {
      if (cp >= start && cp < start + len) { mapped = String.fromCharCode(base + (cp - start)); break; }
    }
    out += mapped || ch;
  }
  return out;
}
function normalizeText(t) { return foldFancyChars(String(t || '')).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(); }
function compactText(t) { return normalizeText(t).replace(/\s+/g, ''); }
function editDistance(a, b) {
  a = String(a || ''); b = String(b || '');
  if (a === b) return 0;
  if (!a) return b.length; if (!b) return a.length;
  const prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  const cur = new Array(b.length + 1);
  for (let i = 1; i <= a.length; i++) {
    cur[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
    }
    for (let j = 0; j <= b.length; j++) prev[j] = cur[j];
  }
  return prev[b.length];
}
function similarity(a, b) {
  a = normalizeText(a); b = normalizeText(b);
  if (!a || !b) return 0;
  const maxLen = Math.max(a.length, b.length);
  return maxLen ? (1 - editDistance(a, b) / maxLen) : 0;
}
// 6.1.5: how a Brazilian name SOUNDS. Voice transcription writes "Kaique"
// for "Kaik", "Tiago" for "Thiago", "Luis" for "Luiz", "Erica" for "Érika"...
// Same sound => same key.
function foneticoPt(palavra) {
  let s = normalizeText(palavra).replace(/\s+/g, '');
  if (!s) return '';
  s = s.replace(/ph/g, 'f').replace(/th/g, 't').replace(/sch/g, 'x').replace(/sh/g, 'x')
       .replace(/ch/g, 'x').replace(/lh/g, 'li').replace(/nh/g, 'ni')
       .replace(/qu(?=[ei])/g, 'k').replace(/gu(?=[ei])/g, 'g').replace(/q/g, 'k')
       .replace(/c(?=[ei])/g, 's').replace(/c/g, 'k').replace(/ck/g, 'k')
       .replace(/y/g, 'i').replace(/w/g, 'v').replace(/z$/g, 's').replace(/ss/g, 's')
       .replace(/(?<![a-z])h/g, '').replace(/h/g, '')
       .replace(/(.)\1+/g, '$1');
  // the unstressed final vowel almost disappears in speech: "kaike" ~ "kaik"
  if (s.length > 3) s = s.replace(/[eo]$/, '');
  return s;
}
function fuzzyNameScore(name, query) {
  const norm = normalizeText(name);
  const target = normalizeText(query);
  const cn = compactText(name);
  const ct = compactText(query);
  if (!target) return 1;
  if (norm === target || cn === ct) return 140;
  if (norm.startsWith(target) || cn.startsWith(ct)) return 120;
  if (norm.includes(target) || cn.includes(ct)) return 105;
  if (target.includes(norm) && norm.length >= 4) return 90;
  // 6.1.5: same SOUND as the full name or as one of its words ("Kaique" -> "Kaik Frederich")
  const fq = target.split(/\s+/).filter(Boolean).map(foneticoPt).filter(x => x.length >= 3);
  const fn = norm.split(/\s+/).filter(Boolean).map(foneticoPt);
  if (fq.length && fq.join('') === fn.join('')) return 130;
  if (fq.length && fq.every(t => fn.includes(t))) return fq.length === fn.length ? 125 : 104;
  const simFull = similarity(norm, target);
  let score = simFull >= 0.72 ? Math.round(75 + simFull * 25) : 0;
  const nameTokens = norm.split(/\s+/).filter(Boolean);
  const targetTokens = target.split(/\s+/).filter(Boolean);
  let tokenScore = 0;
  for (const t of targetTokens) {
    if (t.length < 2) continue;
    let best = 0;
    for (const n of nameTokens) {
      if (n === t) best = Math.max(best, 30);
      else if (n.includes(t) || t.includes(n)) best = Math.max(best, 22);
      else {
        const st = similarity(n, t);
        if (st >= 0.62) best = Math.max(best, Math.round(18 + st * 15));
      }
    }
    tokenScore += best;
  }
  // Número citado na fala (#300, 13 etc.) aumenta confiança.
  const numsQ = target.match(/\d+/g) || [];
  for (const num of numsQ) if (norm.includes(num)) tokenScore += 25;
  score = Math.max(score, Math.min(115, tokenScore));
  return score;
}
function aliasKey(name) { return normalizeText(name); }
function isGroupJid(jid) { return String(jid || '').endsWith('@g.us'); }
function isPersonJid(jid) { return String(jid || '').endsWith('@s.whatsapp.net') || String(jid || '').endsWith('@lid'); }
function linkedPersonJids(jid) {
  const ids = new Set([String(jid || '')].filter(Boolean));
  for (let pass = 0; pass < 2; pass++) {
    for (const [key, c] of Object.entries(contacts || {})) {
      const candidates = [key, c?.id, c?.jid, c?.lid].map(v => String(v || '')).filter(isPersonJid);
      if (candidates.some(v => ids.has(v))) for (const value of candidates) ids.add(value);
    }
  }
  return ids;
}
function filterMessagesByResolvedChat(list, jid) {
  const target = String(jid || '');
  if (!target) return list;
  if (isGroupJid(target)) return list.filter(m => String(m?.jid || '') === target);
  const personIds = linkedPersonJids(target);
  return list.filter(m => {
    if (m?.is_group || isGroupJid(m?.jid)) return false;
    return personIds.has(String(m?.jid || '')) || personIds.has(String(m?.sender_jid || ''));
  });
}
function aliasPriority(source) {
  const priorities = { manual: 100, address_book: 80, private_chat: 50, private_message: 40, private_history: 30, legacy_private: 20, message_or_chat_name: 10 };
  return priorities[String(source || '')] || 0;
}
function saveAlias(name, jidOrPhone) {
  const key = aliasKey(name);
  if (!key) throw new Error('Alias name is empty');
  let jid = String(jidOrPhone || '').trim();
  if (!jid.includes('@')) {
    const num = normalizeBrazilNumber(jid);
    if (!num || num.length < 11) throw new Error('Phone number is invalid');
    jid = `${num}@s.whatsapp.net`;
  }
  aliases[key] = { name: String(name || '').trim(), jid, manual: true, source: 'manual', updated_at: new Date().toISOString() };
  rememberContact(jid, { notify: String(name || '').trim() || jid }, { source: 'manual_alias' });
  saveDb();
  saveStatus({ last_event: 'alias', message: `Contato salvo: ${name} -> ${jid}` });
  return aliases[key];
}

function autoAliasFromName(name, jid, source = 'private_message') {
  try {
    const cleanName = String(name || '').trim();
    const cleanJid = String(jid || '').trim();
    if (!cleanName || !cleanJid || cleanName === 'Você' || cleanName === 'Contato') return;
    if (cleanName.includes('@') || cleanName.length < 2) return;
    // Nome de grupo e nome de participante visto apenas dentro de grupo nÃ£o podem
    // virar automaticamente o destino de uma mensagem privada.
    if (!isPersonJid(cleanJid)) return;
    const key = aliasKey(cleanName);
    if (!key) return;
    const current = aliases[key];
    if (current && current.auto !== true) return;
    if (current && aliasPriority(current.source) > aliasPriority(source)) return;
    if (current && current.jid !== cleanJid && aliasPriority(current.source) === aliasPriority(source)) return;
    aliases[key] = { name: cleanName, jid: cleanJid, auto: true, source, updated_at: new Date().toISOString() };
  } catch (e) { log('autoAliasFromName error', e.message); }
}
function aliasFromMessageHistory(name) {
  const target = aliasKey(name);
  if (!target) return null;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i] || {};
    if (m.is_group || isGroupJid(m.jid)) continue;
    const candidates = [
      { name: m.name, jid: m.sender_jid || m.jid },
      { name: m.chat_name, jid: m.jid },
    ];
    for (const c of candidates) {
      if (!c.name || !c.jid) continue;
      const key = aliasKey(c.name);
      if (key === target || key.includes(target) || target.includes(key)) {
        autoAliasFromName(c.name, c.jid, 'private_history');
        saveDb();
        return aliases[aliasKey(c.name)] || { name: c.name, jid: c.jid, auto: true };
      }
    }
  }
  return null;
}
// 6.1.5: "Você" is the label of OUR sent messages, never a chat/contact name.
// It used to stick to the chat after the first send, and the result said
// "sent to Você" even though the message went to the right person.
function nomeValido(v) { const s = String(v || '').trim(); return s && s !== 'Você' ? s : ''; }
function displayName(obj, fallback = '') {
  for (const v of [obj?.name, obj?.notify, obj?.verifiedName, obj?.subject, obj?.shortName, obj?.pushName]) {
    const s = nomeValido(v);
    if (s) return s;
  }
  return fallback;
}
// 6.1.5: who the message went to, in a form a person can read: the name,
// or the formatted number (+55 14 99149-5373) — never "Você" or "...@s.whatsapp.net".
function nomeDoDestino(jid, pedido = '') {
  const nome = friendlyNameForJid(jid);
  if (nomeValido(nome) && !String(nome).includes('@')) return nome;
  const d = String(jid || '').split('@')[0].replace(/\D/g, '');
  if (String(jid || '').endsWith('@s.whatsapp.net') && d.startsWith('55') && d.length >= 12) {
    const ddd = d.slice(2, 4), resto = d.slice(4);
    return `+55 ${ddd} ${resto.slice(0, resto.length - 4)}-${resto.slice(-4)}`;
  }
  return String(pedido || '').trim() || d || 'o contato';
}
function limparNomesVoce() {
  let n = 0;
  for (const mapa of [chats, contacts]) {
    for (const [jid, c] of Object.entries(mapa || {})) {
      for (const campo of ['name', 'notify', 'pushName']) {
        if (c && String(c[campo] || '').trim() === 'Você') { delete c[campo]; n++; }
      }
    }
  }
  for (const m of (messages || [])) {
    if (m && !m.is_group && String(m.chat_name || '').trim() === 'Você') { m.chat_name = m.jid; n++; }
  }
  if (n) log('cleaned "Você" names', n);
  return n;
}
function friendlyNameForJid(jid) { return displayName(contacts[jid] || chats[jid] || groups[jid] || {}, jid); }
function shortJid(jid) {
  const raw = String(jid || '').split('@')[0] || '';
  if (!raw) return '';
  if (raw.length <= 10) return raw;
  return raw.slice(-8);
}
function _looksLikeRawParticipantName(name, senderJid = '') {
  const raw = String(name || '').trim();
  if (!raw) return true;
  if (raw === senderJid) return true;
  if (raw.includes('@s.whatsapp.net') || raw.includes('@lid') || raw.includes('@g.us')) return true;
  if (/^participante\s+\d{3,}$/i.test(raw)) return true;
  if (/^\d{8,}$/.test(raw.replace(/\D/g, ''))) return true;
  return false;
}
function _senderNameFromKnownMaps(senderJid) {
  const contact = contacts[senderJid] || chats[senderJid] || aliases[aliasKey(senderJid)] || {};
  const vals = [contact.name, contact.notify, contact.verifiedName, contact.shortName, contact.pushName, friendlyNameForJid(senderJid)];
  for (const v of vals) {
    const name = String(v || '').trim();
    if (!_looksLikeRawParticipantName(name, senderJid)) return name;
  }
  return '';
}
function chooseGroupSenderName(msg, senderJid, chatName) {
  const groupNorm = normalizeText(chatName || '');
  const candidates = [];
  const savedName = contacts[senderJid]?.name_source === 'address_book' ? contacts[senderJid]?.name : '';
  if (savedName) candidates.push(savedName);
  if (msg?.pushName) candidates.push(msg.pushName);
  const known = _senderNameFromKnownMaps(senderJid);
  if (known) candidates.push(known);
  for (const c of candidates) {
    const name = String(c || '').trim();
    if (!name) continue;
    const norm = normalizeText(name);
    if (!norm || norm === groupNorm) continue;
    if (name.endsWith('@g.us')) continue;
    if (_looksLikeRawParticipantName(name, senderJid)) continue;
    return name;
  }
  // Não inventar nome nem falar código/ID. Se o WhatsApp não liberar o nome do participante,
  // o Jarvis fala apenas "participante do grupo".
  return 'participante do grupo';
}
function rememberContact(jid, data = {}, options = {}) {
  if (!jid || jid === 'status@broadcast' || isGroupJid(jid)) return;
  const source = String(options.source || 'unknown');
  const incoming = { ...(data || {}) };
  const visibleName = String(incoming.name || '').trim();
  if (source === 'message' || source === 'manual_alias') {
    // pushName/notify pertence ao perfil do WhatsApp. Nunca deve substituir o
    // nome que chegou da agenda do usuÃ¡rio.
    delete incoming.name;
  }
  const merged = { ...(contacts[jid] || {}), ...incoming, id: jid, updated_at: new Date().toISOString() };
  if (source === 'address_book' && visibleName) {
    merged.name = visibleName;
    merged.name_source = 'address_book';
    autoAliasFromName(visibleName, jid, 'address_book');
    if (chats[jid] && !isGroupJid(jid)) chats[jid] = { ...chats[jid], name: visibleName, id: jid, updated_at: new Date().toISOString() };
    for (const item of messages) {
      if (!item?.from_me && item?.sender_jid === jid) item.name = visibleName;
      if (!item?.is_group && item?.jid === jid) item.chat_name = visibleName;
    }
    for (const queue of [alertQueue, agentQueue]) {
      for (const item of queue) {
        if (item?.sender_jid === jid) item.name = visibleName;
        if (!item?.is_group && item?.jid === jid) item.chat_name = visibleName;
      }
    }
  }
  contacts[jid] = merged;
}
function rememberChat(jid, data = {}) { if (!jid || jid === 'status@broadcast') return; chats[jid] = { ...(chats[jid] || {}), ...data, id: jid, updated_at: new Date().toISOString() }; }
function isUsableGroupName(name, jid = '') {
  const clean = String(name || '').trim();
  if (!clean || clean === String(jid || '').trim() || isGroupJid(clean)) return false;
  return normalizeText(clean) !== 'participante do grupo';
}
function rememberGroup(jid, data = {}) {
  if (!jid || !jid.endsWith('@g.us')) return;
  const incoming = { ...(data || {}) };
  const incomingName = incoming.subject || incoming.name || '';
  if (!isUsableGroupName(incomingName, jid)) {
    delete incoming.name;
    delete incoming.subject;
  }
  const merged = { ...(groups[jid] || {}), ...incoming, id: jid, updated_at: new Date().toISOString() };
  const resolvedName = merged.subject || merged.name || '';
  groups[jid] = merged;
  rememberChat(jid, isUsableGroupName(resolvedName, jid) ? { ...incoming, name: resolvedName, subject: resolvedName } : incoming);
  if (isUsableGroupName(resolvedName, jid)) {
    for (const item of messages) if (item?.jid === jid) item.chat_name = resolvedName;
    for (const queue of [alertQueue, agentQueue]) for (const item of queue) if (item?.jid === jid) item.chat_name = resolvedName;
  }
}
function unwrapMessage(message) {
  let m = message || {};
  for (let i = 0; i < 8; i++) {
    if (m.ephemeralMessage?.message) { m = m.ephemeralMessage.message; continue; }
    if (m.viewOnceMessage?.message) { m = m.viewOnceMessage.message; continue; }
    if (m.viewOnceMessageV2?.message) { m = m.viewOnceMessageV2.message; continue; }
    if (m.viewOnceMessageV2Extension?.message) { m = m.viewOnceMessageV2Extension.message; continue; }
    if (m.documentWithCaptionMessage?.message) { m = m.documentWithCaptionMessage.message; continue; }
    if (m.editedMessage?.message) { m = m.editedMessage.message; continue; }
    break;
  }
  return m || {};
}

function textCandidate(v) {
  if (v === undefined || v === null) return '';
  let s = String(v).replace(/\s+/g, ' ').trim();
  if (!s) return '';
  if (/^[A-Za-z0-9+/=]{80,}$/.test(s)) return '';
  if (/^[0-9]{8,}$/.test(s)) return '';
  if (/^https?:\/\//i.test(s) && s.length > 80) return '';
  if (/^(true|false|null|undefined)$/i.test(s)) return '';
  return s;
}
function collectTextDeep(obj, depth = 0, out = []) {
  if (!obj || depth > 8 || out.length > 24) return out;
  if (typeof obj === 'string' || typeof obj === 'number') {
    const c = textCandidate(obj);
    if (c) out.push(c);
    return out;
  }
  if (Array.isArray(obj)) {
    for (const x of obj) collectTextDeep(x, depth + 1, out);
    return out;
  }
  if (typeof obj !== 'object') return out;
  const preferred = [
    'conversation','text','caption','title','subtitle','description','selectedDisplayText',
    'selectedRowId','displayText','buttonText','name','body','footer','label','contentText',
    'matchedText','canonicalUrl','fileName','mimetype','paramsJson','buttonParamsJson'
  ];
  for (const key of preferred) {
    if (!(key in obj)) continue;
    let val = obj[key];
    if ((key === 'paramsJson' || key === 'buttonParamsJson') && typeof val === 'string') {
      try { val = JSON.parse(val); } catch (_) {}
    }
    if (typeof val === 'object') collectTextDeep(val, depth + 1, out);
    else {
      const c = textCandidate(val);
      if (c) out.push(c);
    }
  }
  for (const key of Object.keys(obj)) {
    if (preferred.includes(key)) continue;
    if (/messageContextInfo|jpegThumbnail|thumbnail|mediaKey|directPath|urlTrackingMap/i.test(key)) continue;
    if (/Message$|Reply|Response|interactive|nativeFlow|button|list|poll|header|body|footer|context/i.test(key)) {
      collectTextDeep(obj[key], depth + 1, out);
    }
  }
  return out;
}
function uniqueJoin(parts, textoDireto = false) {
  const seen = new Set();
  const out = [];
  for (const p of parts) {
    // TEXTO DIGITADO PELA PESSOA VALE COMO VEIO (23/09/2026). O filtro de
    // `textCandidate` existe para o lixo das mensagens interativas (ids,
    // base64, link de rastreio). Aplicado ao texto de verdade ele jogava fora
    // mensagem que e so um LINK comprido — e o JARVIS lia "[extendedTextMessage]"
    // em vez do link que o Diego mandou.
    const c = textoDireto ? String(p == null ? '' : p).replace(/\s+/g, ' ').trim() : textCandidate(p);
    if (!c) continue;
    const k = normalizeText(c);
    if (!k || seen.has(k)) continue;
    if (/^(interactive message|native flow|unknown|protocol message)$/i.test(c)) continue;
    seen.add(k);
    out.push(c);
  }
  return out.join(' | ').slice(0, 900);
}
function getMessageText(msg) {
  const m = unwrapMessage(msg.message || {});
  if (m.deviceSentMessage?.message) return getMessageText({ message: m.deviceSentMessage.message });
  if (m.protocolMessage?.editedMessage) return getMessageText({ message: m.protocolMessage.editedMessage });
  const direct = uniqueJoin([
    m.conversation,
    m.extendedTextMessage?.text,
    m.imageMessage?.caption,
    m.videoMessage?.caption,
    m.documentMessage?.caption,
    m.buttonsResponseMessage?.selectedDisplayText,
    m.listResponseMessage?.singleSelectReply?.selectedRowId,
    m.listResponseMessage?.title,
    m.templateButtonReplyMessage?.selectedDisplayText,
    m.pollCreationMessage?.name,
    m.contactMessage?.displayName,
    m.locationMessage?.name,
    m.liveLocationMessage?.caption,
    m.reactionMessage?.text,
  ], true);
  if (direct) return direct;
  const deep = uniqueJoin([
    ...collectTextDeep(m.interactiveMessage || {}),
    ...collectTextDeep(m.interactiveResponseMessage || {}),
    ...collectTextDeep(m.buttonsMessage || {}),
    ...collectTextDeep(m.templateMessage || {}),
    ...collectTextDeep(m.listMessage || {}),
    ...collectTextDeep(m.productMessage || {}),
    ...collectTextDeep(m.orderMessage || {}),
    ...collectTextDeep(m.pollCreationMessage || {}),
  ]);
  if (deep) return deep;
  return '';
}
function messageType(msg) {
  const m = unwrapMessage(msg.message || {});
  if (m.deviceSentMessage?.message) return messageType({ message: m.deviceSentMessage.message });
  if (m.protocolMessage?.editedMessage) return messageType({ message: m.protocolMessage.editedMessage });
  return Object.keys(m).find(k => k !== 'messageContextInfo') || 'unknown';
}
function describeMessage(msg) {
  const text = getMessageText(msg);
  if (text) return text;
  const m = unwrapMessage(msg.message || {});
  if (m.deviceSentMessage?.message) return describeMessage({ message: m.deviceSentMessage.message });
  const t = messageType(msg);
  const map = {
    imageMessage: '[imagem sem legenda]', videoMessage: '[vídeo sem legenda]', audioMessage: '[áudio/voz]',
    documentMessage: '[documento sem legenda]', stickerMessage: '[figurinha]', contactMessage: '[contato]',
    contactsArrayMessage: '[contatos]', locationMessage: '[localização]', liveLocationMessage: '[localização ao vivo]',
    reactionMessage: '[reação]', pollCreationMessage: '[enquete]', interactiveMessage: '[mensagem interativa sem texto visível]',
    secretEncryptedMessage: '[mensagem criptografada sem texto liberado pelo WhatsApp]', interactiveResponseMessage: '[resposta interativa sem texto visível]', buttonsResponseMessage: '[resposta de botão sem texto visível]',
    listResponseMessage: '[resposta de lista sem texto visível]', protocolMessage: '[mensagem de sistema do WhatsApp]',
    senderKeyDistributionMessage: '[sincronização do WhatsApp]', messageContextInfo: '[contexto do WhatsApp]'
  };
  return map[t] || `[${t || 'mensagem sem texto visível'}]`;
}

function mediaInfoFromMessage(msg) {
  const m = unwrapMessage(msg.message || {});
  const candidates = [
    ['audio', m.audioMessage], ['image', m.imageMessage], ['video', m.videoMessage], ['document', m.documentMessage], ['sticker', m.stickerMessage]
  ];
  for (const [kind, media] of candidates) {
    if (media) {
      const mimetype = media.mimetype || (kind === 'audio' ? 'audio/ogg' : 'application/octet-stream');
      return { kind, media, mimetype, fileName: media.fileName || '' };
    }
  }
  return null;
}
function extFromMime(mimetype, kind) {
  const mt = String(mimetype || '').toLowerCase();
  if (mt.includes('ogg')) return '.ogg';
  if (mt.includes('opus')) return '.ogg';
  if (mt.includes('mpeg') || mt.includes('mp3')) return '.mp3';
  if (mt.includes('wav')) return '.wav';
  if (mt.includes('mp4')) return kind === 'audio' ? '.m4a' : '.mp4';
  if (mt.includes('jpeg') || mt.includes('jpg')) return '.jpg';
  if (mt.includes('png')) return '.png';
  if (mt.includes('webp')) return '.webp';
  if (mt.includes('pdf')) return '.pdf';
  return kind === 'audio' ? '.ogg' : '.bin';
}
async function streamToBufferSafe(stream, ms = 20000) {
  return await withTimeout((async () => {
    const chunks = [];
    for await (const chunk of stream) chunks.push(chunk);
    return Buffer.concat(chunks);
  })(), ms, 'download media stream');
}
async function saveIncomingMedia(m, item) {
  const key = String(item?.id || '') + '|' + String(item?.jid || '');
  if (key && mediaDownloadActive.has(key)) return;
  if (key) mediaDownloadActive.add(key);
  try {
    if (!downloadContentFromMessage) return;
    const info = mediaInfoFromMessage(m);
    if (!info || !info.media) return;
    // MIDIA SEM CHAVE (13/10/2026): sem mediaKey nao ha como baixar. Antes a
    // ponte tentava de novo a cada reconexao ("Cannot derive from empty media
    // key" logo depois de CADA 'Connected.'). Marca e nao tenta mais.
    const chave = info.media.mediaKey;
    if (!chave || (typeof chave.length === 'number' && chave.length === 0)) {
      marcarMidiaSemChave(item);
      return;
    }

    item.media_download_status = 'downloading';
    item.media_kind = info.kind;
    item.mimetype = info.mimetype;
    const idxPending = messages.findIndex(x => x.id === item.id && x.jid === item.jid);
    if (idxPending >= 0) messages[idxPending] = { ...messages[idxPending], ...item };
    saveDb();

    const stream = await withTimeout(downloadContentFromMessage(info.media, info.kind), 12000, 'start media download');
    const buffer = await streamToBufferSafe(stream, info.kind === 'audio' ? 25000 : 30000);
    if (!buffer || buffer.length < 10) throw new Error('media buffer empty');
    const safeId = String(item.id || Date.now()).replace(/[^a-zA-Z0-9_-]/g, '_');
    const ext = extFromMime(info.mimetype, info.kind);
    const filePath = path.join(MEDIA_DIR, `${Date.now()}_${info.kind}_${safeId}${ext}`);
    fs.writeFileSync(filePath, buffer);
    item.media_path = filePath;
    item.mimetype = info.mimetype;
    item.media_kind = info.kind;
    item.media_size = buffer.length;
    item.media_download_status = 'saved';
    item.media_saved_at = new Date().toISOString();
    if (info.fileName) item.file_name = info.fileName;
    const idx = messages.findIndex(x => x.id === item.id && x.jid === item.jid);
    if (idx >= 0) messages[idx] = { ...messages[idx], ...item };
    saveDb();
    saveStatus({ last_event: 'media_saved', message: `Mídia recebida salva: ${info.kind}` });
    // Se for áudio ou imagem recebida, o agente só entra agora na fila, já com arquivo disponível
    // para transcrição/análise. Para áudio, também refazemos o alerta com mídia já salva.
    if ((info.kind === 'audio' || info.kind === 'image') && !item.from_me) {
      if (info.kind === 'audio') {
        try { queueAlert(item); } catch (_) {}
      }
      try { queueAgentMessage(item); } catch (_) {}
    }
    log('media saved', info.kind, filePath, buffer.length);
  } catch (e) {
    if (/empty media key/i.test(String(e?.message || e))) {
      marcarMidiaSemChave(item);
      log('saveIncomingMedia: midia sem chave, nao tento de novo', item?.id || '');
      return;
    }
    try {
      const idx = messages.findIndex(x => x.id === item.id && x.jid === item.jid);
      if (idx >= 0) {
        messages[idx].media_download_status = 'failed';
        messages[idx].media_error = String(e.message || e);
        saveDb();
      }
    } catch (_) {}
    log('saveIncomingMedia error', e?.stack || e);
  } finally {
    if (key) mediaDownloadActive.delete(key);
  }
}
function marcarMidiaSemChave(item) {
  try {
    if (item) item.media_download_status = 'sem_chave';
    const idx = messages.findIndex(x => x.id === item?.id && x.jid === item?.jid);
    if (idx >= 0) {
      messages[idx].media_download_status = 'sem_chave';
      messages[idx].media_error = 'empty media key';
      saveDb();
    }
  } catch (_) {}
}

function betterMessage(newItem, oldItem) {
  if (!oldItem) return newItem;
  const oldText = String(oldItem.text || '');
  const newText = String(newItem.text || '');
  const oldBad = /^\[(secretEncryptedMessage|protocolMessage|unknown|senderKeyDistributionMessage|messageContextInfo|mensagem criptografada|mensagem de sistema|sincronização|contexto)/i.test(oldText) || ['secretEncryptedMessage','protocolMessage','unknown'].includes(String(oldItem.type || ''));
  const newGood = isMeaningfulMessageItem(newItem) || newText.length > oldText.length || newItem.media_path;
  if (oldBad && newGood) return { ...oldItem, ...newItem };
  if (newItem.media_path && !oldItem.media_path) return { ...oldItem, ...newItem };
  if (newText && newText.length > oldText.length && !/^\[/.test(newText)) return { ...oldItem, ...newItem };
  return { ...oldItem, updated_at: new Date().toISOString() };
}

function isMeaningfulMessageItem(item) {
  if (!item) return false;
  const text = String(item.text || '').trim();
  const type = String(item.type || '');
  if (!text) return false;
  const badTypes = new Set(['protocolMessage', 'senderKeyDistributionMessage', 'messageContextInfo', 'unknown', 'secretEncryptedMessage']);
  if (badTypes.has(type)) return false;
  if (/^\[(protocolMessage|unknown|senderKeyDistributionMessage|messageContextInfo|secretEncryptedMessage)\]$/i.test(text)) return false;
  if (/^\[(mensagem de sistema do WhatsApp|sincronização do WhatsApp|contexto do WhatsApp|mensagem interativa sem texto visível|resposta interativa sem texto visível)\]$/i.test(text)) return false;
  return true;
}

function matchWatchContact(item, watch) {
  const target = normalizeText(watch || '');
  if (!target) return false;
  const vals = [item.name, item.chat_name, item.sender_jid, item.jid].filter(Boolean).map(v => normalizeText(v));
  if (vals.some(v => v === target || v.includes(target) || target.includes(v))) return true;
  const ali = aliases[target];
  if (ali && vals.some(v => v === normalizeText(ali.name) || v === normalizeText(ali.jid))) return true;
  return false;
}
function watchListMatches(item) {
  const list = Array.isArray(watchConfig.contacts) ? watchConfig.contacts : [];
  return list.some(w => matchWatchContact(item, w.name || w.jid || w.query || w));
}
function isAudioMessageItem(item) {
  const text = String(item?.text || '').toLowerCase();
  const type = String(item?.type || '').toLowerCase();
  const kind = String(item?.media_kind || '').toLowerCase();
  return kind === 'audio' || type.includes('audio') || text.includes('[áudio') || text.includes('[audio') || text.includes('audio/voz');
}
function isImageMessageItem(item) {
  const text = String(item?.text || '').toLowerCase();
  const type = String(item?.type || '').toLowerCase();
  const kind = String(item?.media_kind || '').toLowerCase();
  return kind === 'image' || type.includes('image') || text.includes('[imagem');
}
function shouldAlertMessage(item) {
  if (!watchConfig || !watchConfig.enabled) return false;
  if (!item || item.from_me) return false;
  if (!isMeaningfulMessageItem(item)) return false;

  // Áudio recebido precisa primeiro ser salvo. Assim o Jarvis pode falar o conteúdo transcrito direto
  // e não apenas avisar "[áudio recebido]" antes do arquivo ficar disponível.
  // 'sem_chave' (13/10/2026) e falha definitiva, como 'failed'.
  if (isAudioMessageItem(item) && !item.media_path && !['failed', 'sem_chave'].includes(String(item.media_download_status || '').toLowerCase())) return false;

  const isGroup = Boolean(item.is_group || String(item.jid || '').endsWith('@g.us'));
  const idKey = `${item.jid || ''}:${item.sender_jid || ''}:${item.id || item.timestamp || ''}`;
  if (alertSeen[idKey]) return false;

  const mode = String(watchConfig.mode || '').toLowerCase();
  if (['any', 'all', 'todos', 'qualquer'].includes(mode)) return true;
  if (['private', 'privado', 'privados', 'contacts_only', 'contatos_privados'].includes(mode)) return !isGroup;
  if (['groups', 'group_only', 'grupos', 'somente_grupos'].includes(mode)) return isGroup;
  if (['contact', 'contacts', 'contato', 'specific_contact'].includes(mode)) return !isGroup && watchListMatches(item);
  if (['group', 'specific_group', 'grupo'].includes(mode)) return isGroup && watchListMatches(item);
  if (mode === 'contacts_any') return watchListMatches(item);
  return false;
}
function queueAlert(item) {
  try {
    if (!shouldAlertMessage(item)) return;
    const idKey = `${item.jid || ''}:${item.sender_jid || ''}:${item.id || item.timestamp || ''}`;
    alertSeen[idKey] = true;
    const isGroup = Boolean(item.is_group || String(item.jid || '').endsWith('@g.us'));
    let alertName = item.name || item.sender_name || item.sender_jid || 'contato';
    const alertChatName = item.chat_name || (isGroup ? friendlyNameForJid(item.jid) : (item.name || item.jid || ''));
    if (isGroup && (normalizeText(alertName) === normalizeText(alertChatName) || _looksLikeRawParticipantName(alertName, item.sender_jid))) {
      alertName = 'participante do grupo';
    }
    const alert = {
      id: idKey,
      name: alertName,
      chat_name: alertChatName,
      jid: item.jid,
      sender_jid: item.sender_jid,
      text: String(item.text || '').slice(0, 500),
      is_group: isGroup,
      chat_type: isGroup ? 'group' : 'private',
      type: item.type || 'message',
      media_kind: item.media_kind || '',
      media_path: item.media_path || '',
      media_download_status: item.media_download_status || '',
      timestamp: item.timestamp || Math.floor(Date.now()/1000),
      created_at: new Date().toISOString(),
    };
    alertQueue.push(alert);
    if (alertQueue.length > 200) alertQueue = alertQueue.slice(-200);
    saveDb();
    saveStatus({ last_event:'whatsapp_alert', message:`Alerta WhatsApp de ${alert.name}.` });
  } catch(e) { log('queueAlert error', e.message); }
}

function queueAgentMessage(item) {
  try {
    if (!item || item.from_me) return;
    if (!isMeaningfulMessageItem(item)) return;
    // For audio/image, wait until media has been saved so the Python side can transcribe/analyze before replying.
    if ((isAudioMessageItem(item) || isImageMessageItem(item)) && !item.media_path && !['failed', 'sem_chave'].includes(String(item.media_download_status || '').toLowerCase())) return;
    const idKey = `${item.jid || ''}:${item.sender_jid || ''}:${item.id || item.timestamp || ''}`;
    if (agentSeen[idKey]) return;
    agentSeen[idKey] = true;
    const isGroup = Boolean(item.is_group || String(item.jid || '').endsWith('@g.us'));
    let agentName = item.name || item.sender_name || item.sender_jid || 'contato';
    const agentChatName = item.chat_name || (isGroup ? friendlyNameForJid(item.jid) : (item.name || item.jid || ''));
    if (isGroup && (normalizeText(agentName) === normalizeText(agentChatName) || _looksLikeRawParticipantName(agentName, item.sender_jid))) {
      agentName = 'participante do grupo';
    }
    const ev = {
      id: idKey,
      name: agentName,
      chat_name: agentChatName,
      jid: item.jid,
      sender_jid: item.sender_jid,
      text: String(item.text || '').slice(0, 1200),
      is_group: isGroup,
      chat_type: isGroup ? 'group' : 'private',
      type: item.type || 'message',
      media_kind: item.media_kind || '',
      media_path: item.media_path || '',
      timestamp: item.timestamp || Math.floor(Date.now()/1000),
      created_at: new Date().toISOString(),
    };
    agentQueue.push(ev);
    if (agentQueue.length > 500) agentQueue = agentQueue.slice(-500);
    saveDb();
  } catch(e) { log('queueAgentMessage error', e.message); }
}

function setWatchAny() {
  watchConfig = { enabled: true, mode: 'any', contacts: [], include_groups: true, target_type: 'all', updated_at: new Date().toISOString() };
  alertQueue = [];
  saveDb();
  return 'Alerta ativado: vou avisar quando qualquer pessoa, contato privado ou grupo enviar mensagem no WhatsApp.';
}
function setWatchPrivateOnly() {
  watchConfig = { enabled: true, mode: 'private', contacts: [], include_groups: false, target_type: 'private', updated_at: new Date().toISOString() };
  alertQueue = [];
  saveDb();
  return 'Alerta ativado: vou avisar somente mensagens privadas de contatos. Mensagens de grupos serão ignoradas.';
}
function setWatchGroupsOnly() {
  watchConfig = { enabled: true, mode: 'groups', contacts: [], include_groups: true, target_type: 'groups', updated_at: new Date().toISOString() };
  alertQueue = [];
  saveDb();
  return 'Alerta ativado: vou avisar somente mensagens de grupos. Mensagens privadas serão ignoradas.';
}
function setWatchSpecific(rawName, wantGroup=false) {
  const raw = String(rawName || '').trim();
  if (!raw) throw new Error(wantGroup ? 'Informe o nome do grupo para ativar o alerta.' : 'Informe o nome do contato para ativar o alerta.');
  let found = searchContacts(raw, 8).find(x => wantGroup ? String(x.jid || '').endsWith('@g.us') : !String(x.jid || '').endsWith('@g.us')) || searchContacts(raw, 1)[0];
  const entry = found ? { name: found.name, jid: found.jid || '', query: raw } : { name: raw, jid: '', query: raw };
  watchConfig = { enabled: true, mode: wantGroup ? 'group' : 'contact', contacts: [entry], include_groups: true, target_type: wantGroup ? 'specific_group' : 'specific_contact', updated_at: new Date().toISOString() };
  alertQueue = [];
  saveDb();
  return wantGroup
    ? `Alerta ativado: vou avisar somente quando chegar mensagem no grupo ${entry.name || raw}.`
    : `Alerta ativado: vou avisar somente quando ${entry.name || raw} enviar mensagem no WhatsApp.`;
}
function setWatchContact(contactName) { return setWatchSpecific(contactName, false); }
function setWatchGroup(groupName) { return setWatchSpecific(groupName, true); }
function stopWatch() {
  watchConfig = { enabled: false, mode: 'off', contacts: [], include_groups: true, target_type: 'off', updated_at: new Date().toISOString() };
  alertQueue = [];
  saveDb();
  return 'Alertas de mensagens do WhatsApp desativados.';
}

function rememberMessage(m) {
  try {
    const jid = m.key?.remoteJid;
    if (!jid || jid === 'status@broadcast') return;
    // Sem conteudo (nao decifrada, troca de chave, contexto): nao e mensagem
    // que alguem possa ler, e em rajada ela expulsava as de verdade do banco.
    // Se a mesma mensagem chegar DEPOIS decifrada, ela entra normalmente.
    const tipoRecebido = messageType(m);
    if (REGISTRO_VAZIO.has(tipoRecebido)) return;
    if (tipoRecebido === 'protocolMessage' && !unwrapMessage(m.message || {}).protocolMessage?.editedMessage) return;
    const fromMe = Boolean(m.key?.fromMe);
    const senderJid = fromMe ? (sock?.user?.id || 'me') : (m.key?.participant || jid);
    const isGroup = String(jid || '').endsWith('@g.us');
    const currentChatName = friendlyNameForJid(jid);
    const rawChatName = currentChatName && !String(currentChatName).includes('@') ? currentChatName : jid;
    // 6.1.5: a message WE sent carries our pushName ("Você"): it never names the chat.
    const chatName = isGroup ? rawChatName : (rawChatName && !String(rawChatName).includes('@') ? rawChatName : ((fromMe ? '' : nomeValido(m.pushName)) || jid));
    const savedContactName = contacts[senderJid]?.name_source === 'address_book' ? contacts[senderJid]?.name : '';
    const personName = fromMe ? 'Você' : (isGroup ? chooseGroupSenderName(m, senderJid, chatName) : (savedContactName || m.pushName || friendlyNameForJid(senderJid) || chatName || senderJid));
    const item = { id: m.key?.id, jid, sender_jid: senderJid, from_me: fromMe, name: personName, chat_name: chatName, is_group: isGroup, chat_type: isGroup ? 'group' : 'private', text: describeMessage(m), type: messageType(m), timestamp: Number(m.messageTimestamp || Math.floor(Date.now()/1000)), key: m.key };
    // LID (13/10/2026): o WhatsApp passou as conversas para @lid e manda o
    // numero (PN) ao lado, em senderPn/participantPn. Guarda o par e liga o
    // contato PN ao LID, para "ultimas mensagens de Fulano" achar a conversa.
    const jidAlt = String(m.key?.senderPn || m.key?.participantPn || '');
    if (jidAlt) item.jid_alt = jidAlt;
    if (!fromMe && jidAlt) ligarPnLid(jidAlt, senderJid);
    if (item.id) {
      const idx = messages.findIndex(x => x.id === item.id && x.jid === item.jid);
      if (idx >= 0) {
        messages[idx] = betterMessage(item, messages[idx]);
        if (jidAlt && !messages[idx].jid_alt) messages[idx].jid_alt = jidAlt;
        // Midia sem chave (13/10/2026) nao e baixada de novo a cada reconexao.
        if (mediaInfoFromMessage(m) && !messages[idx].media_path && messages[idx].media_download_status !== 'sem_chave') saveIncomingMedia(m, messages[idx]).catch(()=>{});
        saveDb();
        saveStatus({ last_event: 'message_update', message: 'Mensagem do WhatsApp atualizada.' });
        if (!messages[idx].from_me) { queueAlert(messages[idx]); queueAgentMessage(messages[idx]); }
        return;
      }
    }
    messages.push(item);
    if (mediaInfoFromMessage(m)) saveIncomingMedia(m, item).catch(()=>{});
    if (jid.endsWith('@g.us')) rememberGroup(jid, { subject: chatName, name: chatName });
    else if (fromMe) { if (nomeValido(chatName) && !String(chatName).includes('@')) rememberChat(jid, { name: chatName }); else rememberChat(jid, {}); }
    else rememberChat(jid, { name: chatName, notify: personName, pushName: personName });
    if (!fromMe) rememberContact(senderJid, { notify: personName, pushName: personName }, { source: 'message' });
    if (!fromMe && jidAlt) ligarPnLid(jidAlt, senderJid);
    // Aprender nome automaticamente apenas em conversa privada. Participantes
    // vistos dentro de grupos nÃ£o entram como destinatÃ¡rios automÃ¡ticos.
    if (!fromMe && !isGroup) autoAliasFromName(personName, senderJid, 'private_message');
    if (!isGroup) autoAliasFromName(chatName, jid, 'private_chat');
    saveDb();
    saveStatus({ last_event: 'message', message: fromMe ? 'Mensagem enviada registrada.' : (isGroup ? `Nova mensagem no grupo ${chatName} de ${personName}.` : `Nova mensagem privada de ${personName}.`) });
    if (!fromMe) { queueAlert(item); queueAgentMessage(item); }
  } catch (e) { log('rememberMessage error', e.message); }
}
// Liga PN <-> LID so quando os dois contatos ja existem no banco (o caso
// trivial): contacts[lid].jid = pn e contacts[pn].lid = lid. Quem le e o
// linkedPersonJids, que ja conhece esses dois campos.
function ligarPnLid(pn, outro) {
  try {
    pn = String(pn || ''); outro = String(outro || '');
    if (!pn.endsWith('@s.whatsapp.net') || !outro.endsWith('@lid')) return;
    if (contacts[outro] && contacts[outro].jid !== pn) contacts[outro] = { ...contacts[outro], jid: pn };
    if (contacts[pn] && contacts[pn].lid !== outro) contacts[pn] = { ...contacts[pn], lid: outro };
  } catch (_) {}
}
// ENVIO RECUSADO DEPOIS DO "OK" (13/10/2026). O sendMessage ja tinha voltado
// e o servidor recusou depois (ack com erro, ex.: 463 do LID). Fica no log e
// marcado na mensagem; antes isso se perdia em silencio.
function verificarEnvioRecusado(u) {
  try {
    const key = u?.key || {};
    const up = u?.update || {};
    if (!key.fromMe || !key.id) return;
    const stub = Array.isArray(up.messageStubParameters) ? up.messageStubParameters.map(String) : [];
    const statusErro = (WAMessageStatus && WAMessageStatus.ERROR !== undefined) ? WAMessageStatus.ERROR : 0;
    const comErro = up.status === statusErro || stub.includes('463');
    if (!comErro) return;
    const idx = messages.findIndex(x => x?.id === key.id && x?.from_me);
    if (!enviadasCache.has(key.id) && idx < 0) return;
    log('send rejected', key.id, `status=${up.status === undefined ? '' : up.status} stub=${stub.join(',')}`, String(key.remoteJid || ''));
    if (idx >= 0) {
      messages[idx].send_error = stub.join(',') || 'ERROR';
      messages[idx].send_error_at = new Date().toISOString();
      saveDb();
    }
  } catch (e) { log('verificarEnvioRecusado error', e.message); }
}
function searchContacts(q, limit = 10) {
  const target = normalizeText(q);
  const all = [];
  const privateJids = new Set();
  const groupParticipantJids = new Set();
  for (const m of (messages || [])) {
    const messageJid = String(m?.jid || '');
    const senderJid = String(m?.sender_jid || '');
    if (m?.is_group || isGroupJid(messageJid)) {
      if (isPersonJid(senderJid)) groupParticipantJids.add(senderJid);
    } else {
      if (isPersonJid(messageJid)) privateJids.add(messageJid);
      if (isPersonJid(senderJid)) privateJids.add(senderJid);
    }
  }
  const isGroupOnlyIdentity = (jid) => groupParticipantJids.has(String(jid || '')) && !privateJids.has(String(jid || ''));
  const textScore = (name) => {
    const normName = normalizeText(name);
    const normAll = normalizeText(String(name || ''));
    if (!target) return 1;
    if (normName === target) return 140;
    if (normName.startsWith(target)) return 120;
    if (normName.includes(target)) return 105;
    if (target.includes(normName) && normName.length >= 3) return 80;
    return normAll.includes(target) ? 65 : 0;
  };
  const add = (jid, name, priority, extra = {}) => {
    if (!jid || !name || jid === 'status@broadcast') return;
    const matched = textScore(name);
    if (matched > 0) all.push({ jid, name, score: matched + priority, is_group: isGroupJid(jid), ...extra });
  };
  for (const a of Object.values(aliases || {})) {
    const name = a.name || a.jid;
    const isManual = a.auto !== true;
    if (!isManual && !isGroupJid(a.jid) && isGroupOnlyIdentity(a.jid) && a.source !== 'address_book') continue;
    const priority = isManual ? 220 : (a.source === 'address_book' ? 170 : (isGroupJid(a.jid) ? 0 : 35));
    add(a.jid, name, priority, { alias: true, source: a.source || (isManual ? 'manual' : 'legacy_auto') });
  }
  // HistÃ³rico privado ajuda a localizar nÃ£o salvos; nomes vistos somente em
  // grupos ficam de fora para nÃ£o serem confundidos com a agenda.
  for (const m of (messages || []).slice(-600)) {
    if (m?.is_group || isGroupJid(m?.jid)) continue;
    const candidates = [
      { jid: m.sender_jid || m.jid, name: m.name },
      { jid: m.jid, name: m.chat_name },
    ];
    for (const c of candidates) {
      add(c.jid, c.name, 25, { source: 'private_messages' });
    }
  }
  for (const [jid, c] of Object.entries(contacts || {})) {
    const savedInAddressBook = c?.name_source === 'address_book';
    const groupOnly = isGroupOnlyIdentity(jid);
    if (c?.name && (savedInAddressBook || !groupOnly)) add(jid, c.name, savedInAddressBook ? 180 : 75, { source: savedInAddressBook ? 'address_book' : 'contact_name' });
    if (!groupOnly) {
      if (c?.notify && normalizeText(c.notify) !== normalizeText(c.name)) add(jid, c.notify, 45, { source: 'profile_name' });
      if (c?.pushName && normalizeText(c.pushName) !== normalizeText(c.name) && normalizeText(c.pushName) !== normalizeText(c.notify)) add(jid, c.pushName, 40, { source: 'profile_name' });
    }
  }
  for (const [jid, c] of Object.entries(chats || {})) {
    if (isGroupJid(jid)) continue;
    add(jid, displayName(c, jid), 50, { source: 'private_chat' });
  }
  for (const [jid, g] of Object.entries(groups || {})) {
    add(jid, displayName(g, jid), 0, { source: 'group' });
  }
  const dedup = new Map();
  for (const item of all.sort((a,b) => b.score - a.score || String(a.name).localeCompare(String(b.name)))) {
    const k = String(item.jid || item.name || '');
    if (!dedup.has(k)) dedup.set(k, item);
  }
  return Array.from(dedup.values()).slice(0, limit);
}
async function resolveJid(to) {
  const raw = String(to || '').trim();
  if (!raw) throw new Error('Recipient is empty');
  const alias = aliases[aliasKey(raw)];
  // Alias criado explicitamente pelo usuÃ¡rio continua absoluto. Alias aprendido
  // automaticamente participa do ranking atualizado da agenda.
  if (alias && alias.jid && alias.auto !== true) return alias.jid;
  if (raw.includes('@s.whatsapp.net') || raw.includes('@g.us') || raw.includes('@lid')) return raw;
  let found = searchContacts(raw, 5);
  if (found.length) return found[0].jid;
  const histAlias = aliasFromMessageHistory(raw);
  if (histAlias && histAlias.jid) return histAlias.jid;
  // 6.1.5: a name (not a number) that isn't known yet: fetch the address book
  // again (the first sync can run before the phone sends the keys) and retry.
  if (digitsOnly(raw).length < 8 && Date.now() - ultimaAgendaSob > 60000) {
    ultimaAgendaSob = Date.now();
    try { await refreshAddressBook(8000); } catch (_) {}
    found = searchContacts(raw, 5);
    if (found.length) return found[0].jid;
  }
  const num = normalizeBrazilNumber(raw);
  if (num.length >= 11) {
    let jid = `${num}@s.whatsapp.net`;
    try {
      if (sock?.onWhatsApp) {
        const exists = await withTimeout(sock.onWhatsApp(num), 4000, 'onWhatsApp');
        if (exists && exists[0] && exists[0].exists) jid = exists[0].jid || jid;
      }
    } catch (e) { log('onWhatsApp failed/timeout', e.message); }
    if (lastFailedName) {
      // 6.1.5: LEARNED alias, not a fixed one. The number usually comes by
      // voice and the transcription loses digits ("14 9..." became "49...");
      // a fixed alias would lock the name onto the wrong number forever.
      try {
        aliases[aliasKey(lastFailedName)] = { name: lastFailedName, jid, auto: true, source: 'after_number', updated_at: new Date().toISOString() };
        saveDb();
        log('learned alias after number', lastFailedName, jid);
        lastFailedName = '';
      } catch(e) { log('auto alias failed', e.message); }
    }
    return jid;
  }
  // POR SEMELHANCA (13/10/2026). A busca acima so aceita igual/comeca/contem;
  // um erro de transcricao ("anapaula", "o Fulano") dava "nao encontrado".
  // Aceita o melhor so se for forte (>= 100) e bem na frente do segundo (15).
  const ranking = rankearPessoasPorNome(raw);
  const melhor = ranking[0];
  const segundo = ranking[1];
  if (melhor && melhor.score >= 100 && (!segundo || melhor.score - segundo.score >= 15)) {
    log('recipient by similarity', raw, '->', melhor.name, melhor.score, 'gap', segundo ? melhor.score - segundo.score : 'unico');
    return melhor.jid;
  }
  lastFailedName = raw;
  saveStatus({ last_event:'contact_not_found', message:`Contato não encontrado: ${raw}. Se informar o número agora, vou salvar esse nome automaticamente.` });
  // Sugestoes: ate 3 nomes parecidos, so com os 4 ultimos digitos (nunca o
  // numero inteiro). Antes eram os 8 primeiros da agenda em ordem alfabetica.
  const suggestions = ranking.filter(x => x.score >= 20).slice(0, 3).map(x => ({ name: x.name, tail: finalDoNumero(x.jid) }));
  const texto = suggestions.length
    ? ` Talvez seja: ${suggestions.map(s => s.tail ? `${s.name} (final ${s.tail})` : s.name).join(', ')}.`
    : '';
  throw erroComCodigo('contact_not_found', `Contact not found: ${raw}.${texto} Use o nome como está salvo ou o número com DDD.`, { suggestions });
}
function erroComCodigo(code, message, extra = {}) {
  const e = new Error(message);
  e.error_code = code;
  e.extra = extra || {};
  return e;
}
// 4 ultimos digitos do NUMERO da pessoa. Para @lid usa o PN ligado; sem PN
// conhecido, nada (o LID nao e telefone).
function finalDoNumero(jid) {
  const j = String(jid || '');
  let pn = j.endsWith('@s.whatsapp.net') ? j : '';
  if (!pn) {
    try { for (const v of linkedPersonJids(j)) if (String(v).endsWith('@s.whatsapp.net')) { pn = v; break; } } catch (_) {}
  }
  const d = digitsOnly(String(pn).split('@')[0]);
  return d.length >= 4 ? d.slice(-4) : '';
}
// Ranking de PESSOAS (contatos, apelidos, conversas privadas) pelo
// fuzzyNameScore. Nome que e so numero fica de fora (nao vira sugestao).
// Mesmo nome em PN e LID conta uma vez so (fica o de maior prioridade).
function rankearPessoasPorNome(query) {
  const porNome = new Map();
  const add = (jid, name, prioridade) => {
    jid = String(jid || ''); name = String(name || '').trim();
    if (!jid || !name || !isPersonJid(jid)) return;
    if (_looksLikeRawParticipantName(name, jid)) return;
    const score = fuzzyNameScore(name, query);
    if (score <= 0) return;
    const k = normalizeText(name);
    const atual = porNome.get(k);
    if (!atual || score > atual.score || (score === atual.score && prioridade > atual.prioridade)) porNome.set(k, { jid, name, score, prioridade });
  };
  // Mesma regra do searchContacts (13/10/2026): quem so apareceu em GRUPO e
  // nao esta na agenda nao vira destinatario por semelhanca nem sugestao
  // (senao "manda oi pro Joao" ia para um participante desconhecido de grupo).
  const privados = new Set();
  const deGrupo = new Set();
  for (const m of (messages || [])) {
    const mj = String(m?.jid || '');
    const sj = String(m?.sender_jid || '');
    if (m?.is_group || isGroupJid(mj)) { if (isPersonJid(sj)) deGrupo.add(sj); }
    else { if (isPersonJid(mj)) privados.add(mj); if (isPersonJid(sj)) privados.add(sj); }
  }
  const soDeGrupo = (jid) => deGrupo.has(String(jid || '')) && !privados.has(String(jid || ''));
  for (const a of Object.values(aliases || {})) {
    if (a?.auto === true && a?.source !== 'address_book' && soDeGrupo(a?.jid)) continue;
    add(a?.jid, a?.name, a?.auto !== true ? 220 : (a?.source === 'address_book' ? 170 : 35));
  }
  for (const [jid, c] of Object.entries(contacts || {})) {
    const naAgenda = c?.name_source === 'address_book';
    const grupo = soDeGrupo(jid);
    if (c?.name && (naAgenda || !grupo)) add(jid, c.name, naAgenda ? 180 : 75);
    if (grupo) continue;
    if (c?.notify) add(jid, c.notify, 45);
    if (c?.pushName) add(jid, c.pushName, 40);
  }
  for (const [jid, c] of Object.entries(chats || {})) {
    if (!isGroupJid(jid)) add(jid, displayName(c, ''), 50);
  }
  return Array.from(porNome.values()).sort((a, b) => b.score - a.score || b.prioridade - a.prioridade || String(a.name).localeCompare(String(b.name)));
}
function clearQrWatchdog() { if (qrWatchdog) clearTimeout(qrWatchdog); qrWatchdog = null; }

// ===== AUTH COM GRAVACAO ATOMICA (13/10/2026) =====
// O useMultiFileAuthState do Baileys 6.7.23 grava cada chave POR CIMA do
// arquivo. O JARVIS mata a ponte (TerminateProcess) a qualquer hora: chave
// cortada vira "nao existe", a sessao Signal volta para tras (Bad MAC, "Over
// 2000 messages into the future") e creds.json cortado vira credencial nova
// (QR de novo). Esta e a MESMA logica do Baileys (mesmos nomes de arquivo,
// mesmo BufferJSON, mesma fixFileName: a sessao que ja existe continua
// valendo), mas grava em .tmp e troca pelo nome certo. Um .tmp orfao nao
// atrapalha: so o arquivo final e lido, e a proxima gravacao o substitui.
// Cada gravacao fica contada para o /shutdown esperar terminar.
const filasDeArquivo = new Map();
const gravacoesAuthPendentes = new Set();
function naFilaDoArquivo(arquivo, tarefa) {
  const anterior = filasDeArquivo.get(arquivo) || Promise.resolve();
  const atual = anterior.then(tarefa, tarefa);
  const cauda = atual.catch(() => {});
  filasDeArquivo.set(arquivo, cauda);
  cauda.then(() => { if (filasDeArquivo.get(arquivo) === cauda) filasDeArquivo.delete(arquivo); });
  return atual;
}
function contarGravacao(promessa) {
  gravacoesAuthPendentes.add(promessa);
  promessa.then(() => gravacoesAuthPendentes.delete(promessa), () => gravacoesAuthPendentes.delete(promessa));
  return promessa;
}
async function esperarGravacoesAuth(ms = 1000) {
  const fim = Date.now() + ms;
  while (gravacoesAuthPendentes.size && Date.now() < fim) {
    await Promise.race([Promise.allSettled(Array.from(gravacoesAuthPendentes)), dormir(Math.max(1, fim - Date.now()))]);
  }
  return gravacoesAuthPendentes.size === 0;
}
async function renomearComRetentativa(origem, destino) {
  for (let i = 0; i < 3; i++) {
    try { await fs.promises.rename(origem, destino); return true; }
    catch (e) {
      if (!['EPERM', 'EBUSY', 'EACCES'].includes(e.code)) throw e;
      await dormir(30 * (i + 1));
    }
  }
  return false;
}
async function gravarAtomico(arquivo, texto) {
  const tmp = arquivo + '.tmp';
  await fs.promises.writeFile(tmp, texto);
  if (await renomearComRetentativa(tmp, arquivo)) return;
  await fs.promises.writeFile(arquivo, texto);
  try { await fs.promises.unlink(tmp); } catch (_) {}
}
async function useAtomicMultiFileAuthState(folder) {
  let fechado = false;
  const fixFileName = (file) => file?.replace(/\//g, '__')?.replace(/:/g, '-');
  const writeData = (data, file) => {
    const filePath = path.join(folder, fixFileName(file));
    return contarGravacao(naFilaDoArquivo(filePath, async () => {
      if (fechado) return;
      const texto = JSON.stringify(data, BufferJSON.replacer);
      try {
        await gravarAtomico(filePath, texto);
        // creds.json bom tambem vira creds.json.bak (plano B se o principal quebrar).
        if (file === 'creds.json') await gravarAtomico(filePath + '.bak', texto);
      } catch (e) { log('auth: gravacao falhou', file, e.message); }
    }));
  };
  const readData = (file) => {
    const filePath = path.join(folder, fixFileName(file));
    return naFilaDoArquivo(filePath, async () => {
      try {
        const data = await fs.promises.readFile(filePath, { encoding: 'utf-8' });
        return JSON.parse(data, BufferJSON.reviver);
      } catch (e) {
        if (e && e.code !== 'ENOENT') log('auth: leitura falhou', file, e.message);
        return null;
      }
    });
  };
  const removeData = (file) => {
    const filePath = path.join(folder, fixFileName(file));
    return contarGravacao(naFilaDoArquivo(filePath, async () => {
      if (fechado) return;
      try { await fs.promises.unlink(filePath); } catch (_) {}
    }));
  };
  const folderInfo = await fs.promises.stat(folder).catch(() => null);
  if (folderInfo) {
    if (!folderInfo.isDirectory()) throw new Error(`found something that is not a directory at ${folder}, either delete it or specify a different location`);
  } else {
    await fs.promises.mkdir(folder, { recursive: true });
  }
  const credsPath = path.join(folder, 'creds.json');
  let creds = await readData('creds.json');
  if (!creds && fs.existsSync(credsPath)) {
    // creds.json existe mas nao abre: tenta a copia boa antes de criar
    // credencial nova (credencial nova = QR de novo).
    log('auth: creds.json corrompido; tentando creds.json.bak');
    creds = await readData('creds.json.bak');
    if (creds) {
      const quebrado = `${credsPath}.quebrado-${new Date().toISOString().replace(/[:.]/g, '-')}`;
      try { fs.copyFileSync(credsPath, quebrado); } catch (_) {}
      await writeData(creds, 'creds.json');
      log('auth: creds.json restaurado do .bak');
    } else {
      log('auth: creds.json.bak tambem indisponivel; sera preciso escanear o QR');
    }
  }
  if (!creds) creds = initAuthCreds();
  return {
    state: {
      creds,
      keys: {
        get: async (type, ids) => {
          const data = {};
          await Promise.all(ids.map(async (id) => {
            let value = await readData(`${type}-${id}.json`);
            if (type === 'app-state-sync-key' && value) value = proto.Message.AppStateSyncKeyData.fromObject(value);
            data[id] = value;
          }));
          return data;
        },
        set: async (data) => {
          const tasks = [];
          for (const category in data) {
            for (const id in data[category]) {
              const value = data[category][id];
              const file = `${category}-${id}.json`;
              tasks.push(value ? writeData(value, file) : removeData(file));
            }
          }
          await Promise.all(tasks);
        },
      },
    },
    // Credencial so vai para o disco depois do pareamento (creds.me): assim
    // "existe auth/creds.json" quer dizer "ha sessao salva" (session_saved).
    // No pareamento o Baileys manda creds.update com o objeto inteiro.
    saveCreds: async () => {
      if (!creds || !creds.me || !creds.me.id) return;
      return writeData(creds, 'creds.json');
    },
    fechar: () => { fechado = true; },
  };
}
async function abrirAuth() {
  // Sem as pecas do Baileys (ambiente de teste antigo), usa o original.
  if (!BufferJSON || typeof initAuthCreds !== 'function' || !proto) {
    const r = await useMultiFileAuthState(AUTH_DIR);
    return { ...r, fechar: () => {} };
  }
  return await useAtomicMultiFileAuthState(AUTH_DIR);
}
// Apaga a sessao salva: para de gravar no auth atual, espera o que esta em
// voo (ate 1 s) e so entao remove a pasta (senao uma gravacao atrasada
// recriava um creds.json de sessao morta).
async function apagarAuth() {
  try { if (authAtual && authAtual.fechar) authAtual.fechar(); } catch (_) {}
  await esperarGravacoesAuth(1000);
  try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch (e) { log('auth: nao consegui apagar a pasta', e.message); }
}

// ===== VERSAO DO WHATSAPP WEB (13/10/2026) =====
function compararVersao(a, b) {
  for (let i = 0; i < 3; i++) {
    const d = Number(a?.[i] || 0) - Number(b?.[i] || 0);
    if (d) return d;
  }
  return 0;
}
async function resolverVersao() {
  if (versaoWa) return versaoWa;
  let v = null;
  let origem = '';
  try {
    const r = await withTimeout(Promise.resolve(fetchLatestBaileysVersion({ timeout: 5000 })), 5000, 'fetchLatestBaileysVersion');
    if (r && Array.isArray(r.version) && r.isLatest !== false) { v = r.version; origem = 'github'; }
    else log('WhatsApp Web version: GitHub failed', String(r?.error?.message || r?.error || ''));
  } catch (e) { log('WhatsApp Web version: GitHub failed', e.message); }
  if (!v || compararVersao(v, PISO_VERSAO_WA) < 0) {
    origem = v ? `piso (github deu ${v.join('.')})` : 'piso';
    v = PISO_VERSAO_WA.slice();
  }
  versaoWa = v;
  versaoOrigem = origem;
  log('WhatsApp Web version', v.join('.'), 'source:', origem);
  return v;
}
// So depois de um 405 (versao recusada): pergunta ao proprio web.whatsapp.com.
async function resolverVersaoWaWeb() {
  if (typeof fetchLatestWaWebVersion !== 'function') return false;
  try {
    const r = await withTimeout(Promise.resolve(fetchLatestWaWebVersion({
      timeout: 5000,
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36', 'sec-fetch-site': 'none' },
    })), 6000, 'fetchLatestWaWebVersion');
    if (r && r.isLatest && Array.isArray(r.version) && compararVersao(r.version, versaoWa || PISO_VERSAO_WA) > 0) {
      versaoWa = r.version;
      versaoOrigem = 'web.whatsapp.com';
      log('WhatsApp Web version', versaoWa.join('.'), 'source:', versaoOrigem);
      return true;
    }
    log('WhatsApp Web version: web.whatsapp.com did not give a newer one', String(r?.error?.message || ''));
  } catch (e) { log('WhatsApp Web version: web.whatsapp.com failed', e.message); }
  return false;
}

// ===== ULTIMO DESLIGAMENTO (13/10/2026) =====
// Copia segura do error.data do Baileys (pode trazer Buffer/no binario).
function dadoSeguro(v) {
  if (v === undefined || v === null) return null;
  try {
    const texto = JSON.stringify(v, (_k, x) => {
      if (x && x.type === 'Buffer' && Array.isArray(x.data)) return `<buffer ${x.data.length}>`;
      if (x instanceof Uint8Array) return `<buffer ${x.length}>`;
      return x;
    });
    if (!texto) return null;
    if (texto.length > 4000) return texto.slice(0, 4000);
    return JSON.parse(texto);
  } catch (_) { return String(v).slice(0, 1000); }
}
function gravarUltimoDesligamento(registro) {
  // Logout ainda sem sessao nova: um close da fase do QR (408 do QR que
  // expirou etc.) NAO apaga o registro do logout. E ele que explica ao
  // usuario por que o WhatsApp saiu; o close novo fica no bridge.log.
  if (ultimoDesligamento && ultimoDesligamento.logged_out && !registro.logged_out && !sessaoSalva()) {
    log('last_disconnect kept (logout still pending)', registro.code, registro.reason);
    return;
  }
  ultimoDesligamento = registro;
  try { gravarArquivoAtomicoSync(LAST_DISCONNECT_FILE, JSON.stringify(registro, null, 2)); }
  catch (e) { log('last_disconnect write failed', e.message); }
}
// Mapa de codigos (13/10/2026). Antes tudo que nao era 401 religava em 3 s
// para sempre, inclusive conta banida (403) e versao recusada (405).
function motivoDoFechamento(statusCode, mensagem) {
  if (statusCode === 401) return 'user_logged_out';
  if (statusCode === 411) return 'multidevice_mismatch';
  if (statusCode === 403) return 'banned';
  if (statusCode === 405) return 'version_rejected';
  if (statusCode === 408 && /QR refs attempts ended/i.test(String(mensagem || ''))) return 'qr_expired';
  return 'connection_lost';
}
function mensagemDeEstado() {
  if (currentConnected()) return 'WhatsApp conectado com sucesso.';
  if (paradoMotivo === 'banned') return 'O WhatsApp bloqueou esta conta para o JARVIS (código 403). Confira o WhatsApp no celular.';
  if (paradoMotivo === 'qr_expired') return 'O QR Code expirou sem ser escaneado. Clique em "Gerar QR novo" ou peça para conectar o WhatsApp.';
  if (paradoMotivo === 'version_rejected') return 'O WhatsApp recusou a versão da ponte (código 405). Tente de novo mais tarde.';
  if (lastQr) return 'QR Code gerado. Escaneie com o WhatsApp.';
  if (lastDisconnectReason === 'user_logged_out' || lastDisconnectReason === 'multidevice_mismatch') return 'WhatsApp desconectado completamente. Sessão antiga limpa; peça conectar WhatsApp para gerar QR novo.';
  if (reconectandoAgora()) return 'Reconectando ao WhatsApp...';
  return 'Ponte WhatsApp ativa. Aguardando conexão/QR Code.';
}

// Nao apaga mais o status.json a cada start (13/10/2026): na reconexao de 50
// em 50 min quem lia o arquivo no meio pegava "nao existe". So no fresh.
async function cleanSessionFiles(clearAuth = false) {
  try { if (fs.existsSync(QR_FILE)) fs.unlinkSync(QR_FILE); } catch (_) {}
  lastQr = '';
  if (clearAuth) {
    try { if (fs.existsSync(STATUS_FILE)) fs.unlinkSync(STATUS_FILE); } catch (_) {}
    encerrarConexaoAtual();
    await apagarAuth();
    freshLoginRequired = false;
    // O motivo (ex.: user_logged_out) continua no status ate o proximo 'open'
    // ou um /reset: e ele que explica por que um QR novo foi pedido.
    log('Auth session cleaned for fresh WhatsApp login.');
  }
}
function scheduleQrWatchdog() {
  clearQrWatchdog();
  qrWatchdog = setTimeout(() => {
    if (currentConnected() || lastQr) return;
    lastEvent = 'qr_timeout';
    saveStatus({ connected: false, has_qr: false, last_event: lastEvent, message: 'QR Code ainda não foi gerado. Feche o Mark-XLVIII, rode 8_instalar_whatsapp_bridge.bat e tente de novo.', error: 'QR timeout' });
    log('QR timeout. No qr event received from Baileys.');
  }, 45000);
}
async function start({ fresh = false } = {}) {
  if (desligando) return;
  if (freshLoginRequired) fresh = true;
  // START PEDIDO NO MEIO DE OUTRO START (13/10/2026). Era descartado: o /reset
  // agendava um start em 700 ms; se o start anterior ainda buscava a versao,
  // o novo era jogado fora, o antigo via a geracao nova e desistia, e a ponte
  // ficava sem conexao nenhuma. Agora o pedido espera e roda no fim.
  if (starting) {
    startPendente = { fresh: Boolean(fresh || (startPendente && startPendente.fresh)) };
    log('Start requested while another start is running: queued', startPendente);
    return;
  }
  starting = true;
  let minha = -1;
  let deuCerto = false;
  try {
    clearQrWatchdog();
    // A conexao anterior (se houver) morre ANTES de a nova nascer. Ver
    // `geracao` la em cima.
    encerrarConexaoAtual();
    await cleanSessionFiles(Boolean(fresh));
    // A conexao velha pode estar gravando chave de sessao: le o auth so
    // depois (senao a nova conexao nasce com a chave de antes).
    await esperarGravacoesAuth(2000);
    // Depois da limpeza: `cleanSessionFiles(true)` tambem encerra (e conta).
    minha = geracao;
    const vale = () => minha === geracao;
    manualLogoutInProgress = false;
    fs.mkdirSync(AUTH_DIR, { recursive: true });
    try { if (!fs.existsSync(LOG_FILE)) fs.writeFileSync(LOG_FILE, ''); } catch (_) {}
    connected = false;
    lastEvent = 'starting';
    const comSessao = sessaoSalva();
    saveStatus({ connected: false, has_qr: false, message: comSessao ? 'Reconectando ao WhatsApp...' : 'Iniciando ponte WhatsApp. Gerando QR Code...', last_event: 'starting' });
    log('Starting bridge', { port: PORT, root: ROOT, fresh, session_saved: comSessao });
    const auth = await abrirAuth();
    const { state, saveCreds } = auth;
    const version = await resolverVersao();
    if (!vale()) { try { auth.fechar(); } catch (_) {} log('Start abandoned: a newer connection was requested meanwhile.'); return; }
    authAtual = auth;
    // Cache das chaves Signal na memoria (13/10/2026): menos leitura de disco
    // a cada mensagem. As gravacoes continuam indo para o arquivo na hora.
    const chaves = (typeof makeCacheableSignalKeyStore === 'function' && state && state.keys)
      ? makeCacheableSignalKeyStore(state.keys, baileysLogger)
      : (state && state.keys);
    sock = makeWASocket({
      version,
      auth: { creds: state && state.creds, keys: chaves },
      logger: baileysLogger,
      // printQRInTerminal saiu (13/10/2026): obsoleto no 6.7.x, so gerava aviso.
      // O SISTEMA QUE O CELULAR MOSTRA em "Aparelhos conectados" (27/09/2026).
      // Era sempre Windows — no cliente do Big Linux o WhatsApp dele mostrava
      // um aparelho Windows que ele nao tem. Agora e o sistema de verdade.
      // (Nao muda o historico: o syncFullHistory esta desligado logo abaixo.)
      browser: process.platform === 'linux'
        ? ['Linux', 'Mark-XLVIII', require('os').release()]
        : process.platform === 'darwin'
          ? Browsers.macOS('Mark-XLVIII')
          : Browsers.windows('Mark-XLVIII'),
      connectTimeoutMs: 30000,
      // 60 s / 30 s (13/10/2026), o recomendado: com 15 s as consultas de
      // sessao em rede lenta estouravam e o envio dava "Timed Out".
      defaultQueryTimeoutMs: 60000,
      keepAliveIntervalMs: 30000,
      qrTimeout: 60000,
      markOnlineOnConnect: false,
      // MODO SEGURO: não forçar histórico completo. Forçar syncFullHistory derruba a conexão em alguns WhatsApp.
      syncFullHistory: false,
      fireInitQueries: true,
      generateHighQualityLinkPreview: false,
      // Reenvio quando o destinatario pede de novo (13/10/2026). Ver enviadasCache.
      getMessage: getMessageGuardada,
      msgRetryCounterCache,
      // Status e canais: ninguem le, e decifrar gerava pedidos de reenvio inuteis.
      shouldIgnoreJid: ignorarJid,
    });
    socketVivo = true;
    const meuSock = sock;
    // TODO OUVINTE COM A GUARDA DA GERACAO (13/10/2026). So creds.update e
    // connection.update tinham: eventos atrasados de um socket velho ainda
    // entravam no banco.
    const ouvir = (evento, fn) => meuSock.ev.on(evento, (...a) => { if (!vale()) return; return fn(...a); });
    // Credencial de conexao velha nao se grava: ela estragaria a da nova.
    ouvir('creds.update', (...a) => saveCreds(...a));
    ouvir('contacts.upsert', (items) => { for (const c of items || []) if (c?.id) rememberContact(c.id, c, { source: 'address_book' }); saveDb(); });
    ouvir('contacts.update', (items) => { for (const c of items || []) if (c?.id) rememberContact(c.id, c, { source: 'address_book' }); saveDb(); });
    ouvir('chats.upsert', (items) => { for (const c of items || []) { if (!c?.id) continue; if (c.id.endsWith('@g.us')) rememberGroup(c.id, c); else rememberChat(c.id, c); } saveDb(); });
    ouvir('chats.update', (items) => { for (const c of items || []) { if (!c?.id) continue; if (c.id.endsWith('@g.us')) rememberGroup(c.id, c); else rememberChat(c.id, c); } saveDb(); });
    ouvir('groups.update', (items) => { for (const g of items || []) { if (g?.id) rememberGroup(g.id, { ...g, name: g.subject, subject: g.subject }); } saveDb(); });
    ouvir('messaging-history.set', ({ chats: hc, contacts: hct, messages: hm }) => {
      try {
        for (const c of hct || []) if (c?.id) rememberContact(c.id, c, { source: 'address_book' });
        for (const c of hc || []) if (c?.id) { if (c.id.endsWith('@g.us')) rememberGroup(c.id, c); else rememberChat(c.id, c); }
        for (const m of hm || []) rememberMessage(m);
        saveDb();
        saveStatus({ message: `Sincronizado. Contatos: ${contactCount()}, conversas: ${chatCount()}, mensagens: ${msgCount()}.`, last_event: 'history_sync' });
      } catch (e) { log('history event error', e.message); }
    });
    ouvir('messages.upsert', ({ messages: newMessages }) => {
      for (const m of newMessages || []) {
        // Mensagem nossa (daqui ou do celular) fica guardada para o reenvio.
        if (m?.key?.fromMe && m.message) guardarEnviada(m.key, m.message);
        rememberMessage(m);
      }
    });
    ouvir('messages.update', (updates) => {
      try {
        for (const u of updates || []) {
          if (u?.update?.message) rememberMessage({ key: u.key, message: u.update.message, messageTimestamp: Math.floor(Date.now()/1000), pushName: u.update.pushName || '' });
          verificarEnvioRecusado(u);
        }
      } catch(e) { log('messages.update error', e.message); }
    });
    meuSock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;
      if (!vale()) {
        // Conexao antiga falando depois de encerrada: so fica no registro.
        if (connection || qr) log('old connection.update ignored', { connection, hasQr: Boolean(qr), geracao: minha, atual: geracao });
        return;
      }
      log('connection.update', { connection, hasQr: Boolean(qr), statusCode: lastDisconnect?.error?.output?.statusCode });
      if (qr) {
        clearQrWatchdog();
        lastQr = qr;
        connected = false;
        lastEvent = 'qr';
        // PNG travado (a janela do QR aberta) virava rejeicao sem dono (13/10/2026).
        try { await QRCode.toFile(QR_FILE, qr, { width: 420, margin: 2 }); }
        catch (e) { log('QR file write failed', e.message); }
        if (!vale()) return;
        saveStatus({ connected: false, has_qr: fs.existsSync(QR_FILE), message: 'QR Code gerado. Escaneie com o WhatsApp.', last_event: 'qr' });
        log('QR generated', QR_FILE);
      }
      if (connection === 'open') {
        clearQrWatchdog();
        connected = true;
        freshLoginRequired = false;
        lastDisconnectReason = '';
        paradoMotivo = '';
        falhasSeguidas = 0;
        falhasStart = 0;
        tentouVersaoNova = false;
        lastQr = '';
        lastEvent = 'connected';
        try { if (fs.existsSync(QR_FILE)) fs.unlinkSync(QR_FILE); } catch (_) {}
        saveStatus({ connected: true, has_qr: false, message: 'WhatsApp conectado com sucesso. Leitura de novas mensagens ativa.', last_event: 'connected', connected_at: new Date().toISOString(), safe_sync: true });
        log('Connected.');
        refreshGroups(6000).catch(e => log('background groups failed', e.message));
        refreshAddressBook(20000).catch(e => log('background address book failed', e.message));
        // 6.1.5: right after connecting the phone hasn't sent the keys to read
        // the address book yet (only 5 contacts came in). Try again a bit later.
        for (const ms of [15000, 60000]) {
          setTimeout(() => { if (currentConnected()) refreshAddressBook(20000).then(() => log('address book retry', ms / 1000 + 's', 'contacts', contactCount())).catch(() => {}); }, ms);
        }
      }
      if (connection === 'close') {
        clearQrWatchdog();
        connected = false;
        socketVivo = false;
        lastQr = '';
        lastEvent = 'disconnected';
        const erro = lastDisconnect?.error;
        const statusCode = erro?.output?.statusCode;
        // O MOTIVO INTEIRO NO LOG (13/10/2026): antes so o numero; o texto e
        // o error.data (o no <failure>/<stream:error>) eram jogados fora.
        const mensagemErro = String(erro?.message || '');
        const dados = dadoSeguro(erro?.data);
        log('Disconnected detail', statusCode, mensagemErro, JSON.stringify(dados));
        const manual = manualLogoutInProgress;
        const motivo = manual ? 'user_logged_out' : motivoDoFechamento(statusCode, mensagemErro);
        // 411 e tratado como 401: limpa a sessao e pede QR.
        const userLoggedOut = motivo === 'user_logged_out' || motivo === 'multidevice_mismatch';
        // 405 = versao recusada: tenta UMA vez com a versao do web.whatsapp.com.
        let tentarVersaoNova = false;
        if (motivo === 'version_rejected' && !tentouVersaoNova) { tentouVersaoNova = true; tentarVersaoNova = true; }
        lastDisconnectReason = motivo;
        // last_disconnect.json ANTES de apagar o auth. Logout pedido pelo
        // proprio JARVIS (/logout) fica como 'manual_logout' e logged_out
        // false: nao e "o celular derrubou", e o aviso nao deve sair.
        if (statusCode !== undefined && statusCode !== null) {
          gravarUltimoDesligamento({
            code: Number(statusCode),
            reason: manual ? 'manual_logout' : motivo,
            message: mensagemErro,
            data: dados,
            at: new Date().toISOString(),
            logged_out: Boolean(userLoggedOut && !manual),
          });
        }
        let reconectar = false;
        let esperaMs = 0;
        if (userLoggedOut) {
          // Quando o usuário desconecta pelo celular, as credenciais locais ficam inválidas.
          // Limpa imediatamente para o próximo pedido de conexão gerar um QR 100% novo.
          freshLoginRequired = true;
          paradoMotivo = motivo;
          encerrarConexaoAtual();
          const g = geracao;
          try { if (fs.existsSync(QR_FILE)) fs.unlinkSync(QR_FILE); } catch (_) {}
          try { if (authAtual && authAtual.fechar) authAtual.fechar(); } catch (_) {}
          await esperarGravacoesAuth(1000);
          // Se alguem pediu conexao nova nesse meio-tempo, ela cuida da pasta.
          if (g === geracao) { try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch (_) {} }
          lastQr = '';
        } else if (motivo === 'banned' || motivo === 'qr_expired' || (motivo === 'version_rejected' && !tentarVersaoNova)) {
          // Pede acao do usuario: para de religar (antes martelava a cada 3 s).
          paradoMotivo = motivo;
        } else if (tentarVersaoNova) {
          reconectar = true;
          esperaMs = 1000;
        } else {
          // ESPERA CRESCENTE (13/10/2026): 3 s, 6 s, 12 s, 24 s... ate 60 s,
          // zerada no 'open'. 440 = "outra sessao substituiu esta": outro
          // programa (ou outro PC) com a MESMA sessao; religar rapido so briga
          // com ele em laco, entao continua esperando 20 s.
          reconectar = true;
          esperaMs = statusCode === 440 ? 20000 : Math.min(60000, 3000 * Math.pow(2, falhasSeguidas));
          if (agendarReconexao(minha, esperaMs) && statusCode !== 440) falhasSeguidas += 1;
        }
        const disconnectMessage = userLoggedOut
          ? 'WhatsApp desconectado pelo usuário. Sessão antiga limpa; ao conectar novamente será gerado um QR Code novo.'
          : (paradoMotivo ? mensagemDeEstado() : (reconectar ? 'WhatsApp desconectado. Reconectando...' : 'WhatsApp desconectado.'));
        saveStatus({ connected: false, has_qr: false, message: disconnectMessage, statusCode, disconnect_reason: lastDisconnectReason, fresh_login_required: freshLoginRequired, last_event: 'disconnected' });
        log('Disconnected.', statusCode, lastDisconnectReason, 'reconnect:', reconectar, reconectar ? `in ${esperaMs}ms` : '', 'freshLoginRequired:', freshLoginRequired);
        manualLogoutInProgress = false;
        if (tentarVersaoNova) {
          await resolverVersaoWaWeb();
          agendarReconexao(minha, esperaMs);
        }
      }
    });
    // Com sessao salva nao vem QR: o aviso de "QR nao gerado" so vale sem ela.
    if (!comSessao) scheduleQrWatchdog();
    saveStatus({ connected: false, has_qr: false, message: comSessao ? 'Reconectando ao WhatsApp...' : 'Ponte WhatsApp iniciada. Aguardando QR Code...', last_event: 'started' });
    deuCerto = true;
  } catch (err) {
    log('Start failed', err?.stack || err);
    lastEvent = 'error';
    socketVivo = false;
    saveStatus({ connected: false, has_qr: false, message: 'Falha ao iniciar ponte WhatsApp. Nova tentativa em instantes.', error: String(err?.message || err), last_event: 'error' });
    agendarNovoStart();
  } finally {
    starting = false;
    const pendente = startPendente;
    startPendente = null;
    if (pendente && !desligando) {
      // Roda o pedido guardado se ele e um fresh (reset), se este start nao
      // chegou ao fim ou se uma conexao mais nova foi pedida no meio.
      if (pendente.fresh || !deuCerto || minha !== geracao) {
        log('Running queued start', pendente);
        setImmediate(() => start(pendente).catch(e => log('Queued start failed', e?.stack || e)));
      } else {
        log('Queued start dropped: the connection just created is the current one.');
      }
    }
  }
}
async function convertAudioToOpus(inputPath) {
  if (!ffmpegPath) throw new Error('ffmpeg-static não instalado. Rode 8_instalar_whatsapp_bridge.bat novamente.');
  const out = path.join(MEDIA_DIR, `voice_${Date.now()}.ogg`);
  await new Promise((resolve, reject) => {
    const args = ['-y', '-i', inputPath, '-vn', '-ac', '1', '-ar', '48000', '-c:a', 'libopus', '-b:a', '32k', '-f', 'ogg', out];
    const p = spawn(ffmpegPath, args, { windowsHide: true });
    let err = '';
    p.stderr.on('data', d => err += d.toString());
    p.on('error', reject);
    p.on('close', code => code === 0 && fs.existsSync(out) && fs.statSync(out).size > 500 ? resolve() : reject(new Error('ffmpeg falhou ao converter áudio: ' + err.slice(-400))));
  });
  return out;
}
function mediaPayload(filePath, caption = '') {
  if (!filePath || !fs.existsSync(filePath)) throw new Error('Arquivo não encontrado: ' + filePath);
  const st = fs.statSync(filePath);
  if (st.isDirectory()) throw new Error('Recebi uma pasta sem compactar. Compacte em ZIP antes de enviar pelo WhatsApp.');
  if (MAX_SEND_BYTES && st.size > MAX_SEND_BYTES) {
    const mb = (st.size / (1024 * 1024)).toFixed(2);
    const limitMb = Math.round(MAX_SEND_BYTES / (1024 * 1024));
    throw new Error(`Arquivo muito grande para enviar pelo WhatsApp nesta configuração: ${path.basename(filePath)} (${mb} MB). Limite atual: ${limitMb} MB.`);
  }
  const mt = (mime && mime.lookup(filePath)) || 'application/octet-stream';
  const fileName = path.basename(filePath);
  if (mt.startsWith('image/')) return { image: { url: filePath }, caption: caption || '' };
  if (mt.startsWith('video/')) return { video: { url: filePath }, caption: caption || '', mimetype: mt };
  if (mt.startsWith('audio/')) return { audio: { url: filePath }, mimetype: mt, ptt: false };
  return { document: { url: filePath }, fileName, mimetype: mt, caption: caption || '' };
}
async function refreshGroups(timeoutMs = 6000) {
  if (!currentConnected()) throw new Error('WhatsApp is not connected.');
  if (!sock.groupFetchAllParticipating) return Object.values(groups);
  const data = await withTimeout(sock.groupFetchAllParticipating(), timeoutMs, 'groupFetchAllParticipating');
  for (const [jid, g] of Object.entries(data || {})) rememberGroup(jid, { ...g, name: g.subject, subject: g.subject });
  saveDb();
  saveStatus({ last_event: 'groups', message: `Grupos atualizados: ${groupCount()}.` });
  return Object.values(groups);
}

async function refreshAddressBook(timeoutMs = 20000) {
  if (!currentConnected() || !sock?.resyncAppState || contactSyncInFlight) return false;
  contactSyncInFlight = true;
  try {
    // A colecao "critical_unblock_low" contem as alteracoes da agenda (contactAction).
    // Isto nao solicita historico completo de mensagens.
    await withTimeout(sock.resyncAppState(['critical_unblock_low'], false), timeoutMs, 'address book sync');
    saveDb();
    log('Address book app-state synchronized.');
    return true;
  } catch (e) {
    log('address book sync failed/timeout', e.message);
    return false;
  } finally {
    contactSyncInFlight = false;
  }
}


async function resolveGroupJid(groupName) {
  if (!currentConnected()) throw new Error('WhatsApp is not connected.');
  const raw = String(groupName || '').trim();
  if (!raw) {
    if (pendingLeaveGroup && pendingLeaveGroup.jid) return pendingLeaveGroup;
    throw new Error('Nome do grupo é obrigatório.');
  }
  if (raw.endsWith('@g.us')) {
    const g = groups[raw] || chats[raw] || {};
    return { jid: raw, name: g.subject || g.name || raw };
  }
  try { await refreshGroups(6000); } catch(e) { log('resolveGroupJid refresh failed', e.message); }
  const target = normalizeText(raw);
  const candidates = [];
  for (const [jid, g] of Object.entries(groups || {})) {
    const name = g.subject || g.name || jid;
    const score = fuzzyNameScore(name + ' ' + jid, raw);
    if (score >= 45) candidates.push({ jid, name, score });
  }
  // Also search normal resolver results, but only group JIDs.
  for (const item of searchContacts(raw, 30)) {
    if (!String(item.jid || '').endsWith('@g.us')) continue;
    const score = Math.max(item.score || 0, fuzzyNameScore(item.name || item.jid, raw));
    if (score >= 45) candidates.push({ jid: item.jid, name: item.name || item.jid, score });
  }
  const dedup = new Map();
  for (const c of candidates.sort((a,b)=>b.score-a.score)) if (!dedup.has(c.jid)) dedup.set(c.jid, c);
  const list = Array.from(dedup.values());
  if (!list.length) throw new Error(`Grupo não encontrado: ${raw}. Peça para listar os grupos e use exatamente o nome exibido.`);
  // If many exact-looking results exist, choose the best but include name in result.
  return list[0];
}

// ERRO INTERNO NAO E DESCONEXAO (13/10/2026). Antes qualquer rejeicao do
// Baileys ("Connection Closed", "Timed Out") gravava connected:false com o
// socket aberto, e o JARVIS lia "nao conectado". Agora so registra o erro.
function registrarErroGlobal(tipo, err) {
  log(tipo, err?.stack || err);
  ultimoErro = String(err?.message || err).slice(0, 500);
  ultimoErroEm = new Date().toISOString();
  try { saveStatus({ last_error: ultimoErro, last_error_at: ultimoErroEm }); } catch (_) {}
}
process.on('uncaughtException', err => registrarErroGlobal('UNCAUGHT', err));
process.on('unhandledRejection', err => registrarErroGlobal('UNHANDLED', err));

const app = express();
app.use(cors());
app.use(express.json({ limit: '30mb' }));

app.get('/', (_req, res) => {
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end(`<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mark-XLVIII — WhatsApp QR</title>
<style>
body{margin:0;background:#02070b;color:#8ffcff;font-family:Consolas,monospace;display:flex;min-height:100vh;align-items:center;justify-content:center}.box{width:min(92vw,520px);border:1px solid #0d5670;border-radius:14px;background:#010f18;padding:22px;box-shadow:0 0 30px #00384a}h1{color:#00d4ff;text-align:center;font-size:22px;margin:0 0 10px}.status{text-align:center;color:#d8f8ff;margin:8px 0 16px;min-height:24px}.qr{background:white;border-radius:12px;padding:10px;width:280px;height:280px;object-fit:contain;display:block;margin:0 auto}.ok{background:#001a0d;color:#00ff88;border:1px solid #00aa55;border-radius:12px;padding:35px 10px;text-align:center;font-size:28px;font-weight:bold}.muted{color:#5ab8cc;text-align:center;font-size:13px;line-height:1.45}.row{display:flex;gap:8px;justify-content:center;margin-top:16px}button{background:#011520;color:#00d4ff;border:1px solid #0d5670;border-radius:8px;padding:10px 12px;font-family:inherit;cursor:pointer}button:hover{border-color:#00d4ff}</style>
</head><body><div class="box"><h1>J.A.R.V.I.S — WhatsApp</h1><div id="status" class="status">Iniciando ponte...</div><div id="area"></div><p class="muted">No celular: WhatsApp → Aparelhos conectados → Conectar aparelho. Depois escaneie o QR Code.</p><div class="row"><button onclick="resetar()">Gerar QR novo</button><button onclick="location.reload()">Atualizar</button></div></div>
<script>
async function load(){try{const s=await fetch('/status?ts='+Date.now()).then(r=>r.json());const st=document.getElementById('status'),a=document.getElementById('area');if(s.connected){st.textContent='WhatsApp conectado com sucesso.';a.innerHTML='<div class="ok">✓<br>WHATSAPP<br>CONECTADO</div>';return;}st.textContent=s.has_qr?'Escaneie o QR Code abaixo.':(s.message||s.last_event||'Aguardando QR Code...');if(s.has_qr){a.innerHTML='<img class="qr" src="/qr?ts='+Date.now()+'">';}else{a.innerHTML='<div class="muted">QR ainda não disponível. Aguarde alguns segundos...</div>';}}catch(e){document.getElementById('status').textContent='Ponte offline ou iniciando...';document.getElementById('area').innerHTML='<div class="muted">Se demorar, rode 8_instalar_whatsapp_bridge.bat e tente novamente.</div>';}}
async function resetar(){await fetch('/reset',{method:'POST'}).catch(()=>{});setTimeout(load,1200)}
load(); setInterval(load,2500);
</script></body></html>`);
});

app.get('/status', (_req, res) => res.json(statusPayload()));
app.get('/qr', (_req, res) => { if (fs.existsSync(QR_FILE)) return res.sendFile(QR_FILE); res.status(404).json({ ok: false, error: 'QR not available.' }); });
app.post('/reset', async (_req, res) => {
  if (desligando) return res.status(503).json({ ok: false, error: 'Ponte encerrando.' });
  log('Reset requested. Cleaning previous auth/session before new QR.');
  // Encerrar pela geracao: o fechamento desta conexao NAO pode agendar outra
  // (era isso que fazia nascer a segunda conexao, 3 s depois do reset).
  encerrarConexaoAtual();
  try { connected = false; lastQr = ''; freshLoginRequired = false; lastDisconnectReason = ''; } catch (_) {}
  // Reset tira a ponte de qualquer parada (banida, QR expirado, 405).
  paradoMotivo = ''; falhasSeguidas = 0; falhasStart = 0; tentouVersaoNova = false;
  await apagarAuth();
  try { if (fs.existsSync(QR_FILE)) fs.unlinkSync(QR_FILE); } catch (_) {}
  saveStatus({ connected:false, has_qr:false, message:'Sessão WhatsApp antiga limpa. Gerando QR Code novo...', last_event:'reset_clean' });
  res.json({ ok: true, result: 'Sessão WhatsApp antiga limpa. Gerando QR Code novo.' });
  setTimeout(() => start({ fresh: true }), 700);
});
// POST /start (13/10/2026): conecta SEM apagar a sessao. Tira a ponte da
// parada (QR expirado, 403, 405, logout) e, se nao ha sessao, gera QR novo.
// Se ja ha uma conexao a caminho, nao derruba (o QR na tela continua valendo).
app.post('/start', (_req, res) => {
  if (desligando) return res.status(503).json({ ok: false, error: 'Ponte encerrando.' });
  if (currentConnected()) return res.json({ ok: true, result: 'WhatsApp já está conectado.', connected: true });
  if (!paradoMotivo && (starting || reconexao || socketVivo)) {
    return res.json({ ok: true, result: 'A ponte já está conectando ao WhatsApp.', connected: false, in_progress: true });
  }
  log('Start requested', { parado: paradoMotivo });
  paradoMotivo = ''; falhasSeguidas = 0; falhasStart = 0; tentouVersaoNova = false;
  cancelarReconexao();
  res.json({ ok: true, result: 'Conectando ao WhatsApp.', connected: false });
  start({ fresh: false }).catch(e => log('Start via /start failed', e?.stack || e));
});
// POST /shutdown (13/10/2026). O JARVIS matava a ponte com TerminateProcess
// no meio da gravacao das chaves (Bad MAC, sessao estragada). Agora pede para
// sair: cancela a religacao, fecha o socket, espera as gravacoes de credencial
// e chave terminarem, grava o banco e o status e sai com 0 em ate 1,5 s.
app.post('/shutdown', (_req, res) => {
  res.json({ ok: true });
  let foi = false;
  const ir = () => { if (foi) return; foi = true; encerrarComCalma('http'); };
  res.once('finish', ir);
  setTimeout(ir, 100);
});
async function encerrarComCalma(origem) {
  if (desligando) return;
  desligando = true;
  log('Shutdown requested', origem);
  const limite = setTimeout(() => { log('Shutdown: time limit reached'); finalizarProcesso(); }, 1400);
  try {
    cancelarReconexao();
    clearQrWatchdog();
    encerrarConexaoAtual();
    connected = false;
    if (!(await esperarGravacoesAuth(1000))) log('Shutdown: auth writes still pending', gravacoesAuthPendentes.size);
  } catch (_) {}
  clearTimeout(limite);
  finalizarProcesso();
}
function finalizarProcesso() {
  if (finalizado) return;
  finalizado = true;
  try { saveDbAgora(); } catch (_) {}
  try { saveStatus({ connected: false, has_qr: false, message: 'Ponte encerrada', last_event: 'shutdown' }); } catch (_) {}
  try { log('Bridge closed.'); } catch (_) {}
  try { if (baileysDestino && baileysDestino.flushSync) baileysDestino.flushSync(); } catch (_) {}
  sairCom(0);
}
app.get('/contacts', (req, res) => { const q = String(req.query.q || ''); const limit = Math.min(Number(req.query.limit || 20), 50); res.json({ ok: true, query: q, contacts: searchContacts(q, limit), total_contacts: contactCount(), total_chats: chatCount(), total_groups: groupCount() }); });
app.get('/groups', async (req, res) => {
  try { if (currentConnected() && String(req.query.refresh || '1') !== '0') { try { await refreshGroups(6000); } catch(e) { log('groups refresh failed', e.message); } } const items = Object.values(groups).map(g => ({ jid: g.id, name: g.subject || g.name || g.id })).sort((a,b)=>String(a.name).localeCompare(String(b.name))); res.json({ ok: true, groups: items, total: items.length }); }
  catch(e) { res.status(500).json({ ok:false, error:String(e.message || e) }); }
});
app.get('/messages/latest', async (req, res) => {
  try {
    const limit = Math.min(Number(req.query.limit || 10), 50);
    const direction = String(req.query.direction || 'all').toLowerCase();
    const chat = String(req.query.chat || '').trim();
    const includeSystem = String(req.query.include_system || '0') === '1';
    const jid = chat ? await resolveJid(chat) : '';
    let list = messages.slice();
    if (jid) list = filterMessagesByResolvedChat(list, jid);
    if (direction === 'incoming') list = list.filter(m => !m.from_me);
    if (direction === 'outgoing' || direction === 'sent') list = list.filter(m => m.from_me);
    if (!includeSystem) list = list.filter(isMeaningfulMessageItem);
    list = list.slice(-limit).reverse();
    // Erro com error_code/suggestions (13/10/2026), como no /send.
    res.json({ ok:true, messages:list, total:messages.length });
  } catch(e) { res.status(500).json(corpoDeErro(e)); }
});

app.get('/messages/audio/last', async (req, res) => {
  try {
    const chat = String(req.query.chat || '').trim();
    const jid = chat ? await resolveJid(chat) : '';
    let list = messages.slice();
    if (jid) list = filterMessagesByResolvedChat(list, jid);
    list = list.filter(m => !m.from_me && (String(m.type || '').toLowerCase().includes('audio') || String(m.media_kind || '').toLowerCase() === 'audio' || /\[áudio|\[audio/i.test(String(m.text || ''))));
    const msg = list.length ? list[list.length - 1] : null;
    res.json({ ok:true, message:msg, total:messages.length });
  } catch(e) { res.status(500).json(corpoDeErro(e)); }
});

app.get('/messages/last', async (req, res) => {
  try {
    const direction = String(req.query.direction || 'all').toLowerCase();
    const chat = String(req.query.chat || '').trim();
    const includeSystem = String(req.query.include_system || '0') === '1';
    const jid = chat ? await resolveJid(chat) : '';
    let list = messages.slice();
    if (jid) list = filterMessagesByResolvedChat(list, jid);
    if (direction === 'incoming') list = list.filter(m => !m.from_me);
    if (direction === 'outgoing' || direction === 'sent') list = list.filter(m => m.from_me);
    if (!includeSystem) list = list.filter(isMeaningfulMessageItem);
    const msg = list.length ? list[list.length - 1] : null;
    res.json({ ok:true, message:msg, total:messages.length });
  } catch(e) { res.status(500).json(corpoDeErro(e)); }
});
function messageStubFromPayload(payload, fallbackText = '') {
  if (payload?.text) return { conversation: String(payload.text || fallbackText || '') };
  if (payload?.image) return { imageMessage: { caption: String(payload.caption || fallbackText || '') } };
  if (payload?.video) return { videoMessage: { caption: String(payload.caption || fallbackText || '') } };
  if (payload?.audio) return { audioMessage: {} };
  if (payload?.document) return { documentMessage: { caption: String(payload.caption || fallbackText || ''), fileName: String(payload.fileName || '') } };
  return { conversation: String(fallbackText || '') };
}
// ===== ENVIO (13/10/2026) =====
// Toda falha de envio sai com error_code, para o JARVIS falar a frase certa:
// no_session, needs_qr, not_connected, contact_not_found, timeout,
// send_failed, banned. O texto em ingles continua (o Python antigo procura
// "not connected" nele). Resultado incerto (estourou o tempo ou a conexao
// caiu com o envio em andamento) e 'timeout': a mensagem PODE ter saido.
function codigoDoErroDeEnvio(e) {
  if (e && e.error_code) return e.error_code;
  const msg = String(e?.message || e || '');
  if (/timeout after|timed out|connection closed|connection lost|connection terminated/i.test(msg)) return 'timeout';
  return 'send_failed';
}
function corpoDeErro(e) {
  return { ok: false, error: String(e?.message || e), error_code: codigoDoErroDeEnvio(e), ...((e && e.extra) || {}) };
}
function responderErroDeEnvio(res, e, rotulo = 'send') {
  const corpo = corpoDeErro(e);
  log(`${rotulo} error`, corpo.error_code, corpo.error);
  res.status(500).json(corpo);
}
// Falhas que nao adianta esperar: sem sessao, precisa de QR, conta banida.
function verificarSessaoParaEnvio() {
  if (currentConnected()) return;
  if (desligando) throw erroComCodigo('not_connected', 'WhatsApp is not connected: the bridge is shutting down.');
  if (paradoMotivo === 'banned') throw erroComCodigo('banned', 'WhatsApp is not connected: WhatsApp blocked this account (403).');
  if (!sessaoSalva()) throw erroComCodigo('no_session', 'WhatsApp is not connected. Click CONNECT WHATSAPP and scan the QR Code first.');
  if (freshLoginRequired || lastQr || ['qr_expired', 'user_logged_out', 'multidevice_mismatch'].includes(paradoMotivo)) {
    throw erroComCodigo('needs_qr', 'WhatsApp is not connected. Scan the QR Code first.');
  }
}
// Sessao salva e reconexao a caminho (a queda de 50 em 50 min, por exemplo):
// espera ate 15 s pelo 'open' em vez de recusar na hora.
async function esperarConexaoParaEnvio(ms = 15000) {
  if (currentConnected()) return;
  verificarSessaoParaEnvio();
  if (reconectandoAgora()) {
    log('send waiting for reconnection', `${ms}ms`);
    const fim = Date.now() + ms;
    while (!currentConnected() && Date.now() < fim && reconectandoAgora()) await dormir(200);
    if (currentConnected()) return;
    verificarSessaoParaEnvio();
  }
  throw erroComCodigo('not_connected', 'WhatsApp is not connected (reconnecting). The message was NOT sent; try again in a few seconds.');
}
async function sendAndRegister(jid, payload, timeoutMs, label, fallbackText = '') {
  if (!currentConnected()) throw erroComCodigo('not_connected', 'WhatsApp is not connected. Click CONNECT WHATSAPP and scan the QR Code first.');
  // PRESENCA (13/10/2026): nada de presenceSubscribe + 'available' a cada
  // envio. 'available' e global, ninguem mandava 'unavailable' depois e o
  // celular do dono parava de notificar. No maximo "digitando" -> "parou".
  const s = sock;
  const digitando = Boolean(payload && payload.text);
  if (digitando) { try { await withTimeout(Promise.resolve(s.sendPresenceUpdate('composing', jid)), 2000, 'presence'); } catch (_) {} }
  let sent;
  try {
    sent = await withTimeout(s.sendMessage(jid, payload, { ephemeralExpiration: 0 }), timeoutMs, label);
  } finally {
    if (digitando) { try { Promise.resolve(s.sendPresenceUpdate('paused', jid)).catch(() => {}); } catch (_) {} }
  }
  if (sent && sent.key) {
    if (sent.message) guardarEnviada(sent.key, sent.message);
    // Registra exatamente a chave retornada pelo WhatsApp. Isso evita o Mark-XLVIII achar
    // que falhou e mantém a última mensagem enviada consistente para apagar/listar.
    rememberMessage({
      key: sent.key,
      message: sent.message || messageStubFromPayload(payload, fallbackText),
      messageTimestamp: sent.messageTimestamp || Math.floor(Date.now() / 1000),
      pushName: 'Você'
    });
    saveStatus({ last_event: 'message_sent', message: 'Mensagem enviada pelo WhatsApp e registrada localmente.', last_sent_key: sent.key });
  }
  return sent;
}

app.post('/send', async (req, res) => {
  const t0 = Date.now();
  try {
    // Ordem (13/10/2026): o que nao adianta esperar falha na hora; contato e
    // arquivo sao conferidos ANTES de esperar a reconexao.
    verificarSessaoParaEnvio();
    const to = req.body.to || req.body.receiver || req.body.contact || req.body.target; const message = String(req.body.message || req.body.message_text || req.body.text || req.body.body || req.body.content || req.body.conteudo || '').trim(); const type = String(req.body.type || 'text').toLowerCase(); const audioPath = req.body.audio_path; const jid = await resolveJid(to);
    let sent = null;
    let result = '';
    if (type === 'audio') {
      if (!audioPath || !fs.existsSync(audioPath)) throw new Error('Audio file not found.');
      const opus = await convertAudioToOpus(audioPath);
      const payload = { audio: { url: opus }, mimetype: 'audio/ogg; codecs=opus', ptt: true };
      await esperarConexaoParaEnvio();
      sent = await sendAndRegister(jid, payload, 30000, 'send audio', message || '[áudio]');
      result = `Áudio/voz enviado para ${nomeDoDestino(jid, to)} e registrado no histórico do WhatsApp.`;
    } else if (type === 'file' || type === 'media' || type === 'image' || type === 'video' || type === 'document') {
      const filePath = req.body.file_path || req.body.path;
      const caption = String(req.body.caption || message || '');
      const payload = mediaPayload(filePath, caption);
      await esperarConexaoParaEnvio();
      sent = await sendAndRegister(jid, payload, 120000, 'send file', caption || path.basename(String(filePath || 'arquivo')));
      result = `Arquivo enviado para ${nomeDoDestino(jid, to)} e registrado no histórico do WhatsApp.`;
    } else {
      if (!message) throw new Error('Message text is empty.');
      await esperarConexaoParaEnvio();
      sent = await sendAndRegister(jid, { text: message }, 45000, 'send text', message);
      result = `Texto enviado para ${nomeDoDestino(jid, to)} e registrado no histórico do WhatsApp.`;
    }
    const id = String(sent?.key?.id || '');
    log('send ok', jid, id, `${Date.now() - t0}ms`);
    return res.json({ ok:true, result, id, jid });
  } catch(e) { responderErroDeEnvio(res, e, 'send'); }
});
app.post('/delete-last-sent', async (req, res) => {
  try {
    verificarSessaoParaEnvio();
    const to = String(req.body.to || '').trim();
    const requested = Math.max(1, Math.min(50, Math.floor(Number(req.body.count || req.body.limit || 1)) || 1));
    const jid = to ? await resolveJid(to) : '';
    const signature = `${jid || '*'}|${requested}`;
    const now = Date.now();

    // Uma reconexão ou chamada repetida do modelo não pode apagar o lote seguinte.
    if (recentDeleteBatch.signature === signature && now - recentDeleteBatch.at < 6000 && recentDeleteBatch.response) {
      return res.json({ ...recentDeleteBatch.response, duplicate_suppressed: true });
    }

    const candidates = messages.slice().reverse().filter(m =>
      m.from_me && m.key && !m.deleted_requested_at && (!jid || m.jid === jid)
    );
    const selected = candidates.slice(0, requested);
    if (!selected.length) {
      throw new Error(to
        ? `Não encontrei mensagem enviada para ${to} que ainda possa ser apagada no histórico local.`
        : 'Não encontrei mensagem enviada que ainda possa ser apagada no histórico local.');
    }
    await esperarConexaoParaEnvio();

    const deleted = [];
    const failures = [];
    for (const msg of selected) {
      try {
        await withTimeout(sock.sendMessage(msg.jid, { delete: msg.key }), 10000, 'delete message');
        msg.deleted_requested_at = new Date().toISOString();
        deleted.push(msg);
      } catch (error) {
        failures.push({ id: msg.id || msg.key?.id || '', error: String(error?.message || error) });
      }
    }
    if (deleted.length) saveDb();
    if (!deleted.length) throw new Error(`Não consegui apagar as ${selected.length} mensagens encontradas.`);

    const targetText = to ? ` para ${to}` : '';
    let result = `Solicitei apagar ${deleted.length} ${deleted.length === 1 ? 'mensagem enviada' : 'mensagens enviadas'}${targetText}.`;
    if (selected.length < requested) {
      result += ` Encontrei somente ${selected.length} que ainda não tinham sido apagadas.`;
    }
    if (failures.length) {
      result += ` ${failures.length} ${failures.length === 1 ? 'mensagem falhou' : 'mensagens falharam'} durante a exclusão.`;
    }
    const response = {
      ok: true,
      result,
      requested_count: requested,
      found_count: selected.length,
      deleted_count: deleted.length,
      failed_count: failures.length,
      messages: deleted,
      failures,
    };
    recentDeleteBatch = { signature, at: Date.now(), response };
    res.json(response);
  }
  catch(e) { responderErroDeEnvio(res, e, 'delete'); }
});
app.post('/alias', async (req, res) => {
  try {
    const name = req.body.name || req.body.alias || req.body.contact || '';
    const phone = req.body.phone || req.body.number || req.body.jid || '';
    const a = saveAlias(name, phone);
    res.json({ ok: true, result: `Contato salvo: ${a.name} -> ${a.jid}`, alias: a });
  } catch(e) { res.status(500).json({ ok:false, error:String(e.message || e) }); }
});
app.get('/aliases', (_req, res) => { res.json({ ok:true, aliases:Object.values(aliases || {}), total:Object.keys(aliases || {}).length }); });
app.post('/auto-alias-from-messages', (_req, res) => {
  let count = 0;
  for (const m of (messages || [])) {
    if (m?.is_group || isGroupJid(m?.jid)) continue;
    const before = Object.keys(aliases).length;
    autoAliasFromName(m.name, m.sender_jid || m.jid, 'private_history');
    autoAliasFromName(m.chat_name, m.jid, 'private_history');
    if (Object.keys(aliases).length > before) count++;
  }
  saveDb();
  res.json({ ok:true, result:`Aliases automáticos atualizados a partir das mensagens: ${count}`, aliases:Object.values(aliases || {}), total:Object.keys(aliases || {}).length });
});

app.post('/groups/leave', async (req, res) => {
  try {
    if (!currentConnected()) throw new Error('WhatsApp is not connected.');
    const to = String(req.body.to || req.body.group || req.body.name || '').trim();
    const confirmRaw = req.body.confirm;
    const confirm = confirmRaw === true || String(confirmRaw || '').toLowerCase() === 'true' || String(confirmRaw || '').toLowerCase() === 'sim' || String(confirmRaw || '').toLowerCase() === 'confirmo';
    const g = await resolveGroupJid(to);
    if (!String(g.jid || '').endsWith('@g.us')) throw new Error('O destino encontrado não é um grupo do WhatsApp.');
    if (!confirm) {
      pendingLeaveGroup = { jid: g.jid, name: g.name, requested_at: new Date().toISOString() };
      saveDb();
      saveStatus({ last_event:'leave_group_pending', message:`Confirmação pendente para sair do grupo ${g.name}.` });
      return res.json({ ok:true, needs_confirmation:true, group:g, result:`Confirma que deseja sair do grupo "${g.name}"? Responda confirmando para eu sair.` });
    }
    await withTimeout(sock.groupLeave(g.jid), 15000, 'groupLeave');
    delete groups[g.jid];
    delete chats[g.jid];
    pendingLeaveGroup = null;
    saveDb();
    saveStatus({ last_event:'left_group', message:`Sai do grupo ${g.name}.` });
    return res.json({ ok:true, result:`Saí do grupo "${g.name}" com sucesso.`, group:g });
  } catch(e) { log('leave group error', e?.stack || e); res.status(500).json({ ok:false, error:String(e.message || e) }); }
});


app.post('/alerts/watch', async (req, res) => {
  try {
    let mode = String(req.body.mode || req.body.action || '').toLowerCase().trim();
    const contact = String(req.body.contact || req.body.to || req.body.name || req.body.group || '').trim();
    let result = '';
    if (['off','stop','disable','desativar','parar'].includes(mode)) result = stopWatch();
    else if (['private','privado','privados','contatos','somente_privado','somente_privados','contacts_only'].includes(mode)) result = setWatchPrivateOnly();
    else if (['groups','group_only','grupos','somente_grupos','grupo_todos'].includes(mode)) result = setWatchGroupsOnly();
    else if (['group','grupo','specific_group','grupo_especifico'].includes(mode)) result = setWatchGroup(contact);
    else if (['contact','contacts','contato','specific_contact','contato_especifico'].includes(mode)) result = setWatchContact(contact);
    else if (contact) {
      // If user says "me avise sobre o grupo X", route to group; otherwise contact.
      if (mode.includes('grupo')) result = setWatchGroup(contact); else result = setWatchContact(contact);
    }
    else result = setWatchAny();
    saveStatus({ last_event:'watch_messages', message:result });
    res.json({ ok:true, result, watch:watchConfig });
  } catch(e) { res.status(500).json({ ok:false, error:String(e.message || e) }); }
});
app.get('/alerts/status', (_req, res) => res.json({ ok:true, watch:watchConfig, queue:alertQueue.length }));
app.get('/alerts/poll', (req, res) => {
  const limit = Math.min(Number(req.query.limit || 20), 100);
  const items = alertQueue.splice(0, limit);
  // So grava o banco quando algo saiu da fila (13/10/2026). Era a cada poll:
  // o banco de 2,7 MB regravado a cada 2,5 s sem nada novo.
  if (items.length) saveDb();
  res.json({ ok:true, alerts:items, total:items.length, watch:watchConfig });
});


app.get('/agent/poll', (req, res) => {
  const limit = Math.min(Number(req.query.limit || 20), 100);
  // Itens com mais de 24 h saem da fila antes (13/10/2026). Ver podarFilas.
  const tamanhoAntes = agentQueue.length;
  podarFilas();
  const items = agentQueue.splice(0, limit);
  const tirouDaFila = items.length > 0 || agentQueue.length !== tamanhoAntes;
  // Fallback: entrega também mensagens recentes que podem ter ficado fora da fila.
  // O Python deduplica e filtra pelo horário de ativação do agente.
  try {
    const recent = (messages || []).slice(-80).filter(m => m && !m.from_me && isMeaningfulMessageItem(m));
    for (const m of recent) {
      if (items.length >= limit) break;
      const isGroup = Boolean(m.is_group || String(m.jid || '').endsWith('@g.us'));
      items.push({
        id: `${m.jid || ''}:${m.sender_jid || ''}:${m.id || m.timestamp || ''}`,
        name: m.name || m.sender_name || 'contato',
        chat_name: m.chat_name || m.name || m.jid || 'conversa',
        jid: m.jid,
        sender_jid: m.sender_jid,
        text: String(m.text || '').slice(0, 1200),
        is_group: isGroup,
        chat_type: isGroup ? 'group' : 'private',
        type: m.type || 'message',
        media_kind: m.media_kind || '',
        media_path: m.media_path || '',
        timestamp: m.timestamp || Math.floor(Date.now()/1000),
        created_at: new Date().toISOString(),
      });
    }
  } catch (_) {}
  // O complemento acima nao mexe na fila: so grava se algo saiu dela.
  if (tirouDaFila) saveDb();
  res.json({ ok:true, messages:items, total:items.length });
});

app.post('/logout', async (_req, res) => {
  log('Manual WhatsApp logout requested. Closing linked device and local session.');
  manualLogoutInProgress = true;
  let logoutError = '';
  try {
    if (sock && currentConnected()) {
      await withTimeout(sock.logout(), 20000, 'logout');
    }
  } catch (e) {
    logoutError = String(e.message || e);
    log('logout command failed/timeout; cleaning local session anyway', logoutError);
  }
  encerrarConexaoAtual();
  try { connected = false; lastQr = ''; freshLoginRequired = true; lastDisconnectReason = 'user_logged_out'; lastEvent = 'manual_logout'; } catch (_) {}
  // Fica parada ate pedirem conexao (/start ou /reset), como antes (13/10/2026).
  paradoMotivo = 'user_logged_out';
  await apagarAuth();
  try { if (fs.existsSync(QR_FILE)) fs.unlinkSync(QR_FILE); } catch (_) {}
  try { if (fs.existsSync(STATUS_FILE)) fs.unlinkSync(STATUS_FILE); } catch (_) {}
  pendingLeaveGroup = null;
  saveDb();
  const msg = logoutError
    ? `WhatsApp desconectado localmente e sessão limpa. Aviso: o comando de logout real retornou: ${logoutError}. Se ainda aparecer no celular, remova em WhatsApp > Aparelhos conectados.`
    : 'WhatsApp desconectado completamente. Sessão encerrada no Jarvis e no aparelho conectado; será necessário escanear um novo QR Code.';
  saveStatus({ connected:false, has_qr:false, message:msg, disconnect_reason:lastDisconnectReason, fresh_login_required:true, last_event:'manual_logout' });
  res.json({ ok:true, result: msg, real_logout: !logoutError, warning: logoutError });
});
app.post('/disconnect', async (req, res) => {
  req.url = '/logout';
  return app._router.handle(req, res);
});
// PORTA OCUPADA = SAIR (13/10/2026). O segundo node que nao conseguia a porta
// ficava vivo (o erro virava "uncaught") e o timer dele gravava connected:false
// no MESMO status.json a cada 2,5 s, por cima da ponte verdadeira. Agora sai
// com 3, e o timer do status so comeca depois que a porta e nossa.
function iniciarRegravacaoDoStatus() {
  setInterval(() => {
    try {
      if (desligando) return;
      const cc = currentConnected();
      saveStatus({ connected: cc, has_qr: Boolean(lastQr && !cc && fs.existsSync(QR_FILE)), message: mensagemDeEstado(), disconnect_reason: lastDisconnectReason, last_event: cc ? 'connected' : lastEvent });
    } catch (_) {}
  }, 2500);
}
const servidorHttp = app.listen(PORT, '127.0.0.1', () => {
  log(`Bridge running at http://127.0.0.1:${PORT}`, { pid: process.pid, version: VERSION });
  iniciarRegravacaoDoStatus();
  const comSessao = sessaoSalva();
  saveStatus({ connected:false, has_qr:false, message: comSessao ? 'Reconectando ao WhatsApp...' : 'Servidor local WhatsApp iniciado. Preparando QR Code...', last_event:'server_listening' });
  start({ fresh: false }).catch(e => log('Start failed', e?.stack || e));
});
servidorHttp.on('error', (e) => {
  log('listen failed', e?.code || '', e?.message || e);
  sairCom(e && e.code === 'EADDRINUSE' ? 3 : 1);
});
