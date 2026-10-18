"""ROTEIROS: criação de roteiros + a "inteligência" do roteirista + organização dos vídeos por código de ID.

Tudo em arquivos JSON na pasta `roteiros/` (FORA do git — o repositório é público e roteiro é conteúdo do usuário):
  roteiros/roteiros.json      lista de vídeos/roteiros, cada um com um código (V001, V002…) que acompanha o vídeo
                               da ideia à publicação: ideia → roteiro → gravado → editado → publicado
  roteiros/inteligencia.json  o "cérebro": seções de conhecimento (público, tom de voz, estruturas, regras…) e uma
                               caixa de entrada de ensinamentos crus que o usuário vai mandando
  roteiros/drive.json         a pasta do Google Drive onde os vídeos ficam organizados pelos códigos
"""
import json
import os
import subprocess
import re
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "roteiros"
DB = DIR / "roteiros.json"
BRAIN = DIR / "inteligencia.json"
DRIVE = DIR / "drive.json"
_lock = threading.Lock()

STATUS = ["ideia", "rascunho", "aprovado", "gravado", "editado", "publicado"]
OLD_STATUS = {"roteiro": "aprovado"}
PREFIX = "V"

# esqueleto inicial do cérebro: o usuário (e o Claude Code) vão preenchendo
DEFAULT_SECTIONS = [
    ("publico", "Público e avatar", "Para quem são os vídeos: quem é, o que quer, o que teme, como fala."),
    ("tom", "Tom de voz", "Como você fala: palavras que usa, palavras que evita, ritmo, humor, nível de formalidade."),
    ("ganchos", "Ganchos (hooks)", "Modelos de abertura que prendem nos 3 primeiros segundos."),
    ("estruturas", "Estruturas de roteiro", "Esqueletos que funcionam (ex.: gancho → problema → virada → prova → CTA)."),
    ("ctas", "Chamadas para ação", "Como você fecha os vídeos e o que pede para a pessoa fazer."),
    ("regras", "Regras e proibições", "O que nunca pode aparecer num roteiro seu."),
    ("exemplos", "Roteiros que funcionaram", "Vídeos seus (ou de referência) que performaram — e por quê."),
]


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path, data):
    DIR.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ------------------------------------------------------------------ roteiros (com código de ID)
def load():
    items = _read(DB, [])
    for r in items:
        r["status"] = OLD_STATUS.get(r.get("status"), r.get("status") or "ideia")
    return items


def _num(code):
    m = re.match(rf"^{PREFIX}(\d+)$", code or "")
    return int(m.group(1)) if m else 0


def next_code(items=None):
    items = load() if items is None else items
    return f"{PREFIX}{max([_num(r['code']) for r in items] + [0]) + 1:03d}"


def add(data=None):
    data = data or {}
    with _lock:
        items = load()
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        r = {"code": next_code(items), "title": (data.get("title") or "").strip() or "Sem título",
             "status": data.get("status") if data.get("status") in STATUS else "ideia",
             "hook": data.get("hook", ""), "body": data.get("body", ""), "cta": data.get("cta", ""),
             "notes": data.get("notes", ""), "tags": data.get("tags") or [],
             "project": data.get("project"), "drive": data.get("drive", ""),
             "idea": data.get("idea"), "angle": data.get("angle", ""), "structure": data.get("structure", ""),
             "caption": data.get("caption", ""), "formato": data.get("formato", ""), "ativos": data.get("ativos") or [], "moral": data.get("moral", ""),
             "created": now, "updated": now}
        items.append(r)
        _write(DB, items)
        return r


EDITABLE = {"title", "status", "hook", "body", "cta", "notes", "tags", "project", "drive", "doc", "doc_name", "imported",
            "idea", "angle", "structure", "feedback", "archived", "caption", "formato", "ativos", "moral", "pushed"}


def edit(code, changes):
    with _lock:
        items = load()
        r = next((x for x in items if x["code"] == code), None)
        if not r:
            raise KeyError(code)
        for k, v in changes.items():
            if k in EDITABLE and not (k == "status" and v not in STATUS):
                r[k] = v
        r["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _write(DB, items)
        return r


def remove(code):
    with _lock:
        items = load()
        if not any(x["code"] == code for x in items):
            raise KeyError(code)
        _write(DB, [x for x in items if x["code"] != code])


# ------------------------------------------------------------------ inteligência (o cérebro do roteirista)
def brain():
    b = _read(BRAIN, None)
    if b is None:
        b = {"sections": [{"id": i, "title": t, "hint": h, "body": ""} for i, t, h in DEFAULT_SECTIONS], "inbox": []}
        _write(BRAIN, b)
    return b


def brain_edit(section_id, body=None, title=None):
    with _lock:
        b = brain()
        s = next((x for x in b["sections"] if x["id"] == section_id), None)
        if not s:
            s = {"id": section_id, "title": title or section_id, "hint": "", "body": ""}
            b["sections"].append(s)
        if body is not None:
            s["body"] = body
        if title:
            s["title"] = title
        _write(BRAIN, b)
        return b


def brain_add_section(title):
    sid = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:30] or uuid.uuid4().hex[:6]
    return brain_edit(sid, body="", title=title.strip())


def brain_remove_section(section_id):
    with _lock:
        b = brain()
        b["sections"] = [x for x in b["sections"] if x["id"] != section_id]
        _write(BRAIN, b)
        return b


def teach(text):
    """Ensinamento cru (caixa de entrada): o usuário manda, o Claude Code organiza nas seções depois."""
    with _lock:
        b = brain()
        b["inbox"].append({"id": uuid.uuid4().hex[:8], "text": text.strip(),
                           "added": time.strftime("%Y-%m-%dT%H:%M:%S"), "done": False})
        _write(BRAIN, b)
        return b


def inbox_edit(item_id, done=None, delete=False):
    with _lock:
        b = brain()
        if delete:
            b["inbox"] = [x for x in b["inbox"] if x["id"] != item_id]
        else:
            for x in b["inbox"]:
                if x["id"] == item_id and done is not None:
                    x["done"] = bool(done)
        _write(BRAIN, b)
        return b


def brain_markdown():
    """O cérebro inteiro em texto (para o Claude Code ler antes de escrever um roteiro)."""
    b = brain()
    out = ["# Inteligência de roteiros", ""]
    for s in b["sections"]:
        out += [f"## {s['title']}", s["body"].strip() or "_(vazio)_", ""]
    pend = [x for x in b["inbox"] if not x["done"]]
    if pend:
        out += ["## Caixa de entrada (ainda não organizado)"] + [f"- {x['text']}" for x in pend] + [""]
    return "\n".join(out)


# ------------------------------------------------------------------ Google Drive
def drive():
    return _read(DRIVE, {"url": "", "folder_id": "", "local_path": ""})


def set_drive(url=None, local_path=None):
    d = drive()
    if url is not None:
        d["url"] = url.strip()
        m = re.search(r"/folders/([\w-]+)", d["url"])
        d["folder_id"] = m.group(1) if m else ""
    if local_path is not None:
        d["local_path"] = local_path.strip()
    _write(DRIVE, d)
    return status_drive(d)


def find_local_drive():
    """Pasta do "Google Drive para computador", se estiver instalado (é por ela que os vídeos são organizados)."""
    base = Path.home() / "Library" / "CloudStorage"
    return [str(p) for p in base.glob("GoogleDrive-*")] if base.exists() else []


def status_drive(d=None):
    d = d or drive()
    local = d.get("local_path") and Path(d["local_path"]).exists()
    return {**d, "local_ok": bool(local), "candidates": find_local_drive()}


# ------------------------------------------------------------------ pastas por código no Drive
SUBFOLDERS = ["bruto", "apoio", "final"]


def _safe(name):
    return re.sub(r'[/:\\*?"<>|]+', "-", name).strip()[:60]


def folder_name(r):
    t = r.get("title") or ""
    return f"{r['code']} — {_safe(t)}" if t and t != "Sem título" else r["code"]


def find_folder(code, base=None):
    base = Path(base or drive().get("local_path") or "")
    if not base.is_dir():
        return None
    return next((p for p in sorted(base.iterdir()) if p.is_dir() and re.match(rf"^{re.escape(code)}(\b|\s|$)", p.name)), None)


def ensure_folder(code):
    """Pasta do vídeo dentro da pasta do Drive (cria se faltar; renomeia se o título mudou). Só mexe dentro dela."""
    d = drive()
    base = Path(d.get("local_path") or "")
    if not base.is_dir():
        raise RuntimeError("A pasta do Google Drive não está conectada neste computador.")
    r = next((x for x in load() if x["code"] == code), None)
    if not r:
        raise KeyError(code)
    want = base / folder_name(r)
    cur = find_folder(code, base)
    if cur and cur != want and not want.exists():
        cur.rename(want)
        cur = want
    cur = cur or want
    cur.mkdir(exist_ok=True)
    for s in SUBFOLDERS:
        (cur / s).mkdir(exist_ok=True)
    return cur


def by_project(pid):
    return next((x for x in load() if x.get("project") == pid), None)


def deliver_export(pid, mp4, credits=None):
    """Exportou um vídeo ligado a um roteiro: copia o MP4 (e os créditos) para <pasta do código>/final/
    e marca o roteiro como "editado". Devolve o caminho no Drive (ou None)."""
    import shutil
    r = by_project(pid)
    if not r or not drive().get("local_path"):
        return None
    final = ensure_folder(r["code"]) / "final"
    dst = final / f"{r['code']} — {_safe(r['title'])}{Path(mp4).suffix}"
    # Google Drive para Mac: sobrescrever um MP4 grande no lugar fazia o arquivo sumir, e gravar com nome
    # temporário + renomear deixava o MP4 sem subir (sem "item-id"). O que funciona: apaga a versão antiga,
    # espera, copia limpo e aguarda o Drive registrar o arquivo (xattr com o id do Drive)
    import time
    if dst.exists():
        dst.unlink()
        time.sleep(3)
    shutil.copyfile(mp4, dst)
    for _ in range(24):                     # até ~2 min
        if _drive_item_id(dst):
            break
        time.sleep(5)
    if credits and Path(credits).exists():
        shutil.copyfile(credits, dst.with_suffix(".creditos.txt"))
    if STATUS.index(r["status"]) < STATUS.index("editado"):
        edit(r["code"], {"status": "editado"})
    return str(dst)


# ------------------------------------------------------------------ importar o roteiro do Google Docs
HEADS = {"moral": r"moral", "hook": r"hook|gancho", "body": r"body|roteiro|desenvolvimento|corpo",
         "cta": r"cta|chamada(?: para a[çc][ãa]o)?|call to action"}


def split_script(text):
    """Separa "HOOK: … BODY: … CTA: …" (ou GANCHO/ROTEIRO/CHAMADA) nos campos; sem cabeçalhos, tudo vira roteiro."""
    text = text.replace("﻿", "").replace("\r", "")
    pat = re.compile(r"^\s*(" + "|".join(f"(?P<{k}>{v})" for k, v in HEADS.items()) + r")\s*:\s*", re.I | re.M)
    marks = [(m.start(), m.end(), next(k for k in HEADS if m.group(k))) for m in pat.finditer(text)]
    if not marks:
        return {"body": text.strip()}
    out = {}
    for n, (a, b, k) in enumerate(marks):
        end = marks[n + 1][0] if n + 1 < len(marks) else len(text)
        chunk = re.sub(r"\n{3,}", "\n\n", text[b:end]).strip()
        out[k] = (out.get(k, "") + "\n\n" + chunk).strip() if k in out else chunk
    return out


def gdocs_in(code):
    f = find_folder(code)
    return sorted(f.glob("*.gdoc")) if f else []


TEXT_FIELDS = ("moral", "hook", "body", "cta", "caption")


def snapshot(code, motivo):
    """Guarda a versão atual do texto antes de ser substituída (últimas 15), para dar para voltar."""
    with _lock:
        items = load()
        r = next((x for x in items if x["code"] == code), None)
        if not r:
            raise KeyError(code)
        v = {k: r.get(k, "") for k in TEXT_FIELDS}
        if any(v.values()):
            v.update(when=time.strftime("%Y-%m-%dT%H:%M:%S"), motivo=motivo)
            r["versions"] = ([v] + (r.get("versions") or []))[:15]
            _write(DB, items)


def restore_version(code, idx):
    r = next((x for x in load() if x["code"] == code), None)
    if not r or idx >= len(r.get("versions") or []):
        raise KeyError(code)
    v = r["versions"][idx]
    snapshot(code, "antes de restaurar uma versão")
    return edit(code, {k: v.get(k, "") for k in TEXT_FIELDS})


def import_gdoc(code):
    """Lê o Google Docs que está na pasta do vídeo e copia o texto para o roteiro (gancho/roteiro/CTA).
    Funciona com documentos compartilhados por link (leitura); o original no Drive não é alterado."""
    import httpx
    docs = gdocs_in(code)
    if not docs:
        raise RuntimeError("Não achei nenhum Google Docs na pasta deste vídeo no Drive.")
    stub = json.loads(docs[0].read_text(encoding="utf-8"))
    did = stub.get("doc_id")
    try:
        r = httpx.get(f"https://docs.google.com/document/d/{did}/export?format=txt", timeout=30, follow_redirects=True)
    except httpx.HTTPError as e:
        raise RuntimeError(f"Não consegui falar com o Google Docs agora ({type(e).__name__}). Tente de novo.")
    if r.status_code != 200 or "text/plain" not in r.headers.get("content-type", ""):
        raise RuntimeError("O Google Docs não está compartilhado por link. No Docs: Compartilhar → "
                           "\"Qualquer pessoa com o link\" (leitor) e tente de novo.")
    parts = split_script(r.text)
    snapshot(code, "antes de trazer o texto do Google Docs")
    parts["doc"] = f"https://docs.google.com/document/d/{did}/edit"
    parts["doc_name"] = docs[0].stem
    parts["imported"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return edit(code, parts)


# ------------------------------------------------------------------ inteligência em MD (padrões + padrão Roberto)
DOCS = {"padroes": ("Padrões das referências", DIR / "padroes_referencias.md"),
        "roberto": ("Padrão Roberto (tom de voz)", DIR / "padrao_roberto.md")}


FORMATS = DIR / "formatos"


def formats():
    """Formatos de vídeo do usuário (roteiros/formatos/<slug>.md); o título vem da 1ª linha '# Formato: …'."""
    out = []
    for f in sorted(FORMATS.glob("*.md")) if FORMATS.exists() else []:
        first = f.read_text(encoding="utf-8").split("\n", 1)[0]
        out.append({"slug": f.stem, "title": re.sub(r"^#\s*(Formato:\s*)?", "", first).strip() or f.stem})
    return out


def _doc_entry(key):
    if key.startswith("fmt:"):
        slug = key[4:]
        t = next((x["title"] for x in formats() if x["slug"] == slug), slug)
        return f"Formato · {t}", FORMATS / f"{slug}.md"
    return DOCS[key]


def doc_keys():
    return list(DOCS) + [f"fmt:{x['slug']}" for x in formats()]


def doc_read(key):
    title, path = _doc_entry(key)
    return {"key": key, "title": title, "text": path.read_text(encoding="utf-8") if path.exists() else ""}


def doc_write(key, text):
    path = _doc_entry(key)[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return doc_read(key)


def learn(line):
    """Acrescenta uma linha ao histórico do Padrão Roberto (ele evolui com cada aprovação/correção)."""
    path = DOCS["roberto"][1]
    text = path.read_text(encoding="utf-8") if path.exists() else "# Padrão Roberto\n\n## Histórico de aprendizado\n"
    if "## Histórico de aprendizado" not in text:
        text += "\n\n## Histórico de aprendizado\n"
    path.write_text(text.rstrip() + f"\n- {time.strftime('%Y-%m-%d')}: {line}\n", encoding="utf-8")


def approve(code, feedback=""):
    r = edit(code, {"status": "aprovado", "feedback": feedback, "archived": False})
    learn(f"{code} APROVADO: \"{r['title']}\" (ângulo: {r.get('angle') or '-'}; estrutura: {r.get('structure') or '-'})"
          + (f". Comentário do Roberto: {feedback}" if feedback else ""))
    return r


def discard(code, feedback=""):
    r = edit(code, {"archived": True, "feedback": feedback})
    learn(f"{code} DESCARTADO: \"{r['title']}\"" + (f". Motivo: {feedback}" if feedback else ""))
    return r


# ------------------------------------------------------------------ big ideas (pedidos de roteiro)
IDEAS = DIR / "ideias.json"


def ideas():
    return _read(IDEAS, [])


def add_idea(text, n=3, formato=""):
    with _lock:
        items = ideas()
        iid = f"I{max([int(x['id'][1:]) for x in items] + [0]) + 1:03d}"
        it = {"id": iid, "text": text.strip(), "n": max(1, min(6, int(n or 3))), "status": "na_fila", "formato": formato or "",
              "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "codes": [], "error": ""}
        items.append(it)
        _write(IDEAS, items)
        return it


def idea_edit(iid, **changes):
    with _lock:
        items = ideas()
        it = next((x for x in items if x["id"] == iid), None)
        if not it:
            raise KeyError(iid)
        it.update(changes)
        _write(IDEAS, items)
        return it


def idea_remove(iid):
    with _lock:
        _write(IDEAS, [x for x in ideas() if x["id"] != iid])


# ------------------------------------------------------------------ ENVIAR o roteiro para o Google Docs (Apps Script do usuário)
GOOGLE = DIR / "google.json"
APPS_SCRIPT = """// Editor de Vídeos → Google Docs (roda na SUA conta Google; só mexe na pasta Instagram Pessoal)
const TOKEN = '__TOKEN__';
const PASTA = '__PASTA__';

function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    if (d.token !== TOKEN) return out({ ok: false, erro: 'senha inválida' });
    let doc;
    if (d.docId) {
      if (!dentroDaPasta(DriveApp.getFileById(d.docId))) return out({ ok: false, erro: 'documento fora da pasta' });
      doc = DocumentApp.openById(d.docId);
    } else {
      const pasta = DriveApp.getFolderById(d.folderId);
      if (!dentroDaPasta(pasta) && d.folderId !== PASTA) return out({ ok: false, erro: 'pasta fora da Instagram Pessoal' });
      doc = DocumentApp.create(d.title || 'Roteiro');
      DriveApp.getFileById(doc.getId()).moveTo(pasta);
    }
    const body = doc.getBody();
    body.clear();
    const linha = (t, negrito) => { const p = body.appendParagraph(t); p.setBold(!!negrito); return p; };
    if (d.moral) { linha('MORAL: ' + d.moral, true); linha(''); }
    linha('HOOK: ' + (d.hook || ''), true);
    linha('');
    linha('BODY:', true);
    (d.body || '').split('\\n').forEach(t => linha(t, false));
    if (d.cta) { linha(''); linha('CTA: ' + d.cta, true); }
    const primeiro = body.getChild(0);
    if (primeiro && primeiro.asText().getText() === '') body.removeChild(primeiro);
    doc.saveAndClose();
    return out({ ok: true, docId: doc.getId(), url: doc.getUrl() });
  } catch (err) {
    return out({ ok: false, erro: String(err) });
  }
}

function dentroDaPasta(item) {
  const fila = [item];
  for (let i = 0; i < 40 && fila.length; i++) {
    const it = fila.shift();
    if (it.getId && it.getId() === PASTA) return true;
    const pais = it.getParents();
    while (pais.hasNext()) fila.push(pais.next());
  }
  return false;
}

function out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
"""


def google_cfg():
    import secrets
    c = _read(GOOGLE, {})
    if not c.get("token"):
        c["token"] = secrets.token_urlsafe(18)
        _write(GOOGLE, c)
    return c


def google_status():
    c = google_cfg()
    d = drive()
    code = APPS_SCRIPT.replace("__TOKEN__", c["token"]).replace("__PASTA__", d.get("folder_id") or "")
    return {"script_url": c.get("script_url", ""), "ok": bool(c.get("script_url")), "codigo": code,
            "testado": c.get("testado", "")}


def google_set(url):
    c = google_cfg()
    c["script_url"] = (url or "").strip()
    c["testado"] = ""
    _write(GOOGLE, c)
    return google_status()


def _drive_item_id(path):
    try:
        out = subprocess.run(["xattr", "-p", "com.google.drivefs.item-id#S", str(path)], capture_output=True, text=True)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def plain(t):
    """Texto sem as marcas de destaque (**palavra**)."""
    return (t or "").replace("**", "")


def highlights(r):
    """Trechos destacados pelo Roberto no roteiro (Ctrl+B → **trecho**): viram destaque na legenda da edição."""
    return [m.strip() for k in ("hook", "body", "cta") for m in re.findall(r"\*\*(.+?)\*\*", r.get(k) or "", re.S) if m.strip()]


def _toks(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", (t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", t)


def match_highlights(words, phrases):
    """Acha cada trecho destacado na transcrição (na ordem do roteiro, tolerante a erro do reconhecimento de voz e a
    pequenas diferenças entre o que foi escrito e o que foi falado). Devolve [(trecho, i0, i1) ou (trecho, None, None)]."""
    from difflib import SequenceMatcher
    wt = [(_toks(w["w"]) or [""])[0] for w in words]
    def sim(a, b):
        if a == b:
            return True
        if min(len(a), len(b)) < 4:
            return False
        n = len(os.path.commonprefix([a, b]))           # "dosezinha" × "dose", "criadores" × "creators"
        return n >= 4 and n >= 0.6 * min(len(a), len(b)) or SequenceMatcher(None, a, b).ratio() >= 0.7
    out, pos = [], 0
    for ph in phrases:
        pt = _toks(ph)
        if not pt:
            continue
        best = None
        for start_from in (pos, 0):
            for i in range(start_from, len(wt)):
                if not sim(pt[0], wt[i]) and not (len(pt) > 1 and i + 1 < len(wt) and sim(pt[1], wt[i + 1])):
                    continue
                j, k, hits = i, 0, 0
                while k < len(pt) and j < len(wt) and j - i < len(pt) + 3:
                    if sim(pt[k], wt[j]):
                        hits, k, j = hits + 1, k + 1, j + 1
                    elif k + 1 < len(pt) and sim(pt[k + 1], wt[j]):
                        k += 1                         # palavra do roteiro que não foi falada
                    else:
                        j += 1                         # palavra falada a mais
                score = hits / len(pt)
                if score >= (1.0 if len(pt) == 1 else 0.6) and (best is None or score > best[0]):
                    best = (score, i, j - 1)
                    if score == 1.0:
                        break
            if best:
                break
        if best:
            out.append((ph, best[1], best[2]))
            pos = best[2] + 1
        else:
            out.append((ph, None, None))
    return out


def apply_highlights(pid, code=None):
    """Destaques do roteiro (Ctrl+B) → palavras com `hl` no projeto (CAIXA ALTA na cor de destaque da legenda)."""
    from .store import load as pload, update as pupdate
    r = next((x for x in load() if x["code"] == code), None) if code else by_project(pid)
    if not r:
        return {"roteiro": None, "achados": [], "faltando": []}
    phrases = highlights(r)
    res = match_highlights(pload(pid)["words"], phrases)

    def f(p):
        for w in p["words"]:
            if w.get("hl") == "roteiro":
                w.pop("hl", None)
        for _ph, a, b in res:
            if a is not None:
                for i in range(a, b + 1):
                    p["words"][i].setdefault("hl", "roteiro")
    pupdate(pid, f)
    return {"roteiro": r["code"], "achados": [(ph, a, b) for ph, a, b in res if a is not None],
            "faltando": [ph for ph, a, _ in res if a is None]}


def push_gdoc(code):
    """Manda o texto do roteiro (moral/gancho/roteiro/CTA) para o Google Docs do vídeo (cria se não houver)."""
    import httpx
    c = google_cfg()
    if not c.get("script_url"):
        raise RuntimeError("SETUP")
    r = next((x for x in load() if x["code"] == code), None)
    if not r:
        raise KeyError(code)
    doc_id = None
    m = re.search(r"/document/d/([\w-]+)", r.get("doc") or "")
    if m:
        doc_id = m.group(1)
    payload = {"token": c["token"], "docId": doc_id, "title": f"{code} — {r.get('title') or 'Roteiro'}",
               "moral": r.get("moral", ""), "hook": plain(r.get("hook", "")), "body": plain(r.get("body", "")),
               "cta": plain(r.get("cta", ""))}
    if not doc_id:
        folder = ensure_folder(code)
        fid = _drive_item_id(folder)
        for _ in range(10):                     # pasta recém-criada demora uns segundos para ganhar id no Drive
            if fid:
                break
            time.sleep(1.5)
            fid = _drive_item_id(folder)
        if not fid:
            raise RuntimeError("A pasta do vídeo ainda está sincronizando com o Drive. Tente de novo em instantes.")
        payload["folderId"] = fid
    try:
        resp = httpx.post(c["script_url"], json=payload, timeout=60, follow_redirects=True)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Não consegui falar com o seu Apps Script ({type(e).__name__}). Confira a URL.")
    if resp.status_code in (401, 403):
        raise RuntimeError("O Google barrou o acesso: no Apps Script, Implantar → Gerenciar implantações → lápis → "
                           "\"Quem pode acessar: Qualquer pessoa\" → Implantar (a URL continua a mesma).")
    if resp.status_code == 404:
        raise RuntimeError("URL do Apps Script não encontrada: use a URL do App da Web que termina em /exec.")
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        raise RuntimeError("O Apps Script respondeu uma página em vez de dados: confira se a implantação é \"App da Web\""
                           " com acesso \"Qualquer pessoa\" e se o código colado é o do editor.")
    if not data.get("ok"):
        raise RuntimeError(f"O Google respondeu: {data.get('erro', 'erro desconhecido')}")
    changes = {"pushed": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if data.get("docId") and not doc_id:
        changes.update(doc=f"https://docs.google.com/document/d/{data['docId']}/edit", doc_name=payload["title"])
    c["testado"] = changes["pushed"]
    _write(GOOGLE, c)
    return edit(code, changes)
