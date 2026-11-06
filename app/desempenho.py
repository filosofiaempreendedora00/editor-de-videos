"""DASHBOARD de desempenho: cada vídeo × Instagram, YouTube Shorts e TikTok (aba Dashboard da Agenda).

Só LÊ as redes (`redes.yt_metricas`, `ig_metricas`, `tt_metricas`). A foto fica em `roteiros/desempenho.json`, atualizada
a cada 3 h pelo servidor e no botão "Atualizar agora", com um registro por dia para mostrar o crescimento.

Como um post vira um vídeo (card V0NN), nesta ordem:
1. ligação feita por ele na tela (`ligados`);
2. o link/id que a agenda já guardou ao publicar;
3. texto parecido: a legenda do post × legenda, gancho e título do card (quem posta à mão, como no Instagram).
O que não casa aparece em "Posts sem vídeo", para ele ligar ou ignorar. Sem dado da rede, dá para digitar as views à mão
(`digitar`); o número da API tem prioridade quando chega.
"""
import json
import os
import re
import threading
import time
import traceback
import unicodedata
from collections import Counter
from datetime import datetime, timedelta
from math import log

from . import agenda, redes, roteiros

ARQ = roteiros.DIR / "desempenho.json"
INICIO = "2026-10-01"             # 1ºs vídeos da esteira; posts mais antigos do perfil não entram
INTERVALO = 3 * 3600
MINIMO = 0.6                      # nota mínima do texto para ligar sozinho (0,45 ligou o Epicteto ao vídeo errado)
FOLGA = 1.5                       # e tem que ganhar do 2º colocado por essa razão
FICHA = ("views", "alcance", "curtidas", "comentarios", "compart", "salvos")
PARADAS = set("""para pela pelo pelos pelas como mais mas que quem qual quando onde esse essa isso este esta isto aquele aquela
    aquilo uma umas uns dos das nos nas num numa com sem por você vocês voce voces ele ela eles elas nós nos foi ser são sao
    tem tinha tava está esta estão muito muita muitos muitas seu sua seus suas meu minha nosso nossa até ate sobre entre
    depois antes ainda sempre nunca também tambem porque então entao aqui ali lá tudo todo toda todos todas cada coisa coisas
    fazer feito pode podem vai vão gente agora hoje isso outro outra""".split())

_trava = threading.RLock()
_coleta = threading.Lock()


def _agora():
    return datetime.now(agenda.TZ)


def _ler():
    try:
        d = json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("posts", {k: {} for k in agenda.REDES})
    for chave, vazio in (("redes", {}), ("ligados", {}), ("ignorados", []), ("manual", {}), ("historico", {}), ("atualizado", "")):
        d.setdefault(chave, vazio)
    return d


def _gravar(d):
    with _trava:
        tmp = ARQ.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, ARQ)


# ---------------------------------------------------------------- post ↔ vídeo
def _ident(k, url):
    """O pedaço do link que identifica o post: id do Short, código do Reel, id do TikTok."""
    m = re.search({"yt": r"/shorts/([\w-]+)", "ig": r"/(?:reel|reels|p|tv)/([\w-]+)", "tt": r"/video/(\d+)"}[k], url or "")
    return m.group(1) if m else ""


def _da_agenda():
    """(rede, identificador) → código do vídeo, a partir do que a agenda publicou."""
    out = {}
    for p in agenda.load():
        if p.get("code"):
            for k, e in p["redes"].items():
                for x in (e.get("id_rede"), _ident(k, e.get("url"))):
                    if x:
                        out[(k, str(x))] = p["code"]
    return out


def _palavras(txt):
    sem = unicodedata.normalize("NFKD", (txt or "").lower()).encode("ascii", "ignore").decode()
    return [w for w in re.findall(r"[a-z0-9$]{3,}", sem) if w not in PARADAS]


def _cards_texto():
    """Só os vídeos já marcados como publicados: legenda + gancho + título + início do texto."""
    out = {}
    for c in roteiros.load():
        if c.get("archived") or c.get("status") not in ("publicado", "destaque"):
            continue
        out[c["code"]] = Counter(_palavras(" ".join([c.get("caption") or "", c.get("hook") or "", c.get("title") or "", (c.get("body") or "")[:900]])))
    return out


def _melhor_card(texto, cards, usados):
    """Palavra rara vale mais (Joshie, Jung, Epicteto): nota = peso das palavras do post que estão no card."""
    if not cards:
        return None, 0
    n = len(cards)
    df = Counter(w for c in cards.values() for w in c)
    peso = lambda w: log(1 + n / (1 + df[w])) + (0.6 if df[w] == 0 else 0)    # palavra que não está em card nenhum pesa contra
    alvo = set(_palavras(texto))
    total = sum(peso(w) for w in alvo)
    if not total:
        return None, 0
    notas = sorted(((sum(peso(w) for w in alvo if w in c) / total, code) for code, c in cards.items() if code not in usados), reverse=True)
    if not notas:
        return None, 0
    nota, code = notas[0]
    seg = notas[1][0] if len(notas) > 1 else 0
    return (code if nota >= MINIMO and nota >= seg * FOLGA else None), nota


def _casar(d):
    agendados = _da_agenda()
    cards = _cards_texto()
    for k in agenda.REDES:
        usados = {c for ch, c in d["ligados"].items() if ch.startswith(k + ":")}
        novos = []
        for pid, p in d["posts"].get(k, {}).items():
            ch = f"{k}:{pid}"
            if ch in d["ligados"] or ch in d["ignorados"] or f"solto:{ch}" in d["ignorados"]:
                continue
            code = agendados.get((k, str(pid))) or agendados.get((k, _ident(k, p.get("url"))))
            if code:
                d["ligados"][ch] = code
                usados.add(code)
            else:
                novos.append((p.get("quando") or "", ch, p))
        for _, ch, p in sorted(novos, key=lambda x: x[0], reverse=True):
            if p.get("privado"):
                continue
            code, _nota = _melhor_card(p.get("texto"), cards, usados)
            if code:
                d["ligados"][ch] = code
                usados.add(code)


# ---------------------------------------------------------------- coleta
def _coletar_rede(k):
    """Devolve (posts, estado, mensagem)."""
    if k == "yt":
        return redes.yt_metricas(), "ok", ""
    if k == "ig":
        posts, aviso = redes.ig_metricas(INICIO)
        return posts, ("falta" if aviso else "ok"), aviso
    return redes.tt_metricas(), "ok", ""


def coletar():
    """Pergunta às 3 redes. Rede que falhar mantém os últimos números e mostra o motivo."""
    if not _coleta.acquire(blocking=False):
        return _ler()
    try:
        contas = redes.status()
        d = _ler()
        novo = {}
        for k in agenda.REDES:
            if not contas.get(k, {}).get("conectado"):
                d["redes"][k] = {"estado": "desconectada", "msg": "Conta não conectada (aba Contas)."}
                continue
            try:
                posts, estado, msg = _coletar_rede(k)
                novo[k] = posts
                d["redes"][k] = {"estado": estado, "msg": msg, "em": _agora().isoformat(timespec="seconds")}
            except redes.SemPermissao as ex:
                d["redes"][k] = {"estado": "falta", "msg": str(ex)}
            except (redes.Falha, redes.Temporario) as ex:
                d["redes"][k] = {"estado": "erro", "msg": str(ex)[:300]}
        d = {**_ler(), "redes": d["redes"]}             # ligações feitas na tela durante a coleta não se perdem
        for k, posts in novo.items():
            antes = d["posts"].get(k, {})
            d["posts"][k] = {str(p["id"]): {**{c: v for c, v in (antes.get(str(p["id"])) or {}).items() if c in FICHA and p.get(c) is None},
                                            **{c: v for c, v in p.items() if v is not None}} for p in posts}
        _casar(d)
        _anotar_dia(d)
        d["atualizado"] = _agora().isoformat(timespec="seconds")
        _gravar(d)
        return d
    finally:
        _coleta.release()


def _anotar_dia(d):
    dia = _agora().strftime("%Y-%m-%d")
    por = _por_video(d)
    for code, redes_v in por.items():
        d["historico"].setdefault(code, {})[dia] = {k: p.get("views") for k, p in redes_v.items() if p.get("views") is not None}


def _por_video(d):
    out = {}
    for k in agenda.REDES:
        for pid, p in d["posts"].get(k, {}).items():
            code = d["ligados"].get(f"{k}:{pid}")
            if code and f"{k}:{pid}" not in d["ignorados"] and not p.get("privado"):
                out.setdefault(code, {})[k] = {**p, "id": pid}
    return out


def iniciar():
    """Thread do servidor: atualiza quando a foto passa de 3 h."""
    def laco():
        time.sleep(90)
        while True:
            try:
                em = _ler().get("atualizado")
                if not em or (_agora() - datetime.fromisoformat(em)).total_seconds() > INTERVALO:
                    coletar()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            time.sleep(600)
    threading.Thread(target=laco, daemon=True).start()


# ---------------------------------------------------------------- ações da tela
def ligar(k, pid, code):
    """Liga um post a um vídeo (code = V0NN), ignora (code = "ignorar") ou solta (code vazio: volta para os posts sem vídeo)."""
    with _trava:
        d = _ler()
        ch = f"{k}:{pid}"
        d["ligados"].pop(ch, None)
        d["ignorados"] = [x for x in d["ignorados"] if x != ch]
        if code == "ignorar":
            d["ignorados"].append(ch)
        elif code:
            for outro in [c for c, v in d["ligados"].items() if v == code and c.startswith(k + ":")]:
                d["ligados"].pop(outro)                  # um vídeo tem um post por rede
            d["ligados"][ch] = code
        else:
            d["ignorados"].append(f"solto:{ch}")         # não religa sozinho no próximo casamento
        _gravar(d)


def digitar(code, k, views):
    """Views à mão (rede sem acesso à API). Vazio apaga."""
    with _trava:
        d = _ler()
        vid = d["manual"].setdefault(code, {})
        if views in (None, ""):
            vid.pop(k, None)
        else:
            vid[k] = {"views": max(0, int(views)), "em": _agora().isoformat(timespec="seconds")}
        _gravar(d)


# ---------------------------------------------------------------- o painel
def _estado_agenda(code):
    """Por rede: o que a agenda sabe deste vídeo (agendado para quando, ou já publicado)."""
    out = {}
    for p in agenda.load():
        if p.get("code") != code:
            continue
        for k, e in p["redes"].items():
            if e.get("status") in ("agendado", "enviando", "na_rede", "publicado"):
                out[k] = {"status": e["status"], "quando": e.get("quando") or "", "url": e.get("url") or ""}
    return out


def _thumb(arquivo):
    try:
        return agenda.capa(arquivo, 1.0) if arquivo else None
    except Exception:  # noqa: BLE001
        return None


def painel():
    d = _ler()
    por = _por_video(d)
    linhas = []
    for r in agenda.prontos():
        code = r["code"]
        if r["status"] == "editado" and code not in por:
            continue
        ag_est = _estado_agenda(code)
        cel, total = {}, 0
        tem_numero = False
        for k in agenda.REDES:
            p = por.get(code, {}).get(k)
            mao = d["manual"].get(code, {}).get(k)
            c = {c2: (p or {}).get(c2) for c2 in FICHA}
            est = ag_est.get(k) or {}
            c.update(id=(p or {}).get("id"), url=(p or {}).get("url") or est.get("url") or "", quando=(p or {}).get("quando") or "", manual=False)
            if c["views"] is None and mao:
                c.update(views=mao["views"], manual=True)
            if c["views"] is not None:
                c["estado"] = "ok"
                total += c["views"]
                tem_numero = True
            elif p:
                c["estado"] = "sem_views"
            elif est.get("status") in ("agendado", "enviando") or (est.get("status") == "na_rede" and k == "yt"):
                c.update(estado="agendado", quando=est.get("quando"))
            elif est or (k == "ig" and r["status"] in ("publicado", "destaque")) or (r["canais"] or {}).get(k):
                c["estado"] = "sem_dados"          # postado, mas ainda não achei o post nessa rede
            else:
                c["estado"] = "nao"
            cel[k] = c
        dias = sorted(x for x in d["historico"].get(code, {}) if x < _agora().strftime("%Y-%m-%d"))
        delta = None
        if dias and tem_numero:                 # só compara rede com número da API nos dois dias (rede nova ou digitada não é "crescimento")
            ontem = d["historico"][code][dias[-1]]
            delta = sum(cel[k]["views"] - v for k, v in ontem.items() if cel[k]["views"] is not None and not cel[k]["manual"] and v is not None)
        linhas.append({"code": code, "title": r["title"], "status": r["status"], "thumb": _thumb(r["arquivo"]),
                       "total": total if tem_numero else None, "delta": delta, "redes": cel,
                       "desde": min([c["quando"][:10] for c in cel.values() if c.get("quando") and c["estado"] in ("ok", "sem_views")] or [""])})
    resumo = {}
    for k, info in agenda.REDES.items():
        vals = [ln["redes"][k]["views"] for ln in linhas if ln["redes"][k]["views"] is not None]
        est = d["redes"].get(k) or {"estado": "aguardando", "msg": ""}
        resumo[k] = {"nome": info["nome"], "views": sum(vals) if vals else None, "videos": len(vals), "estado": est["estado"], "msg": est.get("msg", "")}
    soltos = []
    for k in agenda.REDES:
        for pid, p in d["posts"].get(k, {}).items():
            ch = f"{k}:{pid}"
            if ch not in d["ligados"] and ch not in d["ignorados"] and not p.get("privado"):
                soltos.append({"rede": k, "id": pid, "url": p.get("url", ""), "quando": p.get("quando", ""), "texto": (p.get("texto") or "")[:110],
                               "views": p.get("views"), "curtidas": p.get("curtidas")})
    linhas.sort(key=lambda x: (x["total"] is not None, x["total"] or 0, x["desde"]), reverse=True)
    vals = [ln["total"] for ln in linhas if ln["total"] is not None]
    return {"atualizado": d["atualizado"], "total": sum(vals) if vals else None, "redes": resumo, "linhas": linhas,
            "soltos": sorted(soltos, key=lambda x: x["quando"], reverse=True),
            "cards": [{"code": ln["code"], "title": ln["title"]} for ln in sorted(linhas, key=lambda x: roteiros._num(x["code"]), reverse=True)]}
