"""CONTAS E APIs OFICIAIS das redes da agenda (`app/agenda.py`): Instagram (Reels), YouTube Shorts e TikTok.

Segredos (ids de app, tokens) em `.segredos/contas.json` — fora do git (repositório público) e fora do backup.
Cada rede tem: conectar (OAuth com volta em http://localhost:8765/api/agenda/oauth/<rede>, ou colar o token no caso
do Instagram), status da conta (qual @ está ligado, até quando vale), e as ações que o relógio da agenda chama:
- yt: subir (privado + publishAt: o YouTube publica sozinho), atualizar, conferir, cancelar (deixa privado), retomar
- ig: preparar (contêiner + upload do arquivo, 15 min antes), publicar (media_publish na hora), retomar
- tt: publicar (creator_info → init → upload em pedaços → status), retomar
Erros de rede/servidor viram `Temporario` (o relógio tenta de novo em 1, 3 e 10 min); o resto vira `Falha`, com a
mensagem da plataforma traduzida quando dá.
"""
import fcntl
import hashlib
import json
import os
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parent.parent
CONTAS = ROOT / ".segredos" / "contas.json"
VOLTA = "http://localhost:8765/api/agenda/oauth/{k}"
YT_API = "https://www.googleapis.com/youtube/v3"
TT_API = "https://open.tiktokapis.com/v2"
# youtube.upload = subir (videos.insert, thumbnails.set); force-ssl = ver/atualizar (videos.update não aceita só upload)
YT_ESCOPOS = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]
# TikTok: "rascunho" (padrão) = na hora marcada o vídeo chega na caixa de entrada do app dele (video.upload) e ele toca em
# publicar; "direto" = publica sozinho (video.publish) — só sai público depois da auditoria do TikTok, que recusa app de
# uso pessoal (Content Sharing Guidelines: "Not acceptable: a utility tool to help upload contents to the account(s) you
# or your team manages"); sem auditoria, sai "Só eu" e a conta precisa estar privada.
TT_ESCOPOS = {"rascunho": ["user.info.basic", "video.upload"], "direto": ["user.info.basic", "video.upload", "video.publish"]}


class Temporario(Exception):
    """Falha passageira (sem internet, plataforma fora do ar, limite de requisições): tentar de novo resolve."""


class Falha(Exception):
    """Erro definitivo, com a explicação para ele."""


# ---------------------------------------------------------------- segredos
_tl = threading.RLock()
_local = threading.local()


@contextmanager
def _trava():
    """Um de cada vez lendo+gravando os segredos e renovando tokens (threads do relógio e outros processos). 03/11:
    5 envios do YouTube começaram juntos, renovaram o token ao mesmo tempo e se atropelaram no arquivo temporário — e no
    TikTok, onde cada renovação invalida a chave anterior, isso derrubaria a conexão. Reentrante na mesma thread."""
    if getattr(_local, "dentro", 0):
        _local.dentro += 1
        try:
            yield
        finally:
            _local.dentro -= 1
        return
    CONTAS.parent.mkdir(exist_ok=True)
    with _tl, open(CONTAS.with_suffix(".lock"), "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        _local.dentro = 1
        try:
            yield
        finally:
            _local.dentro = 0


def _ler():
    try:
        return json.loads(CONTAS.read_text())
    except (OSError, ValueError):
        return {}


def _gravar(d):
    CONTAS.parent.mkdir(exist_ok=True)
    tmp = CONTAS.with_name(f"contas.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    os.chmod(tmp, 0o600)
    tmp.replace(CONTAS)


def _conta(k):
    return _ler().get(k) or {}


def _salvar_conta(k, **campos):
    with _trava():
        d = _ler()
        d[k] = {**(d.get(k) or {}), **campos}
        _gravar(d)
        return d[k]


def _agora():
    return datetime.now(timezone.utc)


def _ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _dt(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if s else None


# ---------------------------------------------------------------- HTTP
def _http(metodo, url, ok=(200, 201), **kw):
    kw.setdefault("timeout", 60)
    try:
        r = requests.request(metodo, url, **kw)
    except (requests.ConnectionError, requests.Timeout) as ex:
        raise Temporario(f"sem conexão com {url.split('/')[2]} ({type(ex).__name__})")
    if r.status_code in ok:
        return r
    msg = _msg_erro(r)
    if r.status_code in (429, 500, 502, 503, 504):
        raise Temporario(msg)
    raise Falha(msg)


def _msg_erro(r):
    try:
        j = r.json()
    except ValueError:
        return f"HTTP {r.status_code}: {r.text[:300]}"
    e = j.get("error")
    if isinstance(e, dict):                      # Meta / Google / TikTok
        partes = [e.get("message") or e.get("error_user_msg") or "", e.get("code") and f"código {e.get('code')}" or ""]
        for x in (e.get("errors") or [])[:1]:
            partes.append(x.get("reason", ""))
        if e.get("log_id"):
            partes.append(f"log {e['log_id']}")
        return f"HTTP {r.status_code}: " + " · ".join(str(p) for p in partes if p)
    if isinstance(e, str):
        return f"HTTP {r.status_code}: {e} {j.get('error_description', '')}".strip()
    return f"HTTP {r.status_code}: {json.dumps(j)[:300]}"


def _json(r):
    try:
        return r.json()
    except ValueError:
        raise Falha(f"resposta inesperada: {r.text[:200]}")


# ---------------------------------------------------------------- status das contas (para a tela)
def status():
    d = _ler()
    out = {}
    agora = _agora()
    for k in ("ig", "yt", "tt"):
        c = d.get(k) or {}
        conectado = bool(c.get("token") or c.get("refresh_token"))
        st = {"conectado": conectado, "conta": c.get("conta") or "", "foto": c.get("foto") or "", "desde": c.get("desde") or "",
              "app": bool(c.get("client_id")), "client_id": c.get("client_id") or "", "avisos": []}
        exp = _dt(c.get("expira_longo") or "")
        if conectado and exp:
            st["expira"] = _ts(exp)
            if exp < agora:
                st["conectado"] = False
                st["avisos"].append("A conexão venceu: conecte de novo.")
            elif exp - agora < timedelta(days=7):
                st["avisos"].append(f"A conexão vence em {(exp - agora).days} dias (renovo sozinho se o servidor estiver aberto).")
        if k == "ig":
            st["modo"] = c.get("modo") or "facebook"
            st["pagina"] = c.get("pagina") or ""
        if k == "tt":
            st["modo"] = c.get("modo") or "rascunho"
            if conectado and st["modo"] == "direto" and not c.get("auditado"):
                st["avisos"].append("TikTok direto sem auditoria: só publica como “Só eu” e com a conta PRIVADA.")
        out[k] = st
    return out


def salvar_app(k, dados):
    """Credenciais do app de desenvolvedor (client id/secret) e, no Instagram, o token colado."""
    campos = {c: (dados.get(c) or "").strip() for c in ("client_id", "client_secret") if c in dados}
    if "auditado" in dados:
        campos["auditado"] = bool(dados["auditado"])
    if k == "tt" and dados.get("modo") in ("rascunho", "direto"):
        campos["modo"] = dados["modo"]
    if k == "ig" and dados.get("modo") in ("facebook", "instagram"):
        campos["modo"] = dados["modo"]
    if campos:
        _salvar_conta(k, **campos)
    if k == "ig" and (dados.get("token") or "").strip():
        return ig_conectar_token(dados["token"].strip(), modo=dados.get("modo"))
    return status()[k]


def desconectar(k):
    d = _ler()
    c = d.get(k) or {}
    d[k] = {x: c[x] for x in ("client_id", "client_secret", "auditado", "modo") if x in c}   # o app fica; o login sai
    _gravar(d)
    return status()[k]


# ---------------------------------------------------------------- OAuth (volta no próprio servidor local)
def oauth_inicio(k):
    c = _conta(k)
    if not c.get("client_id"):
        raise Falha("Primeiro salve o ID e o segredo do app.")
    estado = secrets.token_urlsafe(16)
    extra = {}
    if k == "yt":
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": c["client_id"], "redirect_uri": VOLTA.format(k=k), "response_type": "code",
            "scope": " ".join(YT_ESCOPOS), "access_type": "offline", "prompt": "consent", "state": estado})
    elif k == "tt":
        verif = secrets.token_urlsafe(48)
        extra["verificador"] = verif
        desafio = hashlib.sha256(verif.encode()).hexdigest()        # o TikTok usa o HEX do SHA256 (não base64url)
        url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
            "client_key": c["client_id"], "redirect_uri": VOLTA.format(k=k), "response_type": "code",
            "scope": ",".join(TT_ESCOPOS[tt_modo()]), "state": estado, "code_challenge": desafio,
            "code_challenge_method": "S256"})
    elif k == "ig":
        url = "https://www.instagram.com/oauth/authorize?" + urlencode({
            "client_id": c["client_id"], "redirect_uri": VOLTA.format(k=k), "response_type": "code",
            "scope": "instagram_business_basic,instagram_business_content_publish", "state": estado})
    else:
        raise KeyError(k)
    _salvar_conta(k, estado=estado, **extra)
    return url


def oauth_fim(k, params):
    c = _conta(k)
    if params.get("error"):
        raise Falha(f"{params.get('error')}: {params.get('error_description') or params.get('error_reason') or ''}")
    if not params.get("state") or params.get("state") != c.get("estado"):
        raise Falha("O pedido de conexão expirou ou não veio daqui. Clique em Conectar de novo.")
    code = params.get("code") or ""
    if k == "yt":
        j = _json(_http("POST", "https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": c["client_id"], "client_secret": c.get("client_secret", ""),
            "redirect_uri": VOLTA.format(k=k), "grant_type": "authorization_code"}))
        if not j.get("refresh_token"):
            raise Falha("O Google não mandou o token de longa duração: tire o acesso do app na sua conta Google e conecte de novo.")
        _salvar_conta(k, token=j["access_token"], refresh_token=j["refresh_token"],
                      expira=_ts(_agora() + timedelta(seconds=int(j.get("expires_in", 3600)) - 60)), desde=_ts(_agora()), estado="")
        ch = (_json(_http("GET", f"{YT_API}/channels", params={"part": "snippet", "mine": "true"},
                          headers=_yt_h())).get("items") or [{}])[0]
        sn = ch.get("snippet") or {}
        _salvar_conta(k, conta=(sn.get("customUrl") or sn.get("title") or ""), canal=ch.get("id", ""),
                      canal_nome=sn.get("title", ""), foto=((sn.get("thumbnails") or {}).get("default") or {}).get("url", ""))
    elif k == "tt":
        j = _json(_http("POST", f"{TT_API}/oauth/token/", data={
            "client_key": c["client_id"], "client_secret": c.get("client_secret", ""), "code": code,
            "grant_type": "authorization_code", "redirect_uri": VOLTA.format(k=k), "code_verifier": c.get("verificador", "")},
            headers={"Content-Type": "application/x-www-form-urlencoded"}))
        if not j.get("access_token"):
            raise Falha(f"O TikTok não devolveu o acesso: {j}")
        _tt_guardar(j)
        _salvar_conta(k, desde=_ts(_agora()), estado="", verificador="")
        tt_quem()                                     # nome e foto da conta ligada
    elif k == "ig":
        j = _json(_http("POST", "https://api.instagram.com/oauth/access_token", data={
            "client_id": c["client_id"], "client_secret": c.get("client_secret", ""), "grant_type": "authorization_code",
            "redirect_uri": VOLTA.format(k=k), "code": code.split("#")[0]}))
        longo = _json(_http("GET", "https://graph.instagram.com/access_token", params={
            "grant_type": "ig_exchange_token", "client_secret": c.get("client_secret", ""), "access_token": j["access_token"]}))
        ig_conectar_token(longo["access_token"], int(longo.get("expires_in") or 5184000), modo="instagram")
        _salvar_conta(k, estado="")
    return status()[k]


# ---------------------------------------------------------------- Instagram
# Dois jeitos de ligar (doc da Meta, 11/2026):
# - "facebook" (RECOMENDADO): o Instagram profissional ligado a uma Página do Facebook → graph.facebook.com com o
#   UPLOAD RETOMÁVEL do arquivo direto do Mac (rupload.facebook.com). Token: o do Graph API Explorer, trocado por um de
#   60 dias (renovo sozinho com o segredo do app).
# - "instagram" (login só do Instagram, token gerado no painel do app, 60 dias): a doc diz que o upload retomável é só
#   do login do Facebook — aqui a Meta quer um LINK PÚBLICO do vídeo. Tento o retomável mesmo assim; se a Meta recusar,
#   a mensagem explica como mudar para o jeito "facebook".
IG_VER = "v26.0"
IG_HOST = {"facebook": f"https://graph.facebook.com/{IG_VER}", "instagram": f"https://graph.instagram.com/{IG_VER}"}


def ig_conectar_token(token, expira_em=5184000, modo=None):
    c = _conta("ig")
    modo = modo or c.get("modo") or ("facebook" if token.startswith("EAA") else "instagram")
    if modo == "facebook":
        if c.get("client_id") and c.get("client_secret"):       # token curto do Explorer → 60 dias
            j = _json(_http("GET", f"{IG_HOST['facebook']}/oauth/access_token", params={
                "grant_type": "fb_exchange_token", "client_id": c["client_id"], "client_secret": c["client_secret"],
                "fb_exchange_token": token}))
            token, expira_em = j["access_token"], int(j.get("expires_in") or 5184000)
        pags = _json(_http("GET", f"{IG_HOST['facebook']}/me/accounts", params={
            "fields": "name,instagram_business_account{id,username,profile_picture_url}", "access_token": token})).get("data") or []
        ligada = next((p for p in pags if p.get("instagram_business_account")), None)
        if not ligada and not pags:
            raise Falha("O token não dá acesso a NENHUMA Página do Facebook. Gere de novo no Graph API Explorer: adicione "
                        "também a permissão business_management (Página no Meta Business Suite) e, na janela, marque a "
                        "Página ligada ao Instagram em “Escolher as Páginas”.")
        if not ligada:
            nomes = ", ".join(f"“{p.get('name', '?')}”" for p in pags)
            raise Falha(f"O token vê a(s) Página(s) {nomes}, mas nenhuma tem um Instagram profissional ligado. Ligue o "
                        "Instagram a essa Página (Meta Business Suite → Configurações → Contas → Instagram) ou marque a "
                        "Página certa ao gerar o token.")
        a = ligada["instagram_business_account"]
        _salvar_conta("ig", modo="facebook", token=token, user_id=a["id"], conta="@" + a.get("username", ""),
                      pagina=ligada.get("name", ""), foto=a.get("profile_picture_url", ""), desde=_ts(_agora()),
                      renovado=_ts(_agora()), expira_longo=_ts(_agora() + timedelta(seconds=expira_em)))
        return status()["ig"]
    j = _json(_http("GET", f"{IG_HOST['instagram']}/me", params={
        "fields": "user_id,username,account_type,profile_picture_url", "access_token": token}))
    if (j.get("account_type") or "").upper() not in ("", "BUSINESS", "MEDIA_CREATOR", "CREATOR"):
        raise Falha(f"A conta @{j.get('username')} é pessoal: mude para conta profissional (Criador ou Empresa) no app.")
    _salvar_conta("ig", modo="instagram", token=token, user_id=str(j.get("user_id") or j.get("id")),
                  conta="@" + j.get("username", ""), foto=j.get("profile_picture_url", ""), desde=_ts(_agora()),
                  renovado=_ts(_agora()), expira_longo=_ts(_agora() + timedelta(seconds=expira_em)))
    return status()["ig"]


def _ig():
    c = _conta("ig")
    if not c.get("token"):
        raise Falha("A conta do Instagram não está conectada (aba Contas da agenda).")
    return c["token"], c["user_id"], IG_HOST[c.get("modo") or "instagram"]


def ig_renovar(forcar=False):
    """Token de 60 dias: renova quando passou de 7 dias. O relógio chama de hora em hora."""
    c = _conta("ig")
    if not c.get("token"):
        return None
    feito = _dt(c.get("renovado") or "")
    if not forcar and feito and _agora() - feito < timedelta(days=7):
        return None
    if c.get("modo") == "facebook":
        if not (c.get("client_id") and c.get("client_secret")):
            return None
        j = _json(_http("GET", f"{IG_HOST['facebook']}/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": c["client_id"], "client_secret": c["client_secret"],
            "fb_exchange_token": c["token"]}))
    else:
        j = _json(_http("GET", "https://graph.instagram.com/refresh_access_token",
                        params={"grant_type": "ig_refresh_token", "access_token": c["token"]}))
    _salvar_conta("ig", token=j["access_token"], renovado=_ts(_agora()),
                  expira_longo=_ts(_agora() + timedelta(seconds=int(j.get("expires_in") or 5184000))))
    return True


def ig_preparar(ctx):
    """Cria o contêiner do Reel e sobe o arquivo (upload retomável direto do Mac)."""
    tok, uid, host = _ig()
    e, p = ctx.e, ctx.p
    o = e.get("opcoes") or {}
    dados = {"media_type": "REELS", "upload_type": "resumable", "caption": e.get("legenda") or "",
             "share_to_feed": "true" if o.get("share_to_feed", True) else "false",
             "thumb_offset": str(int(float(p.get("capa") or 0) * 1000)), "access_token": tok}
    if o.get("ia"):
        dados["is_ai_generated"] = "true"            # selo "Informações de IA"
    colab = [x.strip().lstrip("@") for x in (o.get("colaboradores") or "").replace(";", ",").split(",") if x.strip()]
    if colab:
        dados["collaborators"] = json.dumps(colab[:3])
    try:
        j = _json(_http("POST", f"{host}/{uid}/media", data=dados))
    except Falha as ex:
        if "video_url" in str(ex):
            raise Falha("O login só do Instagram não aceita enviar o arquivo do Mac (a Meta quer um link público). "
                        "Ligue o Instagram a uma Página do Facebook e conecte pelo jeito “Página do Facebook” (aba Contas).")
        raise
    cid = j["id"]
    uri = j.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{IG_VER}/{cid}"
    ctx.salvar("contêiner criado, subindo o vídeo", container=cid)
    tam = os.path.getsize(p["arquivo"])
    with open(p["arquivo"], "rb") as fh:
        _http("POST", uri, data=fh, timeout=1800,
              headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(tam)})
    from .agenda import _carimbo, _hora
    return {"status": "na_rede", "container": cid, "container_em": _carimbo(),
            "etapa": f"Vídeo já está no Instagram · sai {_hora(e['quando'])}"}


def _ig_container(cid, tok, host):
    return _json(_http("GET", f"{host}/{cid}", params={"fields": "status_code,status", "access_token": tok}))


def ig_publicar(ctx):
    tok, uid, host = _ig()
    cid = ctx.e.get("container")
    if not cid:
        return {"status": "agendado", "msg": "sem contêiner: envio de novo"}
    for _ in range(60):                                 # o Instagram processa o vídeo (em geral < 1 min)
        st = _ig_container(cid, tok, host)
        sc = st.get("status_code")
        if sc == "FINISHED":
            break
        if sc == "PUBLISHED":
            return _ig_achar_publicado(ctx, tok, uid, host)
        if sc == "EXPIRED":
            return {"status": "agendado", "container": "", "container_em": "", "msg": "contêiner venceu: envio de novo"}
        if sc == "ERROR":
            raise Falha(f"O Instagram recusou o vídeo: {st.get('status') or 'erro no processamento'}")
        ctx.vivo()
        time.sleep(15)
    else:
        raise Temporario("o Instagram ainda está processando o vídeo")
    j = _json(_http("POST", f"{host}/{uid}/media_publish", data={"creation_id": cid, "access_token": tok}))
    mid = j["id"]
    ctx.salvar("publicado, buscando o link", id_rede=mid)
    link = _json(_http("GET", f"{host}/{mid}", params={"fields": "permalink", "access_token": tok})).get("permalink", "")
    from .agenda import _carimbo
    return {"status": "publicado", "id_rede": mid, "url": link, "publicado_em": _carimbo(), "etapa": ""}


def _ig_achar_publicado(ctx, tok, uid, host):
    mid = ctx.e.get("id_rede")
    if not mid:
        lista = _json(_http("GET", f"{host}/{uid}/media", params={"fields": "id,caption,permalink,timestamp",
                                                                     "limit": 10, "access_token": tok})).get("data") or []
        leg = (ctx.e.get("legenda") or "").strip()[:80]
        m = next((x for x in lista if (x.get("caption") or "").strip()[:80] == leg), None)
        if not m:
            raise Falha("O contêiner consta como publicado, mas não achei o post: confira no Instagram.")
        mid = m["id"]
    link = _json(_http("GET", f"{host}/{mid}", params={"fields": "permalink,timestamp", "access_token": tok}))
    from .agenda import _carimbo
    return {"status": "publicado", "id_rede": mid, "url": link.get("permalink", ""), "publicado_em": _carimbo(), "etapa": ""}


def ig_retomar(ctx):
    tok, uid, host = _ig()
    cid = ctx.e.get("container")
    if not cid:
        return {"status": "agendado"}
    sc = _ig_container(cid, tok, host).get("status_code")
    if sc == "PUBLISHED":
        return _ig_achar_publicado(ctx, tok, uid, host)
    if sc in ("FINISHED", "IN_PROGRESS"):
        return {"status": "na_rede", "msg": "retomado: o vídeo já estava no Instagram"}
    return {"status": "agendado", "container": "", "container_em": "", "msg": "retomado: envio de novo"}


# ---------------------------------------------------------------- YouTube
def _yt_token():
    with _trava():                                    # uma renovação por vez; as outras threads reaproveitam o token novo
        c = _conta("yt")
        if not c.get("refresh_token"):
            raise Falha("A conta do YouTube não está conectada (aba Contas da agenda).")
        exp = _dt(c.get("expira") or "")
        if c.get("token") and exp and exp > _agora():
            return c["token"]
        j = _json(_http("POST", "https://oauth2.googleapis.com/token", data={
            "client_id": c["client_id"], "client_secret": c.get("client_secret", ""), "refresh_token": c["refresh_token"],
            "grant_type": "refresh_token"}))
        _salvar_conta("yt", token=j["access_token"], expira=_ts(_agora() + timedelta(seconds=int(j.get("expires_in", 3600)) - 60)))
        return j["access_token"]


def _yt_h(extra=None):
    return {"Authorization": f"Bearer {_yt_token()}", **(extra or {})}


def _yt_corpo(ctx, publicar_ja):
    from .agenda import quando_dt
    e = ctx.e
    o = e.get("opcoes") or {}
    tags = [t.strip().lstrip("#") for t in (o.get("tags") or "").split(",") if t.strip()]
    st = {"selfDeclaredMadeForKids": bool(o.get("kids")), "containsSyntheticMedia": bool(o.get("ia"))}
    if publicar_ja:
        st["privacyStatus"] = o.get("privacidade") or "public"
    else:
        st["privacyStatus"] = "private"
        st["publishAt"] = quando_dt(e["quando"]).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {"snippet": {"title": (e.get("titulo") or "").strip()[:100], "description": e.get("legenda") or "", "tags": tags,
                        "categoryId": str(o.get("categoria") or "27"), "defaultLanguage": "pt-BR",
                        "defaultAudioLanguage": "pt-BR"}, "status": st}


def _yt_ja(ctx):
    """Publica já (horário passou ou é daqui a 2 min) × agenda no YouTube (privado + publishAt)."""
    from .agenda import agora, quando_dt
    o = ctx.e.get("opcoes") or {}
    return (o.get("privacidade") or "public") != "public" or quando_dt(ctx.e["quando"]) <= agora() + timedelta(minutes=2)


def yt_subir(ctx):
    from .agenda import _carimbo, _hora
    if ctx.e.get("id_rede"):                          # já está no YouTube (foi cancelado e reagendado): só atualiza
        return yt_atualizar(ctx)
    ja = _yt_ja(ctx)
    corpo = _yt_corpo(ctx, ja)
    arq = ctx.p["arquivo"]
    tam = os.path.getsize(arq)
    r = _http("POST", "https://www.googleapis.com/upload/youtube/v3/videos",
              params={"uploadType": "resumable", "part": "snippet,status"}, json=corpo,
              headers=_yt_h({"X-Upload-Content-Length": str(tam), "X-Upload-Content-Type": "video/mp4"}))
    sessao = r.headers.get("Location")
    if not sessao:
        raise Falha("O YouTube não abriu a sessão de envio.")
    ctx.salvar("subindo para o YouTube", sessao_yt=sessao)
    v = _yt_enviar(ctx, sessao, arq, tam, 0)
    vid = v["id"]
    url = f"https://www.youtube.com/shorts/{vid}"
    if ja:
        return {"status": "publicado", "id_rede": vid, "url": url, "publicado_em": _carimbo(), "sessao_yt": "", "etapa": ""}
    return {"status": "na_rede", "id_rede": vid, "url": url, "sessao_yt": "", "capa_pendente": True,
            "etapa": f"No YouTube como privado · o YouTube publica sozinho {_hora(ctx.e['quando'])}"}


def yt_capa(ctx):
    """A capa escolhida vira a miniatura do Short (thumbnails.set; só depois de o YouTube processar o vídeo)."""
    import subprocess
    import tempfile
    from .media import FFMPEG
    v = (_json(_http("GET", f"{YT_API}/videos", params={"part": "processingDetails", "id": ctx.e["id_rede"]},
                     headers=_yt_h())).get("items") or [{}])[0]
    st = (v.get("processingDetails") or {}).get("processingStatus")
    if st == "processing":
        return {"status": "na_rede", "capa_pendente": True, "msg": "YouTube ainda processando: a capa entra depois"}
    if st != "succeeded":
        return {"status": "na_rede", "capa_pendente": False}
    from . import capas
    desenhada = capas.escolhida(ctx.p.get("code")) if ctx.p.get("code") else None
    with tempfile.TemporaryDirectory() as tmp:
        jpg = Path(tmp) / "capa.jpg"
        if desenhada:                                   # a capa com headline escolhida na aba Capas (app/capas.py)
            subprocess.run([FFMPEG, "-v", "error", "-y", "-i", desenhada, "-q:v", "3", str(jpg)], capture_output=True, timeout=60)
        else:                                           # senão, o quadro escolhido do vídeo
            subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{float(ctx.p.get('capa') or 1):.2f}", "-i", ctx.p["arquivo"],
                            "-frames:v", "1", "-q:v", "2", str(jpg)], capture_output=True, timeout=120)
        if not jpg.exists():
            return {"status": "na_rede", "capa_pendente": False, "msg": "capa não entrou (não consegui tirar o quadro do vídeo)"}
        try:
            _http("POST", "https://www.googleapis.com/upload/youtube/v3/thumbnails/set", params={"videoId": ctx.e["id_rede"]},
                  data=jpg.read_bytes(), headers=_yt_h({"Content-Type": "image/jpeg"}))
        except Falha as ex:                             # ex.: conta sem permissão de miniatura personalizada
            return {"status": "na_rede", "capa_pendente": False, "msg": f"capa não entrou ({ex})"}
    return {"status": "na_rede", "capa_pendente": False,
            "msg": "capa desenhada aplicada no Short" if desenhada else "capa do Short aplicada"}


def _yt_enviar(ctx, sessao, arq, tam, inicio):
    PEDACO = 16 * 1024 * 1024                          # múltiplo de 256 KB
    with open(arq, "rb") as fh:
        pos = inicio
        while pos < tam:
            fh.seek(pos)
            bloco = fh.read(PEDACO)
            fim = pos + len(bloco) - 1
            r = _http("PUT", sessao, ok=(200, 201, 308), data=bloco, timeout=600,
                      headers={"Authorization": f"Bearer {_yt_token()}", "Content-Length": str(len(bloco)),
                               "Content-Range": f"bytes {pos}-{fim}/{tam}"})
            if r.status_code in (200, 201):
                return _json(r)
            faixa = r.headers.get("Range")                 # 308: até onde o YouTube recebeu
            pos = int(faixa.split("-")[1]) + 1 if faixa else 0
            ctx.salvar(f"YouTube: {pos * 100 // tam}% enviado")
    raise Temporario("o envio para o YouTube não terminou")


def yt_retomar(ctx):
    if ctx.e.get("id_rede"):
        return {"status": "na_rede", "msg": "retomado: o vídeo já estava no YouTube"}
    sessao = ctx.e.get("sessao_yt")
    if sessao:
        tam = os.path.getsize(ctx.p["arquivo"])
        r = _http("PUT", sessao, ok=(200, 201, 308, 404, 410), data=b"",
                  headers={"Authorization": f"Bearer {_yt_token()}", "Content-Range": f"bytes */{tam}", "Content-Length": "0"})
        if r.status_code in (200, 201):
            vid = _json(r)["id"]
            return {"status": "na_rede", "id_rede": vid, "url": f"https://www.youtube.com/shorts/{vid}", "sessao_yt": "",
                    "msg": "retomado: o envio já tinha terminado"}
        if r.status_code == 308:
            faixa = r.headers.get("Range")
            inicio = int(faixa.split("-")[1]) + 1 if faixa else 0
            v = _yt_enviar(ctx, sessao, ctx.p["arquivo"], tam, inicio)
            from .agenda import _hora
            return {"status": "na_rede", "id_rede": v["id"], "url": f"https://www.youtube.com/shorts/{v['id']}", "sessao_yt": "",
                    "etapa": f"No YouTube como privado · o YouTube publica sozinho {_hora(ctx.e['quando'])}"}
    return {"status": "agendado", "sessao_yt": "", "msg": "retomado: subo de novo"}


def yt_atualizar(ctx):
    from .agenda import _carimbo, _hora
    vid = ctx.e["id_rede"]
    ja = _yt_ja(ctx)
    corpo = _yt_corpo(ctx, ja)
    corpo["id"] = vid
    _http("PUT", f"{YT_API}/videos", params={"part": "snippet,status"}, json=corpo, headers=_yt_h())
    if ja:
        return {"status": "publicado", "atualizar": False, "cancelar": False, "publicado_em": _carimbo(), "etapa": ""}
    return {"status": "na_rede", "atualizar": False, "cancelar": False,
            "etapa": f"No YouTube como privado · o YouTube publica sozinho {_hora(ctx.e['quando'])}",
            "msg": "atualizado no YouTube"}


def yt_cancelar(ctx):
    """Tira o agendamento: o vídeo fica PRIVADO no YouTube Studio (nada é apagado)."""
    vid = ctx.e["id_rede"]
    o = ctx.e.get("opcoes") or {}
    _http("PUT", f"{YT_API}/videos", params={"part": "status"}, headers=_yt_h(),
          json={"id": vid, "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": bool(o.get("kids"))}})
    return {"status": "rascunho", "cancelar": False, "etapa": "", "msg": "desagendado: ficou privado no YouTube Studio"}


def yt_conferir(ctx):
    from .agenda import _carimbo, agora, quando_dt
    v = (_json(_http("GET", f"{YT_API}/videos", params={"part": "status", "id": ctx.e["id_rede"]},
                     headers=_yt_h())).get("items") or [None])[0]
    if not v:
        raise Falha("O vídeo não está mais no YouTube (foi apagado no Studio?).")
    st = v["status"]
    if st.get("uploadStatus") in ("rejected", "failed", "deleted"):
        raise Falha(f"O YouTube recusou o vídeo: {st.get('rejectionReason') or st.get('failureReason') or st.get('uploadStatus')}")
    if st.get("privacyStatus") == "public":
        return {"status": "publicado", "publicado_em": _carimbo(), "etapa": ""}
    if agora() - quando_dt(ctx.e["quando"]) > timedelta(minutes=20):
        raise Falha("Passou do horário e o YouTube manteve o vídeo PRIVADO — o projeto do Google ainda não foi aprovado "
                    "na auditoria da API (vídeos enviados por app não auditado ficam privados). Publique no YouTube Studio.")
    return {}


# ---------------------------------------------------------------- TikTok
def tt_modo():
    return _conta("tt").get("modo") or "rascunho"


def _tt_guardar(j):
    """O refresh token do TikTok GIRA: cada renovação devolve um novo e invalida o anterior — guarda sempre o novo."""
    c = _conta("tt")
    _salvar_conta("tt", token=j["access_token"], refresh_token=j.get("refresh_token") or c.get("refresh_token", ""),
                  open_id=j.get("open_id") or c.get("open_id", ""),
                  expira=_ts(_agora() + timedelta(seconds=int(j.get("expires_in", 7200)) - 120)),
                  expira_longo=_ts(_agora() + timedelta(seconds=int(j.get("refresh_expires_in", 15552000)))))


def _tt_token():
    with _trava():                                    # o refresh token do TikTok GIRA: duas renovações juntas derrubam a conexão
        c = _conta("tt")
        if not c.get("refresh_token"):
            raise Falha("A conta do TikTok não está conectada (aba Contas da agenda).")
        exp = _dt(c.get("expira") or "")
        if c.get("token") and exp and exp > _agora():
            return c["token"]
        j = _json(_http("POST", f"{TT_API}/oauth/token/", data={
            "client_key": c["client_id"], "client_secret": c.get("client_secret", ""), "grant_type": "refresh_token",
            "refresh_token": c["refresh_token"]}, headers={"Content-Type": "application/x-www-form-urlencoded"}))
        if not j.get("access_token"):
            raise Falha(f"O TikTok recusou renovar a conexão (conecte de novo): {j.get('error_description') or j}")
        _tt_guardar(j)
        return j["access_token"]


TT_ERROS = {
    "unaudited_client_can_only_post_to_private_accounts": "App ainda não auditado pelo TikTok: só publica direto em conta "
    "PRIVADA e como “Só eu”. Use o modo rascunho (o vídeo chega no seu app e você toca em publicar).",
    "privacy_level_option_mismatch": "A privacidade escolhida não é permitida para esta conta agora.",
    "spam_risk_too_many_posts": "O TikTok bloqueou por excesso de posts hoje (limite ~15/dia). Tente amanhã.",
    "spam_risk_too_many_pending_share": "Já há 5 vídeos esperando na sua caixa de entrada do TikTok (limite de 24 h): "
    "publique ou descarte algum no app.",
    "reached_active_user_cap": "O app atingiu o limite diário de contas do TikTok. Tente amanhã.",
    "access_token_invalid": "A conexão com o TikTok caiu: conecte de novo na aba Contas.",
    "scope_not_authorized": "O app do TikTok não tem a permissão para isso (confira os produtos/escopos no painel).",
}


def _tt(metodo, caminho, **kw):
    try:
        r = requests.request(metodo, f"{TT_API}{caminho}", timeout=60, headers={
            "Authorization": f"Bearer {_tt_token()}", "Content-Type": "application/json; charset=UTF-8"}, **kw)
    except (requests.ConnectionError, requests.Timeout) as ex:
        raise Temporario(f"sem conexão com o TikTok ({type(ex).__name__})")
    try:
        j = r.json()
    except ValueError:
        raise Temporario(f"TikTok: HTTP {r.status_code}") if r.status_code >= 500 else Falha(f"TikTok: HTTP {r.status_code}")
    err = j.get("error") or {}
    cod = err.get("code")
    if cod not in (None, "ok") or r.status_code >= 400:
        if r.status_code in (429, 500, 502, 503, 504) or cod in ("rate_limit_exceeded", "internal_error"):
            raise Temporario(f"TikTok: {err.get('message') or cod or r.status_code}")
        raise Falha(TT_ERROS.get(cod) or f"TikTok: {err.get('message') or cod} ({cod}, log {err.get('log_id', '')})")
    return j.get("data") or {}


def tt_quem():
    """Nome e foto da conta ligada (user.info.basic); no modo direto, também o @ e o que a conta permite agora."""
    d = _tt("GET", "/user/info/", params={"fields": "open_id,display_name,avatar_url"})
    u = d.get("user") or {}
    _salvar_conta("tt", nome=u.get("display_name", ""), conta=_conta("tt").get("conta") or u.get("display_name", ""),
                  foto=u.get("avatar_url", ""))
    if tt_modo() == "direto":
        tt_creator()


def tt_creator():
    """creator_info (só no modo direto, escopo video.publish): @, privacidades permitidas, duração máxima."""
    d = _tt("POST", "/post/publish/creator_info/query/", json={})
    _salvar_conta("tt", conta="@" + (d.get("creator_username") or ""), nome=d.get("creator_nickname", ""),
                  foto=d.get("creator_avatar_url", ""), privacidades=d.get("privacy_level_options") or [],
                  dur_max=d.get("max_video_post_duration_sec"))
    return d


def _tt_pedacos(tam):
    """Regra do TikTok: pedaços de 5–64 MB, o último leva o resto (até 128 MB); total = tamanho // pedaço."""
    if tam <= 60_000_000:
        return tam, 1
    pedaco = 20_000_000
    return pedaco, tam // pedaco


def _tt_subir(ctx, up, tam, pedaco, n):
    with open(ctx.p["arquivo"], "rb") as fh:
        for i in range(n):
            ini = i * pedaco
            fim = tam - 1 if i == n - 1 else ini + pedaco - 1
            fh.seek(ini)
            bloco = fh.read(fim - ini + 1)
            _http("PUT", up, ok=(200, 201, 206), data=bloco, timeout=600,
                  headers={"Content-Type": "video/mp4", "Content-Length": str(len(bloco)),
                           "Content-Range": f"bytes {ini}-{fim}/{tam}"})
            ctx.salvar(f"TikTok: {(fim + 1) * 100 // tam}% enviado")


def tt_publicar(ctx):
    """Na hora marcada. Rascunho: manda para a caixa de entrada do app (a legenda vai para a área de transferência do
    Mac e na notificação). Direto: publica (creator_info → init com legenda/privacidade → upload → status)."""
    from .agenda import _carimbo, avisar
    e, p = ctx.e, ctx.p
    o = e.get("opcoes") or {}
    tam = os.path.getsize(p["arquivo"])
    pedaco, n = _tt_pedacos(tam)
    fonte = {"source": "FILE_UPLOAD", "video_size": tam, "chunk_size": pedaco, "total_chunk_count": n}
    if tt_modo() == "rascunho":
        d = _tt("POST", "/post/publish/inbox/video/init/", json={"source_info": fonte})
        ctx.salvar("subindo para a caixa de entrada do TikTok", publish_id=d["publish_id"])
        _tt_subir(ctx, d["upload_url"], tam, pedaco, n)
        r = _tt_esperar(ctx, d["publish_id"], _carimbo, ate_caixa=True)
        if r.get("status") == "na_rede":
            _copiar(e.get("legenda") or "")
            avisar("TikTok: vídeo na sua caixa de entrada", f"{p.get('code') or p.get('nome')} — abra o TikTok, toque na "
                   "notificação e cole a legenda (já está copiada).")
        return r
    info = tt_creator()
    priv = o.get("privacidade") or ""
    opcoes = info.get("privacy_level_options") or []
    if priv not in opcoes:
        raise Falha(f"O TikTok não deixa publicar como “{priv}” nesta conta agora (permitido: {', '.join(opcoes) or 'nada'}).")
    if info.get("max_video_post_duration_sec"):
        from .agenda import info_arquivo
        dur = (info_arquivo(p["arquivo"]) or {}).get("dur") or 0
        if dur > info["max_video_post_duration_sec"]:
            raise Falha(f"O vídeo tem {dur:.0f} s e esta conta do TikTok aceita até {info['max_video_post_duration_sec']} s.")
    d = _tt("POST", "/post/publish/video/init/", json={
        "post_info": {"title": e.get("legenda") or "", "privacy_level": priv,
                      "disable_comment": not o.get("comentarios", True), "disable_duet": not o.get("duet", True),
                      "disable_stitch": not o.get("stitch", True),
                      "video_cover_timestamp_ms": int(float(p.get("capa") or 0) * 1000),
                      "brand_content_toggle": False, "brand_organic_toggle": bool(o.get("marca")), "is_aigc": bool(o.get("ia"))},
        "source_info": fonte})
    ctx.salvar("subindo para o TikTok", publish_id=d["publish_id"])
    _tt_subir(ctx, d["upload_url"], tam, pedaco, n)
    return _tt_esperar(ctx, d["publish_id"], _carimbo)


def _copiar(texto):
    try:
        import subprocess
        subprocess.run(["pbcopy"], input=texto.encode("utf-8"), timeout=5)
    except OSError:
        pass


def _tt_concluido(d, pid, _carimbo):
    ids = d.get("publicaly_available_post_id") or []
    conta = (_conta("tt").get("conta") or "").lstrip("@")
    url = f"https://www.tiktok.com/@{conta}/video/{ids[0]}" if ids and conta and " " not in conta else ""
    return {"status": "publicado", "id_rede": str(ids[0]) if ids else pid, "url": url, "publicado_em": _carimbo(),
            "etapa": "" if url else "publicado (o link aparece no app)"}


def _tt_esperar(ctx, pid, _carimbo, ate_caixa=False):
    for _ in range(60):
        d = _tt("POST", "/post/publish/status/fetch/", json={"publish_id": pid})
        st = d.get("status")
        if st == "PUBLISH_COMPLETE":
            return _tt_concluido(d, pid, _carimbo)
        if st == "SEND_TO_USER_INBOX" and ate_caixa:
            return {"status": "na_rede", "etapa": "Na caixa de entrada do seu TikTok: toque na notificação, cole a legenda "
                    "e publique (eu confiro e marco aqui quando sair)"}
        if st == "FAILED":
            raise Falha(f"O TikTok recusou o vídeo: {d.get('fail_reason') or 'falhou'}")
        ctx.vivo()
        time.sleep(10)
    raise Temporario("o TikTok ainda está processando o vídeo")


def tt_conferir(ctx):
    """Rascunho na caixa de entrada: vira "publicado" quando ele publica pelo app."""
    from .agenda import _carimbo
    d = _tt("POST", "/post/publish/status/fetch/", json={"publish_id": ctx.e.get("publish_id")})
    if d.get("status") == "PUBLISH_COMPLETE":
        return _tt_concluido(d, ctx.e.get("publish_id"), _carimbo)
    if d.get("status") == "FAILED":
        raise Falha(f"O TikTok recusou o vídeo: {d.get('fail_reason') or 'falhou'}")
    return {}


def tt_retomar(ctx):
    from .agenda import _carimbo
    pid = ctx.e.get("publish_id")
    if not pid:
        return {"status": "agendado"}
    d = _tt("POST", "/post/publish/status/fetch/", json={"publish_id": pid})
    st = d.get("status")
    if st == "PUBLISH_COMPLETE":
        return _tt_concluido(d, pid, _carimbo)
    if st == "SEND_TO_USER_INBOX":
        return {"status": "na_rede", "etapa": "Na caixa de entrada do seu TikTok: toque na notificação e publique"}
    if st == "PROCESSING_UPLOAD" and d.get("uploaded_bytes"):
        return _tt_esperar(ctx, pid, _carimbo, ate_caixa=tt_modo() == "rascunho")
    return {"status": "agendado", "publish_id": "", "msg": "retomado: o envio não terminou, mando de novo"}


# ---------------------------------------------------------------- o que o relógio chama
ACOES = {
    ("yt", "subir"): yt_subir, ("yt", "atualizar"): yt_atualizar, ("yt", "conferir"): yt_conferir,
    ("yt", "cancelar"): yt_cancelar, ("yt", "retomar"): yt_retomar, ("yt", "capa"): yt_capa,
    ("ig", "preparar"): ig_preparar, ("ig", "publicar"): ig_publicar, ("ig", "retomar"): ig_retomar,
    ("tt", "publicar"): tt_publicar, ("tt", "conferir"): tt_conferir, ("tt", "retomar"): tt_retomar,
}


def executar(k, acao, ctx):
    fn = ACOES.get((k, acao))
    if not fn:
        raise Falha(f"ação desconhecida {k}/{acao}")
    return fn(ctx)


def manutencao():
    """Renova o token do Instagram (60 dias) antes de vencer. Chamado pelo relógio de hora em hora."""
    try:
        ig_renovar()
    except (Falha, Temporario):
        pass
