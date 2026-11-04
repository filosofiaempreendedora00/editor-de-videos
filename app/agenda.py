"""AGENDA DE PUBLICAÇÕES — Instagram (Reels), YouTube Shorts e TikTok num calendário (03/11, pedido dele: "clareza total
no que foi postado e no que não foi" + "setar nessas plataformas a legenda, o arquivo etc. e você publicar exatamente nas
datas e horários que eu pedi" — "parecido com um mLabs da vida").

Um AGENDAMENTO (A001…) = um vídeo (o MP4 final, em geral `<pasta V0NN>/final/… — EDITADO.mp4`) que vai para uma ou
mais redes, cada uma com a própria data/hora, legenda e opções. Fica em `roteiros/agenda.json` (backup privado). As
contas (tokens) ficam em `.segredos/contas.json` (fora do git e do backup) e quem fala com as APIs oficiais é
`app/redes.py`.

Quem publica é o RELÓGIO (`rodar()`, a cada 30 s dentro do servidor; ou `agenda rodar`, pelo launchd): um só por vez
no Mac (trava de arquivo). Por rede:
- YouTube: sobe assim que dá, PRIVADO com `publishAt` → o próprio YouTube publica na hora, mesmo com o Mac desligado.
- Instagram: a API não agenda. 15 min antes o vídeo sobe (contêiner, vale 24 h); na hora exata, `media_publish`.
- TikTok: a API não agenda. Na hora, sobe e publica (o TikTok processa em ~1–2 min).
Mac dormindo na hora: até 3 h de atraso publica assim que acordar (e avisa); mais que isso fica "atrasado" esperando
ele. Com Instagram/TikTok nas próximas 12 h, o servidor segura o Mac acordado (`caffeinate -i`, só enquanto roda).
"""
import fcntl
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import roteiros
from .media import FFMPEG, probe

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "roteiros" / "agenda.json"
CAPAS = ROOT / "roteiros" / "agenda_capas"
SEGREDOS = ROOT / ".segredos"
TZ = ZoneInfo("America/Sao_Paulo")

REDES = {
    "ig": {"nome": "Instagram", "curto": "Reels", "legenda_max": 2200, "hashtags_max": 30, "dur_min": 3, "dur_max": 900,
           "mb_max": 300},
    "yt": {"nome": "YouTube Shorts", "curto": "Shorts", "titulo_max": 100, "legenda_max": 5000, "dur_max": 180},
    "tt": {"nome": "TikTok", "curto": "TikTok", "legenda_max": 2200, "dur_min": 3, "dur_max": 600},
}
OPCOES = {
    "ig": {"share_to_feed": True, "colaboradores": "", "ia": False},
    "yt": {"privacidade": "public", "categoria": "27", "tags": "", "kids": False, "ia": False},
    # TikTok: quem pode ver NÃO tem padrão (regra da TikTok para apps que publicam: a pessoa escolhe a cada post)
    "tt": {"privacidade": "", "comentarios": True, "duet": True, "stitch": True, "ia": False, "marca": False},
}
# status de cada rede dentro de um agendamento
ST = ("rascunho", "agendado", "enviando", "na_rede", "publicado", "erro", "atrasado")
ATIVOS = ("agendado", "enviando", "na_rede")
ANTES_IG = 15 * 60          # o Instagram recebe o vídeo 15 min antes; na hora só falta o "publicar"
ATRASO_MAX = 3 * 3600       # Mac dormindo: até 3 h de atraso ainda publica sozinho
ESPERA = (60, 180, 600)     # novas tentativas depois de falha de rede (1, 3 e 10 min)

_tlock = threading.RLock()


@contextmanager
def _trava():
    """Leitura+escrita do agenda.json sem atropelar: threads do servidor e outros processos (CLI, launchd)."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    with _tlock, open(DB.with_suffix(".lock"), "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def load():
    try:
        return json.loads(DB.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _write(items):
    tmp = DB.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DB)


def agora():
    return datetime.now(TZ)


def quando_dt(s):
    """'2026-11-05T18:00' (horário de Brasília, como o <input datetime-local>) → datetime com fuso."""
    if not s:
        return None
    d = datetime.fromisoformat(s[:16])
    return d.replace(tzinfo=TZ) if d.tzinfo is None else d.astimezone(TZ)


def _hora(s):
    d = quando_dt(s)
    return d.strftime("%d/%m às %H:%M") if d else "—"


def _carimbo():
    return agora().strftime("%Y-%m-%dT%H:%M:%S")


def rede_nova(k, **kw):
    e = {"on": False, "quando": "", "legenda": "", "opcoes": dict(OPCOES[k]), "status": "rascunho", "etapa": "",
         "erro": "", "url": "", "id_rede": "", "publicado_em": "", "tentativas": 0, "log": []}
    if k == "yt":
        e["titulo"] = ""
    e.update(kw)
    return e


# ---------------------------------------------------------------- arquivo do vídeo
def final_mp4(code):
    """O vídeo final do card, pela cópia LOCAL do que foi entregue no Drive (`card.entregue.origem`, gravado pelo
    `entregar`): o servidor roda como serviço do macOS e o macOS não deixa serviço ler a pasta do Google Drive.
    Sem registro: o final na pasta do Drive (se der para ler) ou a exportação mais nova da gravação do código."""
    r = _card(code) or {}
    origem = (r.get("entregue") or {}).get("origem")
    if origem and Path(origem).is_file():
        return origem
    try:
        pasta = roteiros.find_folder(code)
        mp4s = [f for f in (pasta / "final").glob("*.mp4") if not f.name.startswith(".")] if pasta else []
        if mp4s:
            return str(max(mp4s, key=lambda f: ("EDITADO" in f.name, f.stat().st_mtime)))
    except OSError:
        pass
    from .store import PROJECTS
    exps = []
    for f in PROJECTS.glob("*/project.json"):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if p.get("roteiro") == code and not any(w in (p.get("name") or "").lower() for w in ("ensaio", "montador")):
            exps += [x for x in (f.parent / "exports").glob("*.mp4") if not x.name.startswith("amostra") and ".tmp." not in x.name]
    return str(max(exps, key=lambda x: x.stat().st_mtime)) if exps else None


_info = {}


def info_arquivo(path):
    """Duração, resolução e tamanho (com cache pelo mtime — os arquivos do Drive são lidos sob demanda)."""
    p = Path(path or "")
    if not p.is_file():
        return None
    chave = (str(p), p.stat().st_mtime, p.stat().st_size)
    if _info.get(str(p), (None,))[0] != chave:
        i = probe(p)
        _info[str(p)] = (chave, {"dur": round(i["duration"], 2), "w": i["width"], "h": i["height"],
                                 "mb": round(p.stat().st_size / 1e6, 1), "nome": p.name, "audio": i["has_audio"]})
    return _info[str(p)][1]


def capa(path, t=1.0):
    """Miniatura (jpg pequeno) do quadro escolhido como capa. Devolve o nome do arquivo em CAPAS."""
    p = Path(path or "")
    if not p.is_file():
        return None
    nome = hashlib.sha1(f"{p}|{p.stat().st_mtime}|{float(t):.2f}".encode()).hexdigest()[:16] + ".jpg"
    dst = CAPAS / nome
    if not dst.exists():
        CAPAS.mkdir(parents=True, exist_ok=True)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{max(0.0, float(t)):.2f}", "-i", str(p), "-frames:v", "1",
                        "-vf", "scale=360:-2", "-q:v", "4", str(dst)], capture_output=True, timeout=90)
    return nome if dst.exists() else None


# ---------------------------------------------------------------- criar / editar
def _card(code):
    return next((r for r in roteiros.load() if r["code"] == code), None) if code else None


def criar(data):
    """Novo agendamento. Com `code` (V0NN), já vem o MP4 final, a legenda do card e o título para o YouTube."""
    data = dict(data or {})
    code = (data.get("code") or "").strip().upper() or None
    r = _card(code)
    arquivo = data.get("arquivo") or (final_mp4(code) if code else None) or ""
    legenda = (r or {}).get("caption") or ""
    titulo = ((r or {}).get("title") or Path(arquivo).stem if (r or arquivo) else "")[:100]
    with _trava():
        items = load()
        n = max([int(x["id"][1:]) for x in items if re.match(r"^A\d+$", x.get("id", ""))] + [0]) + 1
        post = {"id": f"A{n:03d}", "code": code, "nome": data.get("nome") or (r or {}).get("title") or Path(arquivo).stem,
                "arquivo": arquivo, "capa": float(data.get("capa") or 1.0), "criado": _carimbo(), "atualizado": _carimbo(),
                "redes": {k: rede_nova(k, legenda=legenda, **({"titulo": titulo} if k == "yt" else {})) for k in REDES}}
        quando = data.get("quando") or ""
        for k in data.get("redes_on") or []:
            if k in REDES:
                post["redes"][k].update(on=True, quando=quando)
        items.append(post)
        _write(items)
    if data.get("redes") or data.get("arquivo_novo"):
        return editar(post["id"], data)
    return post


EDITAVEIS = {"nome", "arquivo", "capa", "code"}


def editar(aid, changes):
    """Muda o agendamento. Rede já publicada (ou subindo agora) não muda; mudar o que já está no YouTube/Instagram
    faz o relógio atualizar lá (YouTube: videos.update) ou refazer o envio (Instagram: a legenda vai no contêiner)."""
    with _trava():
        items = load()
        p = next((x for x in items if x["id"] == aid), None)
        if not p:
            raise KeyError(aid)
        for k in EDITAVEIS & set(changes):
            p[k] = changes[k]
        for k, mud in (changes.get("redes") or {}).items():
            if k not in REDES or not isinstance(mud, dict):
                continue
            e = p["redes"].setdefault(k, rede_nova(k))
            if e["status"] in ("publicado", "enviando"):
                if any(mud.get(c) != e.get(c) for c in ("quando", "legenda", "titulo") if c in mud):
                    raise ValueError(f"{REDES[k]['nome']}: já {'publicado' if e['status'] == 'publicado' else 'subindo agora'} — não dá para mudar.")
                continue
            # SEGURANÇA (pedido dele, 03/11: "publicar agora sempre precisa de confirmação dupla"): mudar para o PASSADO o
            # horário de algo armado faria o relógio publicar na hora — só pelo "Publicar agora", com as duas confirmações
            if "quando" in mud and mud["quando"] and mud["quando"] != e.get("quando") and e["status"] in ATIVOS \
                    and quando_dt(mud["quando"]) < agora() - timedelta(minutes=1):
                raise ValueError(f"{REDES[k]['nome']}: esse horário já passou. Para publicar agora, use “Publicar agora” "
                                 "(pede confirmação dupla).")
            if "on" in mud and not mud["on"] and e.get("on") and e["status"] in ("agendado", "erro", "atrasado"):
                e["log"] = (e.get("log") or [])[-29:] + [{"t": _carimbo(), "msg": "desligado: volta a rascunho"}]
            antes = {c: json.dumps(e.get(c), sort_keys=True) for c in ("quando", "legenda", "titulo", "opcoes")}
            for c in ("on", "quando", "legenda", "titulo"):
                if c in mud:
                    e[c] = mud[c]
            if isinstance(mud.get("opcoes"), dict):
                e["opcoes"] = {**e.get("opcoes", {}), **mud["opcoes"]}
            mudou = [c for c in antes if json.dumps(e.get(c), sort_keys=True) != antes[c]]
            if e["status"] == "na_rede" and mudou:
                if k == "yt":
                    e["atualizar"] = True             # o relógio manda a mudança para o vídeo agendado no YouTube
                elif k == "ig":                       # a legenda vai no contêiner: refaz o envio na hora certa
                    e.update(status="agendado", container="", etapa="")
            if e["status"] in ("erro", "atrasado") and "quando" in mudou:
                e.update(status="agendado", erro="", tentativas=0)
            if not e.get("on") and e["status"] in ("agendado", "erro", "atrasado"):
                e["status"] = "rascunho"
            if not e.get("on") and e["status"] == "na_rede":   # desligou depois de já estar na rede: cancela lá
                if k == "yt":
                    e.update(on=True, cancelar=True)          # o relógio deixa privado no YouTube e volta a rascunho
                else:
                    e.update(status="rascunho", container="", etapa="")
        p["atualizado"] = _carimbo()
        _write(items)
        return p


def remover(aid):
    with _trava():
        items = load()
        p = next((x for x in items if x["id"] == aid), None)
        if not p:
            raise KeyError(aid)
        presos = [REDES[k]["nome"] for k, e in p["redes"].items() if e["status"] in ("publicado", "na_rede", "enviando")]
        if presos:
            raise ValueError(f"Já foi para {', '.join(presos)}: cancele lá primeiro (o histórico fica guardado).")
        _write([x for x in items if x["id"] != aid])


def _set_rede(aid, k, **campos):
    with _trava():
        items = load()
        p = next((x for x in items if x["id"] == aid), None)
        if not p:
            return None
        e = p["redes"][k]
        msg = campos.pop("_log", None)
        e.update(campos)
        if msg:
            e["log"] = (e.get("log") or [])[-29:] + [{"t": _carimbo(), "msg": msg}]
        p["atualizado"] = _carimbo()
        _write(items)
        return p


# ---------------------------------------------------------------- validação
def validar(p):
    """Problemas por rede: [{nivel: erro|aviso, msg}]. Erro impede agendar; aviso só alerta."""
    from . import redes
    contas = redes.status()
    out = {}
    info = info_arquivo(p.get("arquivo"))
    for k, cfg in REDES.items():
        e = p["redes"].get(k) or {}
        if not e.get("on"):
            continue
        pr = []
        add = lambda nivel, msg: pr.append({"nivel": nivel, "msg": msg})       # noqa: E731
        if not info:
            add("erro", "O arquivo do vídeo não foi encontrado." if p.get("arquivo") else "Escolha o vídeo.")
        else:
            if info["dur"] > cfg["dur_max"]:
                add("erro", f"O vídeo tem {info['dur']:.0f} s; o limite aqui é {cfg['dur_max'] // 60} min"
                    + (" (acima de 3 min não vira Short)." if k == "yt" else "."))
            if cfg.get("mb_max") and info["mb"] > cfg["mb_max"]:
                add("erro", f"O arquivo tem {info['mb']:.0f} MB; o {cfg['nome']} aceita até {cfg['mb_max']} MB pela API.")
            if info["dur"] < cfg.get("dur_min", 0):
                add("erro", f"Vídeo curto demais ({info['dur']:.1f} s).")
            if info["w"] and info["h"] and info["h"] <= info["w"]:
                add("aviso", f"O vídeo não é vertical ({info['w']}×{info['h']}).")
        if not e.get("quando"):
            add("erro", "Falta a data e a hora.")
        elif quando_dt(e["quando"]) < agora() and e.get("status") not in ("publicado",):
            add("aviso", "O horário já passou: publica assim que agendar.")
        leg = e.get("legenda") or ""
        tam = len(leg.encode("utf-8")) if k == "yt" else len(leg)       # YouTube conta a descrição em bytes
        if tam > cfg["legenda_max"]:
            add("erro", f"{'Descrição' if k == 'yt' else 'Legenda'} com {tam} {'bytes' if k == 'yt' else 'caracteres'} "
                f"(máximo {cfg['legenda_max']}).")
        if k == "ig" and len(re.findall(r"#\w", leg)) > cfg["hashtags_max"]:
            add("erro", f"Mais de {cfg['hashtags_max']} hashtags (o Instagram recusa).")
        if k == "yt":
            t = (e.get("titulo") or "").strip()
            if not t:
                add("erro", "Falta o título do Short.")
            elif len(t) > cfg["titulo_max"]:
                add("erro", f"Título com {len(t)} caracteres (máximo {cfg['titulo_max']}).")
            if re.search(r"[<>]", t + leg):
                add("erro", "O YouTube não aceita os sinais < e > no título/descrição.")
            tags = [x.strip() for x in ((e.get("opcoes") or {}).get("tags") or "").split(",") if x.strip()]
            if sum(len(x) + (2 if " " in x else 0) for x in tags) + max(0, len(tags) - 1) > 500:
                add("erro", "As tags passam de 500 caracteres no total.")
        c = contas.get(k) or {}
        if k == "tt" and c.get("modo") == "direto" and not (e.get("opcoes") or {}).get("privacidade"):
            add("erro", "Escolha quem pode ver o vídeo no TikTok.")
        if not c.get("conectado"):
            add("aviso", f"A conta do {cfg['nome']} ainda não está conectada: conecte antes do horário.")
        for a in c.get("avisos") or []:
            add("aviso", a)
        out[k] = pr
    return out


class PrecisaConfirmar(ValueError):
    """Agendar com horário que já passou (ou daqui a < 2 min) = publicar agora: só com a confirmação dupla."""


def agendar(aid, redes_k=None, confirmado=False):
    """Liga o relógio para as redes marcadas (ou só `redes_k`). Recusa se houver erro de validação, e recusa o que
    sairia NA HORA (horário passado ou em < 2 min) sem `confirmado` — a tela pede a confirmação dupla antes."""
    p = next((x for x in load() if x["id"] == aid), None)
    if not p:
        raise KeyError(aid)
    v = validar(p)
    alvo = [k for k, e in p["redes"].items() if e.get("on") and (not redes_k or k in redes_k)
            and e["status"] in ("rascunho", "erro", "atrasado")]
    erros = [f"{REDES[k]['nome']}: {x['msg']}" for k in alvo for x in v.get(k, []) if x["nivel"] == "erro"]
    if erros:
        raise ValueError(" · ".join(erros))
    ja = [REDES[k]["nome"] for k in alvo if quando_dt(p["redes"][k]["quando"]) <= agora() + timedelta(minutes=2)]
    if ja and not confirmado:
        raise PrecisaConfirmar(f"Isto publicaria AGORA no {', '.join(ja)}: confirme duas vezes (Publicar agora).")
    for k in alvo:
        _set_rede(aid, k, status="agendado", erro="", tentativas=0, proxima="", etapa="",
                  _log=f"agendado para {_hora(p['redes'][k]['quando'])}")
    acordar()
    return next(x for x in load() if x["id"] == aid)


def desagendar(aid, k):
    """Volta para rascunho. Se o vídeo já estava agendado no YouTube, o relógio o deixa PRIVADO lá (não apaga nada)."""
    p = next((x for x in load() if x["id"] == aid), None)
    if not p:
        raise KeyError(aid)
    e = p["redes"][k]
    if e["status"] in ("publicado", "enviando"):
        raise ValueError(f"{REDES[k]['nome']}: já {'publicado' if e['status'] == 'publicado' else 'subindo agora'}.")
    if e["status"] == "na_rede" and k == "yt":
        _set_rede(aid, k, cancelar=True, _log="cancelado: fica privado no YouTube Studio")
        acordar()
    else:
        _set_rede(aid, k, status="rascunho", container="", etapa="", erro="", _log="desagendado")
    return next(x for x in load() if x["id"] == aid)


def publicar_agora(aid, k, confirmado=False):
    """Publica já. SEMPRE com confirmação dupla na tela (pedido dele) — sem `confirmado`, recusa."""
    if not confirmado:
        raise PrecisaConfirmar("“Publicar agora” precisa da confirmação dupla.")
    p = next((x for x in load() if x["id"] == aid), None)
    if not p:
        raise KeyError(aid)
    na_rede = p["redes"][k]["status"] == "na_rede"
    _set_rede(aid, k, on=True, quando=agora().strftime("%Y-%m-%dT%H:%M"),
              **({"atualizar": True} if na_rede and k == "yt" else {}))   # YouTube: o update com horário já passado publica
    if na_rede:
        acordar()
        return next(x for x in load() if x["id"] == aid)
    return agendar(aid, [k], confirmado=True)


def marcar_manual(aid, k, url="", desfazer=False):
    """Ele postou por conta própria (no app): fica registrado como publicado, com o link se tiver."""
    if desfazer:
        return _set_rede(aid, k, status="rascunho", manual=False, url="", publicado_em="", _log="desmarcado")
    p = _set_rede(aid, k, on=True, status="publicado", manual=True, url=url or "", publicado_em=_carimbo(),
                  _log="marcado como publicado à mão")
    _no_kanban(p, k)
    return p


def _no_kanban(p, k):
    """Publicou → o card acompanha: Instagram = coluna Publicado; Shorts/TikTok = o checkzinho do canal."""
    if not p or not p.get("code"):
        return
    r = _card(p["code"])
    if not r:
        return
    try:
        if k == "ig" and roteiros.STATUS.index(r["status"]) < roteiros.STATUS.index("publicado"):
            roteiros.edit(r["code"], {"status": "publicado"})
        elif k in ("yt", "tt") and not (r.get("canais") or {}).get(k):
            roteiros.edit(r["code"], {"canais": {**(r.get("canais") or {}), k: True}})
    except (KeyError, ValueError):
        pass


# ---------------------------------------------------------------- visão geral (o que foi postado e o que não foi)
def prontos():
    """Cards com vídeo pronto (editado, publicado, destaque) e o MP4 final de cada um."""
    out = []
    for r in roteiros.load():
        if r.get("archived") or r["status"] not in ("editado", "publicado", "destaque"):
            continue
        out.append({"code": r["code"], "title": r.get("title") or "", "status": r["status"], "arquivo": final_mp4(r["code"]),
                    "caption": r.get("caption") or "", "canais": r.get("canais") or {}})
    return sorted(out, key=lambda x: roteiros._num(x["code"]), reverse=True)


PESO = {"publicado": 5, "enviando": 4, "na_rede": 4, "agendado": 3, "erro": 2, "atrasado": 2, "rascunho": 1}


def central():
    """Uma linha por vídeo × as 3 redes: publicado (com link), agendado (com a hora), erro ou ainda não postado."""
    posts = load()
    linhas = {}
    for r in prontos():
        linhas[r["code"]] = {"code": r["code"], "title": r["title"], "card": r["status"], "arquivo": r["arquivo"],
                             "redes": {k: {"estado": "nao"} for k in REDES}}
        if r["status"] in ("publicado", "destaque"):
            linhas[r["code"]]["redes"]["ig"] = {"estado": "publicado", "fonte": "kanban"}
        for k in ("yt", "tt"):
            if r["canais"].get(k):
                linhas[r["code"]]["redes"][k] = {"estado": "publicado", "fonte": "marcado no card"}
    for p in posts:
        chave = p.get("code") or p["id"]
        ln = linhas.setdefault(chave, {"code": p.get("code"), "title": p.get("nome"), "card": None, "arquivo": p.get("arquivo"),
                                       "redes": {k: {"estado": "nao"} for k in REDES}})
        for k, e in p["redes"].items():
            if not e.get("on") and e["status"] == "rascunho":
                continue
            atual = ln["redes"][k]
            if PESO.get(e["status"], 0) >= PESO.get(atual.get("estado"), 0) or atual.get("fonte"):
                if atual.get("estado") == "publicado" and e["status"] != "publicado":
                    continue                          # já estava no ar (pelo card) — não "despublica"
                ln["redes"][k] = {"estado": e["status"], "quando": e.get("quando"), "url": e.get("url"), "aid": p["id"],
                                  "erro": e.get("erro"), "etapa": e.get("etapa"), "manual": e.get("manual", False),
                                  "publicado_em": e.get("publicado_em")}
    rows = sorted(linhas.values(), key=lambda x: (roteiros._num(x["code"]) if x.get("code") else 0), reverse=True)
    resumo = {k: {"publicado": 0, "agendado": 0, "nao": 0} for k in REDES}
    for ln in rows:
        for k, c in ln["redes"].items():
            g = "publicado" if c["estado"] == "publicado" else "agendado" if c["estado"] in ATIVOS else "nao"
            resumo[k][g] += 1
    return {"linhas": rows, "resumo": resumo}


# ---------------------------------------------------------------- o relógio
_acordar = threading.Event()
_rodando = {}
_cafe = None


def acordar():
    _acordar.set()


def _passo(p, k, e, t):
    """Qual é a próxima ação desta rede agora (ou None)."""
    if not e.get("on"):
        return None
    if e.get("proxima") and t < datetime.fromisoformat(e["proxima"]).replace(tzinfo=TZ):
        return None
    q = quando_dt(e.get("quando"))
    st = e["status"]
    if st == "enviando":                                  # caiu no meio (servidor reiniciou): retoma com cuidado
        vivo = e.get("vivo_em")
        if not vivo or t - datetime.fromisoformat(vivo).replace(tzinfo=TZ) > timedelta(minutes=10):
            return "retomar"
        return None
    if st == "agendado" and q:
        atraso = (t - q).total_seconds()
        if atraso > ATRASO_MAX and not (k == "yt" and e.get("id_rede")):
            return "atrasou"
        if k == "yt":                                   # público: sobe já e o YouTube publica na hora; não listado/privado: na hora
            return "subir" if ((e.get("opcoes") or {}).get("privacidade") or "public") == "public" or atraso >= 0 else None
        if k == "ig" and atraso >= -ANTES_IG:
            return "preparar"
        if k == "tt" and atraso >= 0:
            return "publicar"
    if st == "na_rede" and q:
        if k == "yt":
            if e.get("cancelar"):
                return "cancelar"
            if e.get("atualizar"):
                return "atualizar"
            if e.get("capa_pendente"):
                feito = e.get("capa_tentou")
                if not feito or t - datetime.fromisoformat(feito).replace(tzinfo=TZ) > timedelta(minutes=2):
                    return "capa"
            conf = e.get("conferido_em")
            if t >= q + timedelta(minutes=1) and (not conf or t - datetime.fromisoformat(conf).replace(tzinfo=TZ) > timedelta(minutes=5)):
                return "conferir"
        if k == "tt":                                   # rascunho na caixa de entrada: confere até ele publicar (48 h)
            conf = e.get("conferido_em")
            if t - q < timedelta(hours=48) and (not conf or t - datetime.fromisoformat(conf).replace(tzinfo=TZ) > timedelta(minutes=3)):
                return "conferir"
        if k == "ig":
            feito = e.get("container_em")
            if feito and t - datetime.fromisoformat(feito).replace(tzinfo=TZ) > timedelta(hours=23):
                return "preparar"                       # contêiner do Instagram vence em 24 h
            if t >= q:
                return "publicar"
    return None


def rodar(esperar=False):
    """Uma passada: dispara (em threads) tudo que está na hora. `esperar`: aguarda terminar (uso pela CLI/launchd)."""
    from . import redes
    t = agora()
    contas = redes.status()
    for p in load():
        for k, e in (p.get("redes") or {}).items():
            acao = _passo(p, k, e, t)
            if not acao:
                continue
            if acao != "atrasou" and not (contas.get(k) or {}).get("conectado"):
                # conta ainda não conectada: espera (ele pode conectar até o horário); passou da hora → erro, uma vez
                q = quando_dt(e.get("quando"))
                if q and t >= q and e["status"] == "agendado":
                    _falhou(p["id"], k, p.get("code") or p.get("nome"),
                            f"Chegou a hora, mas a conta do {REDES[k]['nome']} não está conectada (aba Contas). "
                            "Conecte e clique em Publicar agora.")
                continue
            if acao == "atrasou":
                _set_rede(p["id"], k, status="atrasado", etapa="",
                          erro=f"Não publicou às {_hora(e['quando'])}: o Mac estava desligado/dormindo. Publique agora ou reagende.",
                          _log="atrasado (mais de 3 h)")
                avisar(f"{REDES[k]['nome']}: não publicou", f"{p.get('code') or p['nome']} — o Mac estava dormindo. Abra a agenda.")
                continue
            chave = (p["id"], k)
            th = _rodando.get(chave)
            if th and th.is_alive():
                continue
            th = threading.Thread(target=_executar, args=(p["id"], k, acao), daemon=True)
            _rodando[chave] = th
            th.start()
    _segurar_acordado(t)
    if esperar:
        for th in list(_rodando.values()):
            th.join()


class Ctx:
    """O que a função da rede recebe: o agendamento, a rede, e como salvar o progresso no meio (id do envio etc.)."""

    def __init__(self, aid, k):
        self.aid, self.k = aid, k
        self.p = next(x for x in load() if x["id"] == aid)
        self.e = self.p["redes"][k]

    def salvar(self, msg=None, **campos):
        campos["vivo_em"] = _carimbo()
        if msg:
            campos["_log"] = msg
        self.p = _set_rede(self.aid, self.k, **campos) or self.p
        self.e = self.p["redes"][self.k]

    def vivo(self):
        self.salvar()


def _executar(aid, k, acao):
    from . import redes
    ctx = Ctx(aid, k)
    antes = ctx.e["status"]
    nome = ctx.p.get("code") or ctx.p.get("nome")
    try:
        if acao == "capa":
            ctx.salvar(capa_tentou=_carimbo())
        elif acao != "conferir":
            ctx.salvar(f"{acao}…", status="enviando", erro="")
        fim = redes.executar(k, acao, ctx) or {}
        if acao in ("conferir",) and not fim:
            ctx.salvar(conferido_em=_carimbo())
            return
        fim.setdefault("status", antes if acao != "retomar" else "agendado")
        fim.update(tentativas=0, proxima="", vivo_em="")
        msg = fim.pop("msg", None) or {"publicado": "publicado ✓", "na_rede": fim.get("etapa") or "enviado"}.get(fim["status"], acao)
        p = _set_rede(aid, k, _log=msg, **fim)
        if fim["status"] == "publicado":
            _no_kanban(p, k)
            avisar(f"Publicado no {REDES[k]['nome']} ✓", f"{nome} — {p['redes'][k].get('url') or ''}")
    except redes.Temporario as ex:                        # rede caiu, servidor da plataforma fora: tenta de novo
        n = int(ctx.e.get("tentativas") or 0) + 1
        if n <= len(ESPERA):
            prox = (agora() + timedelta(seconds=ESPERA[n - 1])).strftime("%Y-%m-%dT%H:%M:%S")
            volta = antes if antes != "enviando" else ("na_rede" if ctx.e.get("id_rede") or ctx.e.get("container") else "agendado")
            _set_rede(aid, k, status=volta, tentativas=n, proxima=prox, vivo_em="", erro=str(ex),
                      _log=f"falhou ({ex}); tento de novo às {prox[11:16]}")
        else:
            _falhou(aid, k, nome, str(ex))
    except Exception as ex:  # noqa: BLE001
        traceback.print_exc()
        _falhou(aid, k, nome, str(ex))


def _falhou(aid, k, nome, msg):
    _set_rede(aid, k, status="erro", erro=msg[:600], vivo_em="", _log="erro: " + msg[:200])
    avisar(f"Erro no {REDES[k]['nome']}", f"{nome}: {msg[:120]}")


def _segurar_acordado(t):
    """Instagram/TikTok nas próximas 12 h (ou algo subindo): `caffeinate -i` preso ao processo do servidor."""
    global _cafe
    precisa = any(th.is_alive() for th in _rodando.values())
    for p in load():
        for k, e in p["redes"].items():
            if e.get("on") and e["status"] in ATIVOS and (k != "yt" or not e.get("id_rede")):
                q = quando_dt(e.get("quando"))
                if q and q - t < timedelta(hours=12):
                    precisa = True
    vivo = _cafe is not None and _cafe.poll() is None
    if precisa and not vivo:
        try:
            _cafe = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        except OSError:
            _cafe = None
    elif not precisa and vivo:
        _cafe.terminate()
        _cafe = None


def acordado():
    return _cafe is not None and _cafe.poll() is None


def avisar(titulo, msg):
    """Notificação do macOS (canto da tela)."""
    try:
        subprocess.Popen(["osascript", "-e", f"display notification {json.dumps(msg)} with title {json.dumps(titulo)} "
                          'sound name "Glass"'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


_relogio = {"vivo": False, "desde": None, "ultima": None}


def iniciar_relogio():
    """Thread do servidor: pega a trava do relógio (só um publicador por Mac) e roda a cada 30 s."""
    def laco():
        SEGREDOS.mkdir(exist_ok=True)
        fh = open(SEGREDOS / "relogio.lock", "w")
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(30)                          # outro relógio (launchd/CLI) está rodando
        _relogio.update(vivo=True, desde=_carimbo())
        from . import redes
        manut = 0.0
        while True:
            try:
                rodar()
                if time.time() - manut > 3600:          # de hora em hora: renova o token do Instagram (vale 60 dias)
                    manut = time.time()
                    redes.manutencao()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            _relogio["ultima"] = _carimbo()
            _acordar.wait(30)
            _acordar.clear()
    threading.Thread(target=laco, daemon=True).start()


def rodar_uma_vez():
    """`agenda rodar` (launchd/CLI): se o servidor já é o relógio, não faz nada; senão roda uma passada e espera."""
    SEGREDOS.mkdir(exist_ok=True)
    with open(SEGREDOS / "relogio.lock", "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "o servidor já está cuidando da agenda"
        rodar(esperar=True)
        return "ok"


def relogio():
    return {**_relogio, "acordado": acordado(), "agora": _carimbo()}
