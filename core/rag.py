"""
RAG local — indexa e busca nos documentos do próprio computador.

Sem nuvem, sem chave de API, sem dependência nova: o índice é um BM25 (o mesmo
algoritmo de ranking usado por buscadores) montado em memória a partir dos
arquivos de texto que o usuário apontar. A ideia é simples:

  • indexar()  varre as pastas, quebra cada arquivo em trechos e guarda o texto;
  • buscar()   responde "onde está aquilo que eu falei de X?" com os trechos
               mais relevantes e o caminho do arquivo de cada um;
  • status()   diz o que está indexado, quando foi atualizado e o que falhou.

O índice fica em memory/rag_index.json. Cada arquivo é reindexado apenas quando
muda (data de modificação + tamanho), então rodar indexar() de novo é barato e
serve como "atualizar o índice".

Formatos suportados sem instalar nada: .txt, .md, .csv, .log, .json, .ini e
.docx (lido por dentro como ZIP+XML). .pdf entra automaticamente se o pypdf
estiver instalado — sem ele, o arquivo é anotado como "precisa do pypdf" em vez
de ser silenciosamente ignorado.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
INDEX_FILE = _BASE / "memory" / "rag_index.json"

# Onde procurar quando o usuário não diz a pasta (nomes em português e inglês).
_DEFAULT_FOLDERS = ("Documentos", "Documents", "Downloads", "Desktop",
                    "Área de Trabalho", "OneDrive")

_SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", ".cache",
    "AppData", "Windows", "Program Files", "Program Files (x86)",
    "site-packages", "dist-packages", ".idea", ".vscode",
}
_TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".log", ".json", ".ini",
             ".py", ".js", ".html", ".css", ".sql", ".yaml", ".yml", ".bat", ".sh"}
_MAX_FILE_BYTES = 5 * 1024 * 1024      # 5 MB por arquivo
_MAX_FILES = 4000                       # teto de arquivos por indexação
_CHUNK_CHARS = 1200                     # ~300 palavras por trecho
_CHUNK_OVERLAP = 200

_STOP = set("""a o as os um uma uns umas de do da dos das em no na nos nas por para com sem
que se e ou mas como quando onde qual quais quem cujo cuja é são foi ser está estão estar
já não sim muito mais menos isso isto aquilo eu você vocês ele ela eles elas meu minha seu
sua nosso nossa the of and to in on at for with is are was were be been the a an""".split())


# ── texto ────────────────────────────────────────────────────────────────────
def _fold(s: str) -> str:
    """minúsculas e sem acento, para 'consulta' casar com 'consulta'."""
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")


def _tokens(s: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(_fold(s)) if t not in _STOP]


def _read_text(path: Path) -> str | None:
    """Texto do arquivo, ou None quando o formato não é suportado."""
    ext = path.suffix.lower()
    if ext in _TEXT_EXT:
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
            except OSError:
                return None
        return None
    if ext == ".docx":
        try:
            with zipfile.ZipFile(path) as zf:
                xml = zf.read("word/document.xml").decode("utf-8", "replace")
            xml = re.sub(r"</w:p>", "\n", xml)
            return re.sub(r"<[^>]+>", "", xml)
        except Exception:
            return None
    if ext == ".pdf":
        try:
            from pypdf import PdfReader       # opcional
        except Exception:
            return "\x00NEED_PYPDF\x00"
        try:
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)
        except Exception:
            return None
    return None


def _chunks(text: str) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not text:
        return []
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + _CHUNK_CHARS)
        if end < len(text):
            cut = text.rfind("\n\n", start + _CHUNK_CHARS // 3, end)
            if cut > 0:
                end = cut
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        if end >= len(text):
            break
        start = max(end - _CHUNK_OVERLAP, start + 1)
    return out


# ── índice ───────────────────────────────────────────────────────────────────
def _load() -> dict:
    try:
        d = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("docs"), dict):
            return d
    except Exception:
        pass
    return {"docs": {}, "updated": 0.0, "errors": []}


def _save(idx: dict) -> None:
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = INDEX_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, INDEX_FILE)


def _candidate_folders(pastas: str | None) -> list[Path]:
    if pastas:
        parts = [p.strip().strip('"') for p in re.split(r"[;|]", pastas) if p.strip()]
        return [Path(p).expanduser() for p in parts]
    home = Path.home()
    out = []
    for name in _DEFAULT_FOLDERS:
        p = home / name
        if p.is_dir() and p not in out:
            out.append(p)
    return out or [home]


def index_folders(pastas: str | None = None, force: bool = False) -> str:
    """Indexa (ou atualiza) as pastas. Devolve um resumo legível."""
    t0 = time.time()
    idx = _load()
    docs: dict = idx["docs"]
    pastas_alvo = _candidate_folders(pastas)

    novos = atualizados = inalterados = 0
    erros: list[str] = []
    vistos: set[str] = set()

    for base in pastas_alvo:
        if not base.exists():
            erros.append(f"pasta não encontrada: {base}")
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
            for nome in files:
                if len(vistos) >= _MAX_FILES:
                    break
                path = Path(root) / nome
                try:
                    st = path.stat()
                except OSError:
                    continue
                if st.st_size > _MAX_FILE_BYTES:
                    continue
                key = str(path)
                vistos.add(key)
                antigo = docs.get(key)
                if (antigo and not force
                        and antigo.get("mtime") == st.st_mtime
                        and antigo.get("size") == st.st_size):
                    inalterados += 1
                    continue

                texto = _read_text(path)
                if texto is None:
                    continue
                if texto == "\x00NEED_PYPDF\x00":
                    erros.append(f"{path.name}: instale 'pypdf' para ler PDFs")
                    continue
                pedacos = _chunks(texto)
                if not pedacos:
                    continue
                docs[key] = {
                    "mtime": st.st_mtime,
                    "size": st.st_size,
                    "chunks": pedacos,
                    "tokens": [Counter(_tokens(c)) for c in pedacos],
                    "len": [len(_tokens(c)) for c in pedacos],
                }
                if antigo:
                    atualizados += 1
                else:
                    novos += 1

    # remove do índice o que sumiu do disco
    removidos = 0
    for key in list(docs):
        if key not in vistos and not Path(key).exists():
            docs.pop(key, None)
            removidos += 1

    idx["updated"] = time.time()
    idx["errors"] = erros[:20]
    _save(idx)

    n_chunks = sum(len(d["chunks"]) for d in docs.values())
    partes = [f"{len(docs)} arquivo(s), {n_chunks} trecho(s) no índice"]
    if novos:
        partes.append(f"{novos} novo(s)")
    if atualizados:
        partes.append(f"{atualizados} atualizado(s)")
    if removidos:
        partes.append(f"{removidos} removido(s)")
    if inalterados:
        partes.append(f"{inalterados} sem mudança")
    seg = time.time() - t0
    msg = "Indexei " + ", ".join(partes) + f" em {seg:.1f}s."
    if erros:
        msg += " Avisos: " + "; ".join(erros[:3]) + ("…" if len(erros) > 3 else "")
    if not docs:
        msg += " Nenhum documento encontrado — diga o caminho da pasta para eu indexar."
    return msg


def search(consulta: str, k: int = 5) -> str:
    """BM25 sobre os trechos indexados. Devolve os melhores com o caminho."""
    idx = _load()
    docs: dict = idx["docs"]
    termos = _tokens(consulta)
    if not termos:
        return "Diga o que devo procurar nos seus documentos."
    if not docs:
        return "Ainda não indexei nada. Peça para eu indexar seus documentos primeiro."

    total_chunks = sum(len(d["chunks"]) for d in docs.values())
    df = Counter()
    for d in docs.values():
        for tk in d["tokens"]:
            for t in set(tk) & set(termos):
                df[t] += 1
    avgdl = (sum(sum(d["len"]) for d in docs.values()) / total_chunks) if total_chunks else 1.0
    k1, b = 1.5, 0.75

    hits: list[tuple[float, str, int, str]] = []
    for caminho, d in docs.items():
        for i, tk in enumerate(d["tokens"]):
            score = 0.0
            dl = d["len"][i] or 1
            for t in termos:
                tf = tk.get(t, 0)
                if not tf:
                    continue
                idf = math.log(1 + (total_chunks - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
            if score > 0:
                hits.append((score, caminho, i, d["chunks"][i]))

    hits.sort(key=lambda h: h[0], reverse=True)
    if not hits:
        return f"Nada encontrado para '{consulta}' nos {len(docs)} arquivos indexados."

    linhas = [f"Encontrei {len(hits)} trecho(s); os melhores:"]
    for score, caminho, i, trecho in hits[:max(1, min(10, k))]:
        resumo = re.sub(r"\s+", " ", trecho).strip()
        if len(resumo) > 400:
            resumo = resumo[:400] + "…"
        linhas.append(f"\n• {Path(caminho).name} (trecho {i + 1}) — {caminho}\n  {resumo}")
    return "\n".join(linhas)


def status() -> str:
    idx = _load()
    docs = idx.get("docs", {})
    if not docs:
        return "O índice de documentos está vazio. Peça para eu indexar uma pasta."
    quando = time.strftime("%d/%m/%Y %H:%M", time.localtime(idx.get("updated") or 0))
    chunks = sum(len(d["chunks"]) for d in docs.values())
    por_tipo = Counter(Path(c).suffix.lower() or "(sem extensão)" for c in docs)
    tipos = ", ".join(f"{ext}: {n}" for ext, n in por_tipo.most_common(6))
    return (f"{len(docs)} arquivo(s) e {chunks} trecho(s) indexados, atualizado em {quando}. "
            f"Tipos: {tipos}.")


def forget_all() -> str:
    """Apaga o índice (os arquivos originais não são tocados)."""
    try:
        INDEX_FILE.unlink()
    except FileNotFoundError:
        return "O índice já estava vazio."
    except OSError as e:
        return f"Não consegui apagar o índice: {e}"
    return "Índice apagado. Os seus arquivos continuam intactos."
