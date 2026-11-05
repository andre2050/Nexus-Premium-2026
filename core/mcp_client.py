"""
Cliente MCP — liga o JARVIS a servidores MCP (Model Context Protocol).

MCP é o padrão aberto que expõe dados e ferramentas a uma IA de forma
padronizada: um servidor MCP declara "estas são as ferramentas que eu tenho" e o
assistente passa a poder chamá-las. É assim que se pluga um repositório de
código, um banco, um sistema da empresa ou uma API sem escrever uma ação nova
para cada um.

Nada aqui é descoberto sozinho: só conversa com os servidores listados em
config/mcp_servers.json. O comando é passado como LISTA (nunca por shell), com
timeout curto, e o processo é encerrado ao final de cada chamada.

Formato do arquivo (crie com este exemplo):

    {
      "servers": {
        "arquivos": {
          "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "C:/Users/voce/Documentos"],
          "env": {},
          "timeout": 25
        },
        "meu_banco": {
          "command": ["python", "C:/caminho/meu_servidor_mcp.py"],
          "timeout": 30
        }
      }
    }

Transporte suportado: stdio com JSON por linha (o transporte padrão do MCP).
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
CONFIG_FILE = _BASE / "config" / "mcp_servers.json"
_PROTOCOL = "2024-11-05"
_MAX_OUTPUT = 12000          # caracteres devolvidos ao modelo


def _load_cfg() -> dict:
    try:
        d = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        srv = d.get("servers")
        return srv if isinstance(srv, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def servers() -> dict:
    return _load_cfg()


class _Process:
    """Um servidor MCP rodando, falando JSON-RPC por linha no stdin/stdout."""

    def __init__(self, nome: str, cfg: dict):
        self.nome = nome
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self._q: queue.Queue = queue.Queue()
        self._next_id = 0
        self._lock = threading.Lock()
        self.timeout = float(cfg.get("timeout") or 25)

    # -- ciclo de vida -------------------------------------------------------
    def start(self) -> None:
        cmd = self.cfg.get("command")
        if not isinstance(cmd, (list, tuple)) or not cmd:
            raise ValueError(f"servidor '{self.nome}': 'command' precisa ser uma lista")
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in (self.cfg.get("env") or {}).items()})
        self.proc = subprocess.Popen(
            [str(c) for c in cmd],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
        )
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._q.put(json.loads(line))
            except json.JSONDecodeError:
                continue            # linha de log do servidor, não JSON-RPC

    def stop(self) -> None:
        if not self.proc:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        finally:
            self.proc = None

    # -- JSON-RPC ------------------------------------------------------------
    def notify(self, method: str, params: dict | None = None) -> None:
        assert self.proc and self.proc.stdin
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict | None = None):
        with self._lock:
            self._next_id += 1
            rid = self._next_id
            assert self.proc and self.proc.stdin
            msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()

            limite = time.monotonic() + self.timeout
            while True:
                resta = limite - time.monotonic()
                if resta <= 0:
                    raise TimeoutError(f"'{self.nome}' não respondeu em {self.timeout:.0f}s")
                try:
                    data = self._q.get(timeout=min(resta, 0.5))
                except queue.Empty:
                    if self.proc.poll() is not None:
                        raise RuntimeError(f"'{self.nome}' encerrou (código {self.proc.returncode})")
                    continue
                if data.get("id") == rid:
                    if "error" in data:
                        err = data["error"]
                        raise RuntimeError(err.get("message") if isinstance(err, dict) else str(err))
                    return data.get("result")

    def handshake(self) -> None:
        self.request("initialize", {
            "protocolVersion": _PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "NEXUS Premium 2026", "version": "3.1.0"},
        })
        self.notify("notifications/initialized")


def _with_server(nome: str, fn):
    cfg = _load_cfg().get(nome)
    if not cfg:
        disponiveis = ", ".join(_load_cfg()) or "nenhum"
        return f"Servidor MCP '{nome}' não está configurado. Configurados: {disponiveis}."
    p = _Process(nome, cfg)
    try:
        p.start()
        p.handshake()
        return fn(p)
    except Exception as e:
        return f"Falha ao falar com o servidor MCP '{nome}': {e}"
    finally:
        p.stop()


def list_tools(nome: str) -> str:
    """Lista as ferramentas que um servidor MCP oferece."""
    def _run(p: _Process):
        res = p.request("tools/list", {}) or {}
        tools = res.get("tools") or []
        if not tools:
            return f"O servidor '{nome}' não declarou ferramentas."
        linhas = [f"Servidor '{nome}' — {len(tools)} ferramenta(s):"]
        for t in tools[:40]:
            desc = (t.get("description") or "").strip().replace("\n", " ")
            if len(desc) > 160:
                desc = desc[:160] + "…"
            linhas.append(f"• {t.get('name')}: {desc}")
        return "\n".join(linhas)
    return _with_server(nome, _run)


def call_tool(nome: str, ferramenta: str, argumentos: dict | None = None) -> str:
    """Chama uma ferramenta de um servidor MCP e devolve o texto do resultado."""
    if not ferramenta:
        return "Diga qual ferramenta do servidor MCP devo chamar (veja com 'listar')."

    def _run(p: _Process):
        res = p.request("tools/call", {"name": ferramenta,
                                      "arguments": argumentos or {}}) or {}
        partes: list[str] = []
        for item in (res.get("content") or []):
            if isinstance(item, dict):
                if item.get("type") == "text":
                    partes.append(str(item.get("text", "")))
                else:
                    partes.append(f"[{item.get('type', 'conteúdo')}]")
        texto = "\n".join(x for x in partes if x).strip() or json.dumps(res, ensure_ascii=False)
        if res.get("isError"):
            texto = "Erro do servidor: " + texto
        return texto[:_MAX_OUTPUT]

    return _with_server(nome, _run)


def status() -> str:
    srvs = _load_cfg()
    if not srvs:
        return ("Nenhum servidor MCP configurado. Crie config/mcp_servers.json com "
                "{\"servers\": {\"nome\": {\"command\": [\"comando\", \"args\"]}}}.")
    linhas = [f"{len(srvs)} servidor(es) MCP configurado(s):"]
    for nome, cfg in srvs.items():
        cmd = cfg.get("command")
        resumo = " ".join(str(c) for c in cmd) if isinstance(cmd, (list, tuple)) else "comando inválido"
        linhas.append(f"• {nome}: {resumo[:120]}")
    return "\n".join(linhas)
