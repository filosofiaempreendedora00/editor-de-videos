// AGENDA DE PUBLICAÇÕES (03/11) — calendário + "o que foi postado" + contas, para Instagram (Reels), YouTube Shorts e
// TikTok. Quem publica é o relógio do servidor (app/agenda.py); esta tela só marca o quê, onde e quando.
// Usa $, $$, api, toast, esc, show e RT_CANAIS de app.js (carregado depois; tudo aqui roda só dentro de funções).
const AG_ST = {
  rascunho: 'Rascunho', agendado: 'Agendado', enviando: 'Subindo…', publicado: 'Publicado', erro: 'Erro', atrasado: 'Atrasado',
  na_rede: { yt: 'No YouTube · publica sozinho', ig: 'Pronto no Instagram', tt: 'Na caixa do TikTok' },
};
const AG_ICO = { rascunho: '○', agendado: '◷', enviando: '↑', na_rede: '◉', publicado: '✓', erro: '!', atrasado: '!' };
const ag = { tab: 'cal', mes: null, dados: null, prontos: [], sel: null, poll: null, bound: false, escolher: null, arquivos: null };

const agRede = k => RT_CANAIS.find(c => c.k === k);
const agSvg = k => `<svg viewBox="0 0 24 24" aria-hidden="true">${agRede(k).svg}</svg>`;
const agDia = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const agStLabel = (st, k) => (st === 'na_rede' ? AG_ST.na_rede[k] : AG_ST[st]) || st;
function agHora(q) {
  if (!q) return '—';
  const d = new Date(q);
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}
function agPadrao(dia) {               // dia clicado (ou amanhã) às 18:00
  const d = dia ? new Date(dia + 'T18:00') : new Date(Date.now() + 86400000);
  return `${agDia(d)}T18:00`;
}

async function loadAgenda(tab) {
  show('agenda');
  history.replaceState(null, '', '#agenda');
  if (tab) { ag.tab = tab; ag.capasFeitas = false; ag.dashFeito = false; }
  if (!ag.mes) { const d = new Date(); ag.mes = new Date(d.getFullYear(), d.getMonth(), 1); }
  agBind();
  $$('#ag-tabs button').forEach(b => b.classList.toggle('on', b.dataset.ag === ag.tab));
  $$('.ag-pane').forEach(p => p.classList.toggle('hidden', p.id !== 'ag-' + ag.tab));
  await agRefresh();
}

async function agRefresh() {
  clearTimeout(ag.poll);
  try {
    const [d, pr] = await Promise.all([api('/api/agenda'), api('/api/agenda/prontos')]);
    ag.dados = d; ag.prontos = pr;
    agRelogio();
    if (ag.tab === 'cal') agCal();
    else if (ag.tab === 'central') agCentral(await api('/api/agenda/central'));
    else if (ag.tab === 'dash') { if (!ag.dashFeito) { ag.dashFeito = true; agDash(await api('/api/desempenho')); } }
    else if (ag.tab === 'capas') { if (!ag.capaSel && !ag.capasFeitas) { agCapas(await api('/api/capas')); ag.capasFeitas = true; } }
    else if (!ag.sel && !agContasEditando()) agContas();   // não redesenha com ele digitando (apagava o que ele colou)
    if (ag.sel) agStatusAtualiza();
  } catch (e) { toast('Agenda: ' + e.message, true); }
  if (!$('#agenda').classList.contains('hidden')) ag.poll = setTimeout(agRefresh, 15000);
}

function agRelogio() {
  const r = ag.dados.relogio || {};
  const el = $('#ag-relogio');
  el.className = 'ag-relogio ' + (r.vivo ? 'on' : 'off');
  el.innerHTML = r.vivo ? `<i></i>publicador ligado${r.acordado ? ' · Mac acordado para publicar' : ''}`
    : '<i></i>publicador desligado: abra o servidor do editor';
  el.title = r.vivo ? `Confere a agenda a cada 30 s (última: ${(r.ultima || '').slice(11, 16)}). Enquanto houver Instagram/TikTok nas próximas 12 h, o Mac não dorme sozinho — mas com a tampa fechada na bateria ele dorme.` : '';
}

// ---------------------------------------------------------------- calendário
function agEventos() {
  const out = {};
  for (const p of ag.dados.posts) {
    for (const [k, e] of Object.entries(p.redes)) {
      if (!e.quando || (!e.on && e.status === 'rascunho')) continue;
      (out[e.quando.slice(0, 10)] ||= []).push({ p, k, e });
    }
  }
  Object.values(out).forEach(l => l.sort((a, b) => a.e.quando.localeCompare(b.e.quando)));
  return out;
}

function agChip({ p, k, e }) {
  const mov = !['publicado', 'enviando'].includes(e.status);
  return `<div class="ag-ev ${k} st-${e.status}" data-aid="${p.id}" data-k="${k}" ${mov ? 'draggable="true"' : ''}
      title="${esc(agRede(k).nome)} · ${esc(p.code || p.nome)} · ${esc(agStLabel(e.status, k))}${e.erro ? ' — ' + esc(e.erro) : ''}">
    ${agSvg(k)}<b>${e.quando.slice(11, 16)}</b><span>${esc(p.code || p.nome)}</span><i>${AG_ICO[e.status] || ''}</i></div>`;
}

function agCal() {
  const m = ag.mes;
  const mes = m.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
  $('#ag-mes').textContent = mes.charAt(0).toUpperCase() + mes.slice(1);
  $('#ag-legenda').innerHTML = ['agendado', 'na_rede', 'publicado', 'erro'].map(st =>
    `<span class="ag-lg st-${st}"><i>${AG_ICO[st]}</i>${st === 'na_rede' ? 'já na rede' : AG_ST[st].toLowerCase()}</span>`).join('');
  const ini = new Date(m.getFullYear(), m.getMonth(), 1 - m.getDay());
  const ult = new Date(m.getFullYear(), m.getMonth() + 1, 0);
  const semanas = Math.ceil((m.getDay() + ult.getDate()) / 7);
  const evs = agEventos();
  const hoje = agDia(new Date());
  let html = '';
  for (let i = 0; i < semanas * 7; i++) {
    const d = new Date(ini.getFullYear(), ini.getMonth(), ini.getDate() + i);
    const dia = agDia(d);
    const lista = evs[dia] || [];
    html += `<div class="ag-day ${d.getMonth() !== m.getMonth() ? 'out' : ''} ${dia === hoje ? 'today' : ''} ${dia < hoje ? 'past' : ''}" data-day="${dia}">
      <div class="ag-dn"><span>${d.getDate()}</span>${dia >= hoje ? `<button class="ag-add" data-add-day="${dia}" title="Agendar neste dia">＋</button>` : ''}</div>
      <div class="ag-evs">${lista.map(agChip).join('')}</div></div>`;
  }
  $('#ag-grid').innerHTML = html;
  $('#ag-grid').style.gridTemplateRows = `repeat(${semanas}, minmax(112px, 1fr))`;
  agProntos();
}

function agEstadoCode(code) {
  // por rede: publicado / agendado / nao — junta o kanban (Instagram = coluna Publicado; Shorts/TikTok = checkzinho) e a agenda
  const r = ag.prontos.find(x => x.code === code) || {};
  const out = { ig: ['publicado', 'destaque'].includes(r.status) ? 'publicado' : 'nao', yt: r.canais?.yt ? 'publicado' : 'nao', tt: r.canais?.tt ? 'publicado' : 'nao' };
  for (const p of ag.dados.posts.filter(p => p.code === code)) {
    for (const [k, e] of Object.entries(p.redes)) {
      if (e.status === 'publicado') out[k] = 'publicado';
      else if (['agendado', 'enviando', 'na_rede'].includes(e.status) && out[k] !== 'publicado') out[k] = 'agendado';
    }
  }
  return out;
}

function agProntos() {
  const lista = ag.prontos.map(r => ({ ...r, est: agEstadoCode(r.code) }))
    .map(r => ({ ...r, faltam: Object.entries(r.est).filter(([, v]) => v === 'nao').map(([k]) => k) }))
    .sort((a, b) => b.faltam.length - a.faltam.length);
  $('#ag-prontos').innerHTML = lista.map(r => `
    <div class="ag-pr ${r.faltam.length ? '' : 'done'}" draggable="true" data-code="${esc(r.code)}" title="Arraste para um dia do calendário">
      ${r.thumb ? `<img src="/api/agenda-capas/${r.thumb}" alt="">` : '<div class="ag-pr-ph">▶</div>'}
      <div class="ag-pr-t"><span class="rt-code">${esc(r.code)}</span><b>${esc(r.title)}</b>
        <div class="ag-dots">${['ig', 'yt', 'tt'].map(k => `<span class="ag-dot ${k} ${r.est[k]}" title="${esc(agRede(k).nome)}: ${r.est[k] === 'publicado' ? 'publicado' : r.est[k] === 'agendado' ? 'agendado' : 'ainda não'}">${agSvg(k)}</span>`).join('')}</div>
      </div></div>`).join('') || '<p class="ag-vazio">Nenhum vídeo editado ainda.</p>';
}

// ---------------------------------------------------------------- o que foi postado (central)
function agCentral(c) {
  const nomes = { ig: 'Instagram', yt: 'YouTube Shorts', tt: 'TikTok' };
  const cel = (ln, k) => {
    const x = ln.redes[k];
    if (x.estado === 'publicado') {
      const quando = x.publicado_em ? agHora(x.publicado_em) : '';
      const quem = x.fonte === 'kanban' ? 'pelo kanban' : x.fonte === 'marcado no card' ? 'marcado no card' : x.manual ? 'postado à mão' : quando;
      return `<td class="ag-c ok">${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">✓ No ar ↗</a>` : '<span>✓ No ar</span>'}<small>${esc(quem)}</small></td>`;
    }
    if (['agendado', 'enviando', 'na_rede'].includes(x.estado))
      return `<td class="ag-c ag" data-open="${x.aid}"><span>◷ ${agHora(x.quando)}</span><small>${esc(agStLabel(x.estado, k))}</small></td>`;
    if (['erro', 'atrasado'].includes(x.estado))
      return `<td class="ag-c err" data-open="${x.aid}"><span>! ${esc(AG_ST[x.estado])}</span><small>${esc((x.erro || '').slice(0, 70))}</small></td>`;
    return `<td class="ag-c no"><span>— não postado</span>${ln.code ? `<div class="ag-c-acts"><button data-agendar-code="${esc(ln.code)}" data-k="${k}">Agendar</button><button data-ja="${esc(ln.code)}" data-k="${k}">Já postei</button></div>` : ''}</td>`;
  };
  $('#ag-central').innerHTML = `
    <div class="ag-resumo">${Object.entries(c.resumo).map(([k, r]) => `<div class="ag-rs ${k}">${agSvg(k)}<div><b>${nomes[k]}</b>
      <span><em>${r.publicado}</em> no ar · <em>${r.agendado}</em> agendado${r.agendado === 1 ? '' : 's'} · <em>${r.nao}</em> faltando</span></div></div>`).join('')}</div>
    <div class="rf-card ag-tabela"><table>
      <thead><tr><th>Vídeo</th>${Object.keys(nomes).map(k => `<th>${agSvg(k)} ${nomes[k]}</th>`).join('')}</tr></thead>
      <tbody>${c.linhas.map(ln => `<tr>
        <td class="ag-vid"><span class="rt-code">${esc(ln.code || '—')}</span><b>${esc(ln.title || '')}</b><small>${esc({ editado: 'editado', publicado: 'publicado', destaque: '✦ destaque' }[ln.card] || '')}</small></td>
        ${['ig', 'yt', 'tt'].map(k => cel(ln, k)).join('')}</tr>`).join('')}</tbody></table></div>`;
}

// ---------------------------------------------------------------- dashboard: cada vídeo × as 3 redes
const AD_REDES = ['ig', 'yt', 'tt'];
const adNum = n => (n === null || n === undefined ? '—' : Number(n).toLocaleString('pt-BR'));
const adCurt = n => `${adNum(n)} curtida${n === 1 ? '' : 's'}`;
const adQuando = q => (q ? new Date(q).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) : '');

function agDash(d) {
  ag.dash = d;
  const ord = ag.dashOrdem || (ag.dashOrdem = { col: 'total', dir: -1 });
  const valor = ln => (ord.col === 'total' ? ln.total : ln.redes[ord.col].views);
  const linhas = [...d.linhas].sort((a, b) => ((valor(a) ?? -1) - (valor(b) ?? -1)) * ord.dir);
  const th = (col, html) => `<th class="ad-n ${ord.col === col ? 'on' : ''}" data-ordem="${col}" aria-sort="${ord.col === col ? 'descending' : 'none'}">${html}${ord.col === col ? (ord.dir < 0 ? ' ↓' : ' ↑') : ''}</th>`;
  const cabec = k => `<i class="ad-cor ${k}"></i>${agSvg(k)} ${esc(k === 'yt' ? 'Shorts' : agRede(k).nome)}`;
  const celula = (ln, k) => {
    const c = ln.redes[k];
    if (c.estado === 'ok') return `<td class="ad-n"><b>${adNum(c.views)}</b>${c.manual ? '<small>digitado</small>' : c.curtidas != null ? `<small>${adCurt(c.curtidas)}</small>` : ''}</td>`;
    if (c.estado === 'sem_views') return `<td class="ad-n ad-falta" title="O post foi achado, mas esta conexão ainda não lê as views"><b>—</b><small>${adCurt(c.curtidas)}</small></td>`;
    if (c.estado === 'agendado') return `<td class="ad-n ad-falta"><b>◷</b><small>sai ${adQuando(c.quando)}</small></td>`;
    if (c.estado === 'sem_dados') return `<td class="ad-n ad-falta"><b>—</b><small>sem dados</small></td>`;
    return '<td class="ad-n ad-falta"><b>—</b><small>não postado</small></td>';
  };
  const barra = ln => {
    const fatias = AD_REDES.filter(k => ln.redes[k].views > 0);
    if (!fatias.length) return '';
    return `<div class="ad-barra" role="img" aria-label="${fatias.map(k => `${agRede(k).nome}: ${adNum(ln.redes[k].views)}`).join(', ')}">${fatias.map(k => `<i class="ad-cor ${k}" style="flex:${ln.redes[k].views} 0 0" title="${esc(agRede(k).nome)}: ${adNum(ln.redes[k].views)} views"></i>`).join('')}</div>`;
  };
  const ficha = (ln, k) => {
    const c = ln.redes[k];
    const itens = [['Views', c.views], ['Alcance', c.alcance], ['Curtidas', c.curtidas], ['Comentários', c.comentarios], ['Compartilhamentos', c.compart], ['Salvamentos', c.salvos]]
      .filter(([, v]) => v !== null && v !== undefined);
    return `<section class="ad-ficha">
      <h4><i class="ad-cor ${k}"></i>${agSvg(k)} ${esc(agRede(k).nome)}${c.quando && c.estado !== 'agendado' ? `<small>${adQuando(c.quando)}</small>` : ''}</h4>
      ${itens.length ? `<dl>${itens.map(([n, v]) => `<div><dt>${n}</dt><dd>${adNum(v)}</dd></div>`).join('')}</dl>` : '<p class="ad-vazio">Sem números desta rede por enquanto.</p>'}
      <div class="ad-ficha-acts">
        ${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">Abrir o post ↗</a>` : ''}
        ${c.id ? `<button data-soltar="${k}:${esc(c.id)}">Não é este post</button>` : ''}
      </div>
      ${c.manual || c.views === null || c.views === undefined ? `<label class="ad-mao">Views à mão
        <input inputmode="numeric" data-mao="${k}" data-code="${esc(ln.code)}" value="${c.manual ? c.views : ''}" placeholder="0"></label>` : ''}
    </section>`;
  };
  const faltam = AD_REDES.filter(k => ['falta', 'erro'].includes(d.redes[k].estado));
  const aviso = k => {
    const r = d.redes[k];
    if (r.estado === 'erro') return `<div class="ad-aviso"><b>${agSvg(k)} ${esc(r.nome)}: não consegui atualizar agora</b><p>${esc(r.msg)}</p></div>`;
    if (k === 'ig') return `<div class="ad-aviso"><b>${agSvg(k)} Instagram: falta 1 permissão para ler as views</b>
      <p>Já leio curtidas e comentários. Para as views, abra o Graph API Explorer, mantenha as permissões que já estão lá, adicione <code>instagram_manage_insights</code>, clique em <b>Generate Access Token</b>, escolha a sua Página e cole o token na aba <b>Contas</b>.</p>
      <div class="ad-aviso-acts"><a class="rf-btn" href="https://developers.facebook.com/tools/explorer" target="_blank" rel="noopener">Abrir o Graph API Explorer ↗</a><button class="rf-back" data-ir-contas>Ir para Contas</button></div></div>`;
    return `<div class="ad-aviso"><b>${agSvg(k)} TikTok: falta liberar a leitura dos vídeos</b>
      <p>No app do TikTok for Developers, adicione o produto <b>Display API</b> com o escopo <code>video.list</code>. Depois clique em <b>Reconectar</b>. O TikTok só entrega vídeos públicos, então o que estiver na sua caixa de entrada aparece quando você publicar. Enquanto isso, dá para digitar as views à mão abrindo o vídeo aqui embaixo.</p>
      <div class="ad-aviso-acts"><a class="rf-btn" href="https://developers.tiktok.com/apps" target="_blank" rel="noopener">Abrir o TikTok for Developers ↗</a><a class="rf-back" href="/api/agenda/oauth/tt/inicio?leitura=1">Reconectar</a></div></div>`;
  };
  $('#ag-dash').innerHTML = `
    <div class="ad-topo">
      <span class="ad-atual">${d.atualizado ? `Atualizado em ${new Date(d.atualizado).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })} · atualiza sozinho a cada 3 h` : 'Ainda sem dados'}</span>
      <button class="rf-btn" data-atualizar>Atualizar agora</button>
    </div>
    <div class="ad-tiles">
      <div class="ad-tile hero"><span>Views somadas</span><b>${adNum(d.total)}</b><small>${d.linhas.length} vídeos${AD_REDES.filter(k => d.redes[k].views !== null).length < 3 ? ` · só conta ${AD_REDES.filter(k => d.redes[k].views !== null).map(k => d.redes[k].nome).join(' e ') || 'as redes lidas'} por enquanto` : ''}</small></div>
      ${AD_REDES.map(k => { const r = d.redes[k]; return `<div class="ad-tile"><span><i class="ad-cor ${k}"></i>${esc(r.nome)}</span><b>${adNum(r.views)}</b><small>${r.views === null ? 'falta ler as views' : `em ${r.videos} vídeo${r.videos === 1 ? '' : 's'}`}</small></div>`; }).join('')}
    </div>
    ${faltam.map(aviso).join('')}
    <div class="rf-card ag-tabela ad-tabela"><table>
      <thead><tr><th>Vídeo</th>${AD_REDES.map(k => th(k, cabec(k))).join('')}${th('total', 'Total')}</tr></thead>
      <tbody>${linhas.map(ln => `
        <tr class="ad-linha ${ag.dashAberto === ln.code ? 'aberta' : ''}" data-code="${esc(ln.code)}" tabindex="0">
          <td><div class="ad-vid">${ln.thumb ? `<img src="/api/agenda-capas/${esc(ln.thumb)}" alt="" loading="lazy">` : '<span class="ad-sem"></span>'}
            <div><span class="rt-code">${esc(ln.code)}</span>${ln.status === 'destaque' ? '<em>✦ destaque</em>' : ''}<b>${esc(ln.title)}</b></div></div></td>
          ${AD_REDES.map(k => celula(ln, k)).join('')}
          <td class="ad-n ad-total"><b>${adNum(ln.total)}</b>${ln.delta ? `<small>+${adNum(ln.delta)} desde ontem</small>` : ''}${barra(ln)}</td>
        </tr>
        ${ag.dashAberto === ln.code ? `<tr class="ad-det"><td colspan="5"><div class="ad-fichas">${AD_REDES.map(k => ficha(ln, k)).join('')}</div></td></tr>` : ''}`).join('')}</tbody>
    </table></div>
    ${d.soltos.length ? `<h3 class="ad-h3">Posts sem vídeo</h3>
      <p class="ad-nota">Não consegui ligar estes posts a um vídeo sozinho. Escolha o vídeo ou ignore.</p>
      <div class="rf-card ad-soltos">${d.soltos.map(s => `<div class="ad-solto">
        <i class="ad-cor ${s.rede}"></i>${agSvg(s.rede)}<span class="ad-solto-q">${adQuando(s.quando)}</span>
        <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.texto || '(sem legenda)')}</a>
        <span class="ad-solto-v">${s.views != null ? `${adNum(s.views)} views` : adCurt(s.curtidas)}</span>
        <select data-ligar="${s.rede}:${esc(s.id)}" aria-label="Ligar a um vídeo"><option value="">Ligar a…</option>${d.cards.map(c => `<option value="${esc(c.code)}">${esc(c.code)} · ${esc(c.title.slice(0, 40))}</option>`).join('')}</select>
        <button data-ignorar="${s.rede}:${esc(s.id)}">Ignorar</button></div>`).join('')}</div>` : ''}
    <p class="ad-nota">Cada rede conta a visualização do seu jeito, então compare um vídeo com outro dentro da mesma rede. O Instagram pode levar até 48 h para consolidar os números.</p>`;
}

async function agDashEnvia(url, corpo) {
  try { agDash(await api(url, { method: 'POST', json: corpo || {} })); } catch (e) { toast(e.message, true); }
}

async function agDashClique(e) {
  const t = e.target;
  if (t.closest('a')) return;
  if (t.closest('[data-atualizar]')) {
    const b = t.closest('[data-atualizar]');
    b.disabled = true; b.textContent = 'Atualizando…';
    return agDashEnvia('/api/desempenho/atualizar');
  }
  if (t.closest('[data-ir-contas]')) return loadAgenda('contas');
  const ord = t.closest('[data-ordem]');
  if (ord) {
    const col = ord.dataset.ordem;
    ag.dashOrdem = { col, dir: ag.dashOrdem.col === col ? -ag.dashOrdem.dir : -1 };
    return agDash(ag.dash);
  }
  const ign = t.closest('[data-ignorar]'), sol = t.closest('[data-soltar]');
  if (ign || sol) {
    const [rede, id] = (ign ? ign.dataset.ignorar : sol.dataset.soltar).split(':');
    return agDashEnvia('/api/desempenho/ligar', { rede, id, code: ign ? 'ignorar' : '' });
  }
  if (t.closest('.ad-det')) return;
  const ln = t.closest('.ad-linha');
  if (ln) { ag.dashAberto = ag.dashAberto === ln.dataset.code ? null : ln.dataset.code; agDash(ag.dash); }
}

function agDashMudou(e) {
  const t = e.target;
  if (t.dataset.ligar && t.value) {
    const [rede, id] = t.dataset.ligar.split(':');
    agDashEnvia('/api/desempenho/ligar', { rede, id, code: t.value });
  }
  if (t.dataset.mao) agDashEnvia('/api/desempenho/digitar', { code: t.dataset.code, rede: t.dataset.mao, views: t.value.trim() });
}

// ---------------------------------------------------------------- contas
function agContasEditando() {
  const box = $('#ag-contas');
  return !!box && (box.contains(document.activeElement) || $$('input[data-c]', box).some(i => i.value.trim()));
}
function agContas() {
  // o que ele já digitou sobrevive a qualquer redesenho (troca de modo, conta conectada em outra rede)
  const digitado = {};
  $$('#ag-contas .ag-ct[data-k] input[data-c]').forEach(i => { if (i.value) digitado[i.closest('.ag-ct').dataset.k + '.' + i.dataset.c] = i.value; });
  const ct = ag.dados.contas;
  const volta = k => `http://localhost:8765/api/agenda/oauth/${k}`;
  const topo = (k, c) => `<div class="ag-ct-h">${agSvg(k)}<b>${esc(agRede(k).nome)}</b>
    ${c.conectado ? `<span class="ag-ct-ok">${c.foto ? `<img src="${esc(c.foto)}" alt="">` : ''}conectado: <b>${esc(c.conta || '?')}</b>${c.pagina ? ` · Página ${esc(c.pagina)}` : ''}</span>
      <button class="rf-back" data-sair="${k}">Desconectar</button>` : '<span class="ag-ct-no">não conectado</span>'}</div>
    ${(c.avisos || []).map(a => `<p class="ag-ct-av">⚠ ${esc(a)}</p>`).join('')}
    ${c.expira ? `<p class="ag-ct-sub">conexão válida até ${new Date(c.expira).toLocaleDateString('pt-BR')} (renovo sozinho)</p>` : ''}`;
  const copia = u => `<code class="ag-uri">${u}</code><button class="ag-copy" data-copy="${u}">copiar</button>`;
  const ig = ct.ig, yt = ct.yt, tt = ct.tt;
  $('#ag-contas').innerHTML = `
  <p class="ag-ct-lead">Cada rede pede um "app de desenvolvedor" no seu nome. É grátis e só você usa. Os segredos ficam neste Mac,
    em <code>.segredos/</code>: fora do GitHub e fora do backup.</p>
  <div class="ag-cts">
    <section class="rf-card ag-ct ig" data-k="ig">${topo('ig', ig)}
      <div class="ag-modo">
        <label><input type="radio" name="ig-modo" value="facebook" ${ig.modo !== 'instagram' ? 'checked' : ''}> <b>Pela Página do Facebook</b> (recomendado: o vídeo sobe direto do Mac)</label>
        <label><input type="radio" name="ig-modo" value="instagram" ${ig.modo === 'instagram' ? 'checked' : ''}> <b>Só com o login do Instagram</b> (a Meta pode exigir link público do vídeo, e aí eu aviso)</label>
      </div>
      <ol class="ag-passos">
        <li>Seu Instagram precisa ser <b>profissional</b> (Criador ou Empresa)${ig.modo !== 'instagram' ? ' e estar <b>ligado a uma Página do Facebook</b> (Meta Business Suite → Configurações → Contas do Instagram)' : ''}.</li>
        <li>Em <a href="https://developers.facebook.com/apps" target="_blank" rel="noopener">developers.facebook.com/apps</a> crie um app do tipo <b>Empresa</b> e adicione o produto <b>Instagram</b>.</li>
        ${ig.modo !== 'instagram' ? `<li>Copie o <b>ID do app</b> e a <b>Chave secreta</b> (Configurações do app → Básico) para os campos abaixo.</li>
        <li>No <a href="https://developers.facebook.com/tools/explorer" target="_blank" rel="noopener">Graph API Explorer</a>, escolha o seu app e marque
          <code>instagram_basic</code>, <code>instagram_content_publish</code>, <code>instagram_manage_insights</code>, <code>pages_show_list</code> e <code>pages_read_engagement</code>.
          Clique em <b>Generate Access Token</b>, escolha a Página e cole o token abaixo. Eu troco por um de 60 dias e renovo sozinho.</li>`
        : `<li>No app: Instagram → <b>API setup with Instagram login</b> → <b>Generate token</b> ao lado da sua conta. Cole abaixo (vale 60 dias; renovo sozinho).</li>`}
      </ol>
      <div class="ag-campos">
        ${ig.modo !== 'instagram' ? `<input data-c="client_id" placeholder="ID do app" value="${esc(ig.client_id)}"><input data-c="client_secret" type="password" placeholder="Chave secreta do app${ig.app ? ' (já salva)' : ''}">` : ''}
        <input data-c="token" type="password" placeholder="Token de acesso">
        <button class="rf-btn" data-salvar="ig">Conectar</button>
      </div>
    </section>

    <section class="rf-card ag-ct yt" data-k="yt">${topo('yt', yt)}
      <ol class="ag-passos">
        <li>Em <a href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noopener">console.cloud.google.com</a> crie um projeto e ative a
          <a href="https://console.cloud.google.com/apis/library/youtube.googleapis.com" target="_blank" rel="noopener">YouTube Data API v3</a>.</li>
        <li><b>Google Auth Platform</b> → Público: <b>Externo</b>, com o seu e-mail. Depois clique em <b>Publicar app</b>, para ficar "Em produção".
          Em "Teste" a conexão cai a cada 7 dias. Para uso pessoal não precisa de verificação: o aviso "app não verificado" é normal (Avançado → continuar).</li>
        <li><b>Clientes</b> → Criar cliente → <b>Aplicativo da Web</b> → URI de redirecionamento autorizado: ${copia(volta('yt'))}</li>
        <li>Cole o <b>ID do cliente</b> e a <b>chave secreta</b> e conecte com a conta Google do seu canal.</li>
      </ol>
      <div class="ag-campos">
        <input data-c="client_id" placeholder="ID do cliente (…apps.googleusercontent.com)" value="${esc(yt.client_id)}">
        <input data-c="client_secret" type="password" placeholder="Chave secreta do cliente${yt.app ? ' (já salva)' : ''}">
        <button class="rf-btn" data-salvar="yt">Salvar e conectar com o Google</button>
      </div>
    </section>

    <section class="rf-card ag-ct tt" data-k="tt">${topo('tt', tt)}
      <div class="ag-modo">
        <label><input type="radio" name="tt-modo" value="rascunho" ${tt.modo !== 'direto' ? 'checked' : ''}> <b>Rascunho na hora marcada</b> (recomendado):
          o vídeo chega na caixa de entrada do seu TikTok, você toca em publicar e a legenda já vai copiada</label>
        <label><input type="radio" name="tt-modo" value="direto" ${tt.modo === 'direto' ? 'checked' : ''}> <b>Publicar sozinho</b>: só funciona depois da auditoria do TikTok,
          e o TikTok não aprova app de uso pessoal. Sem ela, o post sai "Só eu" e a conta precisa estar privada.</label>
      </div>
      <ol class="ag-passos">
        <li>Em <a href="https://developers.tiktok.com/apps" target="_blank" rel="noopener">developers.tiktok.com</a> → Manage apps → <b>Connect an app</b>.</li>
        <li>Plataforma <b>Desktop</b>. Produtos: <b>Login Kit</b>, <b>Content Posting API</b> e <b>Display API</b> (a Display API é a que lê as views: escopo <code>video.list</code>).</li>
        <li>No Login Kit, Redirect URI: ${copia(volta('tt'))}</li>
        <li>Ligue o <b>Sandbox</b> e adicione a sua conta do TikTok como usuário de teste. Assim não precisa de revisão.</li>
        <li>Cole o <b>Client key</b> e o <b>Client secret</b> e conecte.</li>
      </ol>
      <div class="ag-campos">
        <input data-c="client_id" placeholder="Client key" value="${esc(tt.client_id)}">
        <input data-c="client_secret" type="password" placeholder="Client secret${tt.app ? ' (já salvo)' : ''}">
        <button class="rf-btn" data-salvar="tt">Salvar e conectar com o TikTok</button>
      </div>
    </section>
  </div>`;
  $$('#ag-contas .ag-ct[data-k] input[data-c]').forEach(i => {
    const v = digitado[i.closest('.ag-ct').dataset.k + '.' + i.dataset.c];
    if (v) i.value = v;
  });
}

async function agSalvarConta(k) {
  const box = $(`.ag-ct[data-k="${k}"]`);
  const dados = {};
  $$('[data-c]', box).forEach(i => { if (i.value.trim()) dados[i.dataset.c] = i.value.trim(); });
  const modo = $(`input[name="${k}-modo"]:checked`, box);
  if (modo) dados.modo = modo.value;
  try {
    await api(`/api/agenda-contas/${k}`, { method: 'POST', json: dados });
    if (k === 'ig') { toast('Instagram conectado ✓'); return agRefresh(); }
    location.href = `/api/agenda/oauth/${k}/inicio`;          // Google/TikTok: login na página deles, volta para cá
  } catch (e) { toast(e.message, true, 9000); }
}

// ---------------------------------------------------------------- gaveta do agendamento
function agAbrir(aid) {
  const p = ag.dados.posts.find(x => x.id === aid);
  if (!p) return;
  ag.sel = JSON.parse(JSON.stringify(p));
  ag.escolher = null;
  agEditor();
  $('#ag-drawer').classList.remove('hidden');
}
function agFechar() {
  ag.sel = null; ag.escolher = null; $('#ag-drawer').classList.add('hidden');
  if (ag.capaSel) { ag.capaSel = null; ag.capasFeitas = false; }
  agRefresh();
}

// ---------------------------------------------------------------- CAPAS (03/11): 3 opções por vídeo — headline + o melhor rosto
// Princípio do @fernandomiranda777 (imagem do assunto + rosto + pergunta na emenda), com tipografia grande e a paleta
// Kronos. Gerar = app/capas.py (Apple Vision escolhe os quadros; Chrome desenha). A escolhida vira capa.jpg.
const capaUrl = (code, nome, v) => `/api/capas/${encodeURIComponent(code)}/img/${encodeURIComponent(nome)}?v=${v || 0}`;
function agCapas(lista) {
  ag.capas = lista;
  $('#ag-capas').innerHTML = `
    <p class="ag-ct-lead">Cada vídeo ganha 3 opções de capa: a headline (o gancho), a imagem do assunto e o quadro em que o seu
      rosto saiu melhor. Escolha uma e baixe para usar no Instagram, no Shorts e no TikTok. Tudo que importa fica dentro do
      recorte do grid (3:4).</p>
    <div class="cp-grid">${lista.map(v => {
      const c = v.capa || {};
      const img = c.escolhida != null ? 'capa.jpg' : (c.capas || [])[0];
      return `<button class="cp-item" data-capa="${esc(v.code)}">
        <div class="cp-thumb">${img ? `<img src="${capaUrl(v.code, img, c.versao)}" alt="">` : '<span>sem capa ainda</span>'}</div>
        <div class="cp-meta"><span class="rt-code">${esc(v.code)}</span><b>${esc(v.title)}</b>
          <small class="${c.escolhida != null ? 'ok' : ''}">${c.escolhida != null ? '✓ capa escolhida' : (c.capas || []).length ? '3 opções prontas · escolha uma' : 'gerar as opções'}</small></div>
      </button>`;
    }).join('')}</div>`;
}

async function agAbrirCapa(code) {
  if ($('#agenda').classList.contains('hidden') || ag.tab !== 'capas') await loadAgenda('capas');
  ag.capas = ag.capas || await api('/api/capas');
  ag.capaSel = code;
  agCapaEditor();
  $('#ag-drawer').classList.remove('hidden');
  const v = ag.capas.find(x => x.code === code);
  if (v && !(v.capa?.capas || []).length) agGerarCapa(code, {});       // 1ª vez: já gera
}

function agCapaEditor(prog) {
  const v = ag.capas.find(x => x.code === ag.capaSel);
  if (!v) return;
  const c = v.capa || {};
  const opcoes = c.capas || [];
  $('#ag-editor').innerHTML = `
    <header class="ag-ed-bar"><span class="rt-code">${esc(v.code)}</span><b class="cp-titulo">${esc(v.title)}</b>
      <div class="spacer"></div><button class="rf-back" id="ag-x">Fechar</button></header>
    <div class="cp-ed">
      <div class="cp-form">
        <label>Headline da capa <small>use *palavra* para destacar em dourado</small>
          <textarea id="cp-hl" rows="3">${esc(c.headline || v.headline_padrao)}</textarea></label>
        <div class="cp-row">
          <div class="cp-modelo">${[['dividida', 'Dividida (assunto em cima)'], ['retrato', 'Retrato (só você)']].map(([m, t]) =>
            `<button data-modelo="${m}" class="${(c.modelo || 'dividida') === m ? 'on' : ''}" ${m === 'dividida' && c.quadros && !c.contexto ? 'disabled title="Este vídeo não tem ativo no gancho"' : ''}>${t}</button>`).join('')}</div>
          <div class="spacer"></div>
          <button class="rf-back" id="cp-novos" title="Procura outros quadros do seu rosto no vídeo">↻ Outros quadros</button>
          <button class="rf-btn" id="cp-gerar">Gerar capas</button>
        </div>
        ${prog ? `<div class="cp-prog"><i style="width:${Math.round((prog.progress || 0) * 100)}%"></i><span>${esc(prog.message || 'gerando…')}</span></div>` : ''}
      </div>
      <label class="cp-recorte"><input type="checkbox" id="cp-grid" ${ag.capaGrid ? 'checked' : ''}> mostrar o recorte do grid (3:4)</label>
      <div class="cp-opcoes ${ag.capaGrid ? 'grid3x4' : ''}">${opcoes.length ? opcoes.map((nome, i) => `
        <div class="cp-op ${c.escolhida === i ? 'on' : ''}">
          <button class="cp-img" data-escolher="${i}" title="Escolher esta">
            <img src="${capaUrl(v.code, nome, c.versao)}" alt="opção ${i + 1}"><span class="cp-faixa t"></span><span class="cp-faixa b"></span></button>
          <div class="cp-acts"><button class="${c.escolhida === i ? 'rf-btn' : 'rf-back'}" data-escolher="${i}">${c.escolhida === i ? '✓ Escolhida' : 'Escolher'}</button>
            <a class="rf-back" href="${capaUrl(v.code, nome, c.versao)}&baixar=1" download>⬇ Baixar</a></div>
        </div>`).join('') : '<p class="ag-vazio">Gerando as primeiras opções… (cerca de 1 minuto)</p>'}</div>
      <div class="cp-onde"><b>Onde usar a capa escolhida</b>
        <p><b>Instagram:</b> ao postar, toque em <i>Editar capa → Adicionar da galeria</i>. Em Reels já publicados: no post, <i>⋯ → Editar → Editar capa</i>.</p>
        <p><b>YouTube Shorts:</b> entra sozinha como miniatura nos próximos envios da agenda, depois que o canal for verificado em youtube.com/verify.</p>
        <p><b>TikTok:</b> ao publicar o rascunho, toque em <i>Capa → Carregar</i> e escolha a imagem.</p></div>
    </div>`;
}

async function agGerarCapa(code, opts) {
  const v = ag.capas.find(x => x.code === code);
  try {
    const job = await api(`/api/capas/${encodeURIComponent(code)}/gerar`, { method: 'POST', json: opts });
    agCapaEditor({ progress: 0.02, message: 'começando…' });
    for (;;) {
      await new Promise(r => setTimeout(r, 1500));
      const j = await api(`/api/jobs/${job.id}`);
      if (ag.capaSel === code) agCapaEditorProg(j);
      if (j.status === 'done') { v.capa = j.result; break; }
      if (j.status === 'error') throw new Error(j.message || 'falhou');
    }
    if (ag.capaSel === code) agCapaEditor();
    ag.capasFeitas = false;
    toast(`${code}: 3 opções de capa prontas`);
  } catch (e) { toast('Capa: ' + e.message, true, 8000); if (ag.capaSel === code) agCapaEditor(); }
}
function agCapaEditorProg(j) {
  const box = $('.cp-prog');
  if (!box) return agCapaEditor(j);
  $('i', box).style.width = Math.round((j.progress || 0) * 100) + '%';
  $('span', box).textContent = j.message || 'gerando…';
}

async function agNovo(opts = {}) {
  // sem vídeo escolhido: a gaveta abre na lista de vídeos prontos
  if (!opts.code && !opts.arquivo) {
    ag.sel = null; ag.escolher = { dia: opts.dia || null, k: opts.k || null };
    ag.arquivos = ag.arquivos || await api('/api/agenda-arquivos');
    agEscolher();
    $('#ag-drawer').classList.remove('hidden');
    return;
  }
  const est = opts.code ? agEstadoCode(opts.code) : { ig: 'nao', yt: 'nao', tt: 'nao' };
  const on = opts.k ? [opts.k] : Object.keys(est).filter(k => est[k] === 'nao');
  try {
    const p = await api('/api/agenda', { method: 'POST', json: { code: opts.code || '', arquivo: opts.arquivo || '', quando: agPadrao(opts.dia), redes_on: on.length ? on : ['ig'] } });
    ag.dados.posts.push(p);
    agAbrir(p.id);
  } catch (e) { toast(e.message, true); }
}

function agEscolher() {
  const ed = $('#ag-editor');
  const lista = ag.prontos.map(r => ({ ...r, est: agEstadoCode(r.code) }));
  const outros = (ag.arquivos || []).filter(a => !a.code);
  ed.innerHTML = `<header class="ag-ed-bar"><b>Qual vídeo?</b><div class="spacer"></div><button class="rf-back" id="ag-x">Fechar</button></header>
    <div class="ag-esc-grid">${lista.map(r => `<button class="ag-esc" data-esc-code="${esc(r.code)}">
      ${r.thumb ? `<img src="/api/agenda-capas/${r.thumb}" alt="">` : '<div class="ag-pr-ph">▶</div>'}
      <span class="rt-code">${esc(r.code)}</span><b>${esc(r.title)}</b>
      <div class="ag-dots">${['ig', 'yt', 'tt'].map(k => `<span class="ag-dot ${k} ${r.est[k]}">${agSvg(k)}</span>`).join('')}</div></button>`).join('')}</div>
    <details class="ag-outros"><summary>Outro arquivo (exportações dos projetos ou um MP4 do seu computador)</summary>
      <div class="ag-arqs">${outros.map(a => `<button data-esc-arq="${esc(a.arquivo)}"><b>${esc(a.nome)}</b><small>${esc(a.origem)}</small></button>`).join('')}</div>
      <label class="rf-back ag-up">⬆ Enviar um MP4<input type="file" accept="video/mp4,video/quicktime" id="ag-up" hidden></label>
    </details>`;
}

function agCampoOpc(k, nome, rotulo, o, tipo = 'check', extra = {}) {
  const v = (o || {})[nome];
  if (tipo === 'check') return `<label class="ag-chk"><input type="checkbox" data-o="${nome}" ${v ? 'checked' : ''}> ${rotulo}</label>`;
  if (tipo === 'select') return `<label class="ag-sel">${rotulo}<select data-o="${nome}">${extra.opcoes.map(([val, txt]) =>
    `<option value="${val}" ${String(v ?? '') === val ? 'selected' : ''}>${txt}</option>`).join('')}</select></label>`;
  return `<label class="ag-txt">${rotulo}<input data-o="${nome}" value="${esc(v || '')}" placeholder="${esc(extra.ph || '')}"></label>`;
}

function agNetHTML(p, k) {
  const e = p.redes[k];
  const cfg = ag.dados.redes[k];
  const conta = ag.dados.contas[k] || {};
  const trava = ['publicado', 'enviando'].includes(e.status);
  const dis = trava ? 'disabled' : '';
  const o = e.opcoes || {};
  let opc = '';
  if (k === 'ig') opc = agCampoOpc(k, 'share_to_feed', 'Mostrar também no feed', o) + agCampoOpc(k, 'ia', 'Selo "Informações de IA"', o)
    + agCampoOpc(k, 'colaboradores', 'Colaboradores (até 3 @)', o, 'text', { ph: '@fulano, @marca' });
  if (k === 'yt') opc = agCampoOpc(k, 'privacidade', 'Visibilidade', o, 'select', { opcoes: [['public', 'Público'], ['unlisted', 'Não listado'], ['private', 'Privado']] })
    + agCampoOpc(k, 'categoria', 'Categoria', o, 'select', { opcoes: [['27', 'Educação'], ['22', 'Pessoas e blogs'], ['28', 'Ciência e tecnologia'], ['24', 'Entretenimento'], ['26', 'Guias e estilo']] })
    + agCampoOpc(k, 'tags', 'Tags (separadas por vírgula)', o, 'text', { ph: 'filosofia, marketing' })
    + agCampoOpc(k, 'kids', 'Feito para crianças', o) + agCampoOpc(k, 'ia', 'Conteúdo alterado/sintético (IA)', o);
  if (k === 'tt') opc = conta.modo === 'direto'
    ? agCampoOpc(k, 'privacidade', 'Quem pode ver', o, 'select', { opcoes: [['', 'Escolha…'], ['PUBLIC_TO_EVERYONE', 'Todo mundo'], ['MUTUAL_FOLLOW_FRIENDS', 'Amigos'], ['FOLLOWER_OF_CREATOR', 'Seguidores'], ['SELF_ONLY', 'Só eu']] })
      + agCampoOpc(k, 'comentarios', 'Permitir comentários', o) + agCampoOpc(k, 'duet', 'Permitir dueto', o) + agCampoOpc(k, 'stitch', 'Permitir costura', o)
      + agCampoOpc(k, 'ia', 'Rótulo "gerado por IA"', o) + agCampoOpc(k, 'marca', 'Divulga a sua própria marca', o)
      + '<p class="ag-nota">Ao publicar, você concorda com a Confirmação de Uso de Música do TikTok.</p>'
    : '<p class="ag-nota">Modo rascunho: no horário, o vídeo chega na caixa de entrada do seu TikTok, com a legenda já copiada no Mac. Privacidade e comentários você escolhe no app.</p>';
  const max = cfg.legenda_max;
  return `<section class="ag-net ${k} ${e.on ? 'on' : 'off'} ${trava ? 'trava' : ''}" data-k="${k}">
    <header><label class="ag-sw" title="Publicar nesta rede"><input type="checkbox" data-f="on" ${e.on ? 'checked' : ''} ${dis}><span></span></label>
      ${agSvg(k)}<b>${esc(cfg.nome)}</b><span class="ag-acc ${conta.conectado ? '' : 'no'}">${conta.conectado ? esc(conta.conta) : 'conta não conectada'}</span>
      <div class="spacer"></div><span class="ag-st st-${e.status}">${AG_ICO[e.status] || ''} ${esc(agStLabel(e.status, k))}</span></header>
    <div class="ag-net-body">
      <label class="ag-quando">Quando <input type="datetime-local" data-f="quando" value="${esc(e.quando || '')}" ${dis}></label>
      ${k === 'yt' ? `<label class="ag-tit">Título do Short <input data-f="titulo" maxlength="100" value="${esc(e.titulo || '')}" ${dis}><small data-n="titulo">${(e.titulo || '').length}/100</small></label>` : ''}
      <label class="ag-leg">${k === 'yt' ? 'Descrição' : 'Legenda'}${k !== 'ig' ? ' <button type="button" class="ag-mini" data-igual>↺ igual ao Instagram</button>' : ''}
        <textarea data-f="legenda" rows="7" ${dis}>${esc(e.legenda || '')}</textarea><small data-n="legenda">${(e.legenda || '').length}/${max}</small></label>
      <div class="ag-opcs">${opc}</div>
      <div class="ag-probs" data-probs="${k}">${agProbs(p, k)}</div>
      <div class="ag-net-st" data-st="${k}">${agStatusHTML(p, k)}</div>
    </div></section>`;
}

function agProbs(p, k) {
  return ((p.problemas || {})[k] || []).map(x => `<p class="ag-pb ${x.nivel}">${x.nivel === 'erro' ? '✗' : '⚠'} ${esc(x.msg)}</p>`).join('');
}

function agStatusHTML(p, k) {
  const e = p.redes[k];
  const linhas = [];
  if (e.etapa) linhas.push(`<p class="ag-etapa">${esc(e.etapa)}</p>`);
  if (e.erro && ['erro', 'atrasado'].includes(e.status)) linhas.push(`<p class="ag-pb erro">✗ ${esc(e.erro)}</p>`);
  if (e.url) linhas.push(`<p><a href="${esc(e.url)}" target="_blank" rel="noopener">${e.status === 'publicado' ? 'Abrir o post ↗' : 'Ver na rede ↗'}</a>${e.publicado_em ? ` · publicado ${agHora(e.publicado_em)}` : ''}</p>`);
  const b = [];
  if (['agendado', 'na_rede'].includes(e.status)) b.push(`<button class="rf-back" data-acao="desagendar" data-k="${k}">Desagendar</button>`);
  if (!['publicado', 'enviando'].includes(e.status)) b.push(`<button class="rf-back" data-acao="agora" data-k="${k}">Publicar agora</button>`);
  if (!['publicado', 'enviando', 'na_rede'].includes(e.status)) b.push(`<button class="rf-back" data-acao="manual" data-k="${k}">Já postei à mão</button>`);
  if (e.status === 'publicado' && e.manual) b.push(`<button class="rf-back" data-acao="desmarcar" data-k="${k}">Desmarcar</button>`);
  const log = (e.log || []).slice(-8).reverse();
  return `${linhas.join('')}<div class="ag-acts">${b.join('')}</div>
    ${log.length ? `<details class="ag-log"><summary>histórico</summary>${log.map(l => `<p><time>${esc(l.t.slice(8, 10) + '/' + l.t.slice(5, 7) + ' ' + l.t.slice(11, 16))}</time>${esc(l.msg)}</p>`).join('')}</details>` : ''}`;
}

function agEditor() {
  const p = ag.sel;
  const i = p.info;
  const vid = p.arquivo ? `/api/agenda-video?arquivo=${encodeURIComponent(p.arquivo)}` : '';
  const dur = i ? `${Math.floor(i.dur / 60)}:${String(Math.round(i.dur % 60)).padStart(2, '0')}` : '';
  const quandos = Object.values(p.redes).filter(e => e.on).map(e => e.quando).filter(Boolean);
  $('#ag-editor').innerHTML = `
    <header class="ag-ed-bar"><span class="rt-code">${esc(p.id)}</span>${p.code ? `<span class="rt-code">${esc(p.code)}</span>` : ''}
      <input id="ag-nome" value="${esc(p.nome || '')}" aria-label="Nome do agendamento">
      <div class="spacer"></div><span id="ag-salvo" class="ag-salvo"></span><button class="rf-back" id="ag-x">Fechar</button></header>
    <div class="ag-ed">
      <div class="ag-prev">
        ${vid ? `<video id="ag-video" src="${vid}#t=${p.capa || 1}" controls preload="metadata" playsinline></video>` : '<div class="ag-novid">sem vídeo</div>'}
        <div class="ag-capa">${p.thumb ? `<img src="/api/agenda-capas/${p.thumb}" alt="capa">` : ''}<div><b>Capa</b><small>quadro em ${Number(p.capa || 0).toFixed(1).replace('.', ',')} s</small>
          <button class="ag-mini" id="ag-capa">Usar o quadro do vídeo</button></div></div>
        <p class="ag-file">${i ? `<b>${esc(i.nome)}</b><br>${dur} · ${i.w}×${i.h} · ${String(i.mb).replace('.', ',')} MB` : '<b>Vídeo não encontrado</b>'}</p>
        <button class="rf-back ag-trocar" id="ag-trocar">Trocar vídeo</button>
      </div>
      <div class="ag-form">
        <div class="ag-todas"><label>Mesmo horário em todas as redes marcadas <input type="datetime-local" id="ag-todas" value="${esc(quandos[0] || '')}"></label>
          <button class="ag-mini" id="ag-todas-ok">Aplicar</button></div>
        <div class="ag-nets">${['ig', 'yt', 'tt'].map(k => agNetHTML(p, k)).join('')}</div>
      </div>
    </div>
    <footer class="ag-ed-foot"><button class="rf-back ag-del" id="ag-del">Excluir agendamento</button><div class="spacer"></div>
      <button class="rf-back" id="ag-salvar">Salvar rascunho</button><button class="rf-btn" id="ag-agendar">Agendar</button></footer>`;
}

function agColetar() {
  const p = ag.sel;
  const out = { nome: $('#ag-nome').value.trim(), capa: p.capa, arquivo: p.arquivo, redes: {} };
  for (const sec of $$('#ag-editor .ag-net')) {
    if (sec.classList.contains('trava')) continue;
    const k = sec.dataset.k;
    const r = { opcoes: {} };
    $$('[data-f]', sec).forEach(el => { r[el.dataset.f] = el.type === 'checkbox' ? el.checked : el.value; });
    $$('[data-o]', sec).forEach(el => { r.opcoes[el.dataset.o] = el.type === 'checkbox' ? el.checked : el.value; });
    out.redes[k] = r;
  }
  return out;
}

async function agSalvar(silencio) {
  if (!ag.sel || !$('#ag-nome')) return null;
  try {
    const p = await api(`/api/agenda/${ag.sel.id}`, { method: 'PUT', json: agColetar() });
    ag.sel = p;
    const i = ag.dados.posts.findIndex(x => x.id === p.id);
    if (i >= 0) ag.dados.posts[i] = p;
    $$('[data-probs]').forEach(el => { el.innerHTML = agProbs(p, el.dataset.probs); });
    $('#ag-salvo').textContent = '✓ salvo';
    if (!silencio) toast('Salvo');
    return p;
  } catch (e) { toast(e.message, true, 7000); return null; }
}

function agStatusAtualiza() {
  // enquanto a gaveta está aberta, só o STATUS de cada rede acompanha o relógio (o que ele está digitando fica)
  const p = ag.dados.posts.find(x => x.id === ag.sel?.id);
  if (!p) return;
  for (const k of ['ig', 'yt', 'tt']) {
    const antes = ag.sel.redes[k].status;
    ag.sel.redes[k] = { ...ag.sel.redes[k], ...Object.fromEntries(['status', 'etapa', 'erro', 'url', 'publicado_em', 'log', 'manual'].map(c => [c, p.redes[k][c]])) };
    const sec = $(`#ag-editor .ag-net[data-k="${k}"]`);
    if (!sec) continue;
    if (antes !== p.redes[k].status && ['publicado', 'enviando'].includes(p.redes[k].status)) { agEditor(); return; }
    $('.ag-st', sec).className = `ag-st st-${p.redes[k].status}`;
    $('.ag-st', sec).textContent = `${AG_ICO[p.redes[k].status] || ''} ${agStLabel(p.redes[k].status, k)}`;
    $(`[data-st="${k}"]`, sec).innerHTML = agStatusHTML(ag.sel, k);
  }
}

// CONFIRMAÇÃO DUPLA (pedido dele, 03/11) para tudo que vai ao ar NA HORA: "Publicar agora" e agendar com horário que já
// passou. A 2ª pergunta diz o vídeo, a rede e a conta; o servidor recusa sem as duas (confirmado: "sim").
function agConfirmaDupla(redesK) {
  const p = ag.sel;
  const onde = redesK.map(k => `${agRede(k).nome} (${(ag.dados.contas[k] || {}).conta || 'conta'})`).join(' e ');
  if (!confirm(`Publicar AGORA no ${onde}?`)) return false;
  return confirm(`Confirmação final: “${p.code ? p.code + ' · ' : ''}${p.nome}” vai ao ar AGORA no ${onde}.\n\n` +
    'Depois de publicado, não dá para desfazer pela ferramenta. Publicar?');
}

async function agAcao(acao, k) {
  const nome = agRede(k).nome;
  let json = { rede: k };
  if (acao === 'agora') {
    if (!agConfirmaDupla([k])) return;
    json.confirmado = 'sim';
  }
  if (acao === 'manual') {
    const url = prompt(`Link do post no ${nome} (opcional):`, '');
    if (url === null) return;
    json.url = url;
  }
  if (acao === 'desmarcar') { acao = 'manual'; json.desfazer = true; }
  if (acao === 'desagendar' && ag.sel?.redes[k]?.status === 'na_rede' && k === 'yt' &&
      !confirm('O vídeo já está no YouTube como privado. Desagendar deixa ele privado no YouTube Studio (nada é apagado). Continuar?')) return;
  if (['agora'].includes(acao) && !(await agSalvar(true))) return;
  try {
    const p = await api(`/api/agenda/${ag.sel.id}/${acao}`, { method: 'POST', json });
    ag.sel = p;
    agEditor();
    toast({ agora: `${nome}: publicando agora…`, desagendar: `${nome}: desagendado`, manual: json.desfazer ? 'Desmarcado' : `${nome}: marcado como publicado` }[acao]);
    setTimeout(agRefresh, 1500);
  } catch (e) { toast(e.message, true, 8000); }
}

// ---------------------------------------------------------------- eventos (uma vez)
function agBind() {
  if (ag.bound) return;
  ag.bound = true;
  $('#ag-tabs').onclick = e => { const b = e.target.closest('button[data-ag]'); if (b) loadAgenda(b.dataset.ag); };
  $('#ag-dash').addEventListener('click', agDashClique);
  $('#ag-dash').addEventListener('change', agDashMudou);
  $('#ag-prev').onclick = () => { ag.mes = new Date(ag.mes.getFullYear(), ag.mes.getMonth() - 1, 1); agCal(); };
  $('#ag-next').onclick = () => { ag.mes = new Date(ag.mes.getFullYear(), ag.mes.getMonth() + 1, 1); agCal(); };
  $('#ag-hoje').onclick = () => { const d = new Date(); ag.mes = new Date(d.getFullYear(), d.getMonth(), 1); agCal(); };
  $('#ag-novo').onclick = () => agNovo();
  $('#ag-drawer-bg').onclick = () => { if (ag.sel) agSalvar(true); agFechar(); };

  // calendário: clique no chip abre; ＋ no dia agenda; arrastar chip muda o dia (mantém a hora); arrastar vídeo pronto cria
  $('#ag-cal').addEventListener('click', e => {
    const ch = e.target.closest('.ag-ev');
    if (ch) return agAbrir(ch.dataset.aid);
    const add = e.target.closest('[data-add-day]');
    if (add) return agNovo({ dia: add.dataset.addDay });
    const pr = e.target.closest('.ag-pr');
    if (pr) {
      const p = ag.dados.posts.filter(x => x.code === pr.dataset.code).pop();
      return p ? agAbrir(p.id) : agNovo({ code: pr.dataset.code });
    }
  });
  $('#ag-cal').addEventListener('dragstart', e => {
    const ch = e.target.closest('.ag-ev, .ag-pr');
    if (!ch) return;
    e.dataTransfer.setData('text/plain', JSON.stringify(ch.classList.contains('ag-ev') ? { aid: ch.dataset.aid, k: ch.dataset.k } : { code: ch.dataset.code }));
    e.dataTransfer.effectAllowed = 'move';
  });
  $('#ag-grid').addEventListener('dragover', e => { const d = e.target.closest('.ag-day'); if (d) { e.preventDefault(); $$('.ag-day.drop').forEach(x => x !== d && x.classList.remove('drop')); d.classList.add('drop'); } });
  $('#ag-grid').addEventListener('dragleave', e => { const d = e.target.closest('.ag-day'); if (d && !d.contains(e.relatedTarget)) d.classList.remove('drop'); });
  $('#ag-grid').addEventListener('drop', async e => {
    const d = e.target.closest('.ag-day');
    if (!d) return;
    e.preventDefault(); d.classList.remove('drop');
    let x; try { x = JSON.parse(e.dataTransfer.getData('text/plain')); } catch { return; }
    if (x.code) return agNovo({ code: x.code, dia: d.dataset.day });
    const p = ag.dados.posts.find(y => y.id === x.aid);
    const ev = p?.redes[x.k];
    if (!ev) return;
    const novo = d.dataset.day + 'T' + (ev.quando || 'T18:00').slice(11, 16);
    if (new Date(novo) < new Date() && ['agendado', 'na_rede'].includes(ev.status))
      return toast('Esse horário já passou. Para publicar agora, abra o agendamento e use “Publicar agora”.', true, 6000);
    try {
      const r = await api(`/api/agenda/${p.id}`, { method: 'PUT', json: { redes: { [x.k]: { quando: novo } } } });
      Object.assign(p, r);
      agCal();
      toast(`${agRede(x.k).nome}: ${p.code || p.nome} → ${agHora(novo)}`);
    } catch (err) { toast(err.message, true, 7000); }
  });

  // o que foi postado
  $('#ag-central').addEventListener('click', async e => {
    const op = e.target.closest('[data-open]');
    if (op) return agAbrir(op.dataset.open);
    const ag1 = e.target.closest('[data-agendar-code]');
    if (ag1) { const p = ag.dados.posts.filter(x => x.code === ag1.dataset.agendarCode).pop(); return p ? agAbrir(p.id) : agNovo({ code: ag1.dataset.agendarCode, k: ag1.dataset.k }); }
    const ja = e.target.closest('[data-ja]');
    if (ja) {
      const k = ja.dataset.k;
      const url = prompt(`Link do post no ${agRede(k).nome} (opcional):`, '');
      if (url === null) return;
      try {
        let p = ag.dados.posts.filter(x => x.code === ja.dataset.ja).pop();
        if (!p) p = await api('/api/agenda', { method: 'POST', json: { code: ja.dataset.ja } });
        await api(`/api/agenda/${p.id}/manual`, { method: 'POST', json: { rede: k, url } });
        toast(`${ja.dataset.ja}: marcado como publicado no ${agRede(k).nome}`);
        agRefresh();
      } catch (err) { toast(err.message, true); }
    }
  });

  // capas
  $('#ag-capas').addEventListener('click', e => { const b = e.target.closest('[data-capa]'); if (b) agAbrirCapa(b.dataset.capa); });

  // contas
  $('#ag-contas').addEventListener('click', async e => {
    const s = e.target.closest('[data-salvar]');
    if (s) return agSalvarConta(s.dataset.salvar);
    const sair = e.target.closest('[data-sair]');
    if (sair && confirm('Desconectar esta conta? (o app continua salvo; é só conectar de novo)')) {
      await api(`/api/agenda-contas/${sair.dataset.sair}`, { method: 'DELETE' }); return agRefresh();
    }
    const cp = e.target.closest('[data-copy]');
    if (cp) { navigator.clipboard.writeText(cp.dataset.copy); toast('Copiado'); }
  });
  $('#ag-contas').addEventListener('change', async e => {
    const r = e.target.closest('input[type=radio]');
    if (!r) return;
    const k = r.name.split('-')[0];
    await api(`/api/agenda-contas/${k}`, { method: 'POST', json: { modo: r.value } });
    ag.dados.contas[k].modo = r.value;
    agContas();
  });

  // gaveta
  const ed = $('#ag-editor');
  ed.addEventListener('click', async e => {
    const t = e.target;
    if (t.closest('#ag-x')) { if (ag.sel) await agSalvar(true); return agFechar(); }
    if (ag.capaSel) {                                 // painel da capa
      const code = ag.capaSel, hl = () => $('#cp-hl')?.value || '';
      const m = t.closest('[data-modelo]');
      if (m && !m.disabled) return agGerarCapa(code, { headline: hl(), modelo: m.dataset.modelo });
      if (t.closest('#cp-gerar')) return agGerarCapa(code, { headline: hl() });
      if (t.closest('#cp-novos')) return agGerarCapa(code, { headline: hl(), refazer: true });
      const esc1 = t.closest('[data-escolher]');
      if (esc1) {
        try {
          const c = await api(`/api/capas/${encodeURIComponent(code)}/escolher`, { method: 'POST', json: { i: +esc1.dataset.escolher } });
          ag.capas.find(x => x.code === code).capa = c;
          ag.capasFeitas = false;
          agCapaEditor();
          toast(`${code}: capa ${+esc1.dataset.escolher + 1} escolhida`);
        } catch (err) { toast(err.message, true); }
      }
      return;
    }
    const esc1 = t.closest('[data-esc-code], [data-esc-arq]');
    if (esc1) {
      if (ag.sel) {                                   // trocar o vídeo de um agendamento aberto
        ag.sel.arquivo = esc1.dataset.escArq || (ag.prontos.find(r => r.code === esc1.dataset.escCode) || {}).arquivo || '';
        if (esc1.dataset.escCode) ag.sel.code = esc1.dataset.escCode;
        const p = await api(`/api/agenda/${ag.sel.id}`, { method: 'PUT', json: { ...agColetarSeguro(), arquivo: ag.sel.arquivo, code: ag.sel.code } });
        ag.sel = p; return agEditor();
      }
      return agNovo({ code: esc1.dataset.escCode, arquivo: esc1.dataset.escArq, dia: ag.escolher?.dia, k: ag.escolher?.k });
    }
    if (t.closest('#ag-trocar')) { ag.arquivos = ag.arquivos || await api('/api/agenda-arquivos'); const keep = ag.sel; agEscolher(); ag.sel = keep; ag._form = null; return; }
    if (t.closest('#ag-capa')) {
      const v = $('#ag-video');
      if (!v) return;
      ag.sel.capa = Math.round(v.currentTime * 10) / 10;
      const p = await agSalvar(true);
      if (p) { agEditor(); toast(`Capa: quadro em ${p.capa.toFixed(1).replace('.', ',')} s`); }
      return;
    }
    if (t.closest('#ag-todas-ok')) {
      const v = $('#ag-todas').value;
      if (!v) return;
      $$('#ag-editor .ag-net.on:not(.trava) [data-f="quando"]').forEach(i => { i.value = v; });
      return agSalvar(true);
    }
    const ig = t.closest('[data-igual]');
    if (ig) {
      const src = $('#ag-editor .ag-net[data-k="ig"] [data-f="legenda"]').value;
      const ta = $('[data-f="legenda"]', ig.closest('.ag-net'));
      if (!ta.disabled) { ta.value = src; ta.dispatchEvent(new Event('input', { bubbles: true })); }
      return;
    }
    const ac = t.closest('[data-acao]');
    if (ac) return agAcao(ac.dataset.acao, ac.dataset.k);
    if (t.closest('#ag-salvar')) return agSalvar();
    if (t.closest('#ag-agendar')) {
      const p = await agSalvar(true);
      if (!p) return;
      // horário já passado (ou daqui a < 2 min) = sairia na hora: confirmação dupla, como no "Publicar agora"
      const jaJa = Object.entries(p.redes).filter(([, e]) => e.on && ['rascunho', 'erro', 'atrasado'].includes(e.status)
        && e.quando && new Date(e.quando) <= new Date(Date.now() + 120000)).map(([k]) => k);
      if (jaJa.length && !agConfirmaDupla(jaJa)) return;
      try {
        ag.sel = await api(`/api/agenda/${p.id}/agendar`, { method: 'POST', json: jaJa.length ? { confirmado: 'sim' } : {} });
        agEditor();
        const on = Object.entries(ag.sel.redes).filter(([, e]) => e.on).map(([k, e]) => `${agRede(k).curto} ${agHora(e.quando)}`);
        toast(`Agendado ✓ ${on.join(' · ')}`, false, 5000);
      } catch (err) { toast(err.message, true, 9000); }
      return;
    }
    if (t.closest('#ag-del')) {
      if (!confirm('Excluir este agendamento?')) return;
      try { await api(`/api/agenda/${ag.sel.id}`, { method: 'DELETE' }); toast('Agendamento excluído'); agFechar(); }
      catch (err) { toast(err.message, true, 7000); }
    }
  });
  ed.addEventListener('input', e => {
    const f = e.target.dataset?.f;
    if (f === 'legenda' || f === 'titulo') {
      const k = e.target.closest('.ag-net').dataset.k;
      const max = f === 'titulo' ? 100 : ag.dados.redes[k].legenda_max;
      const n = k === 'yt' && f === 'legenda' ? new TextEncoder().encode(e.target.value).length : e.target.value.length;
      const sm = $(`[data-n="${f}"]`, e.target.closest('.ag-net'));
      sm.textContent = `${n}/${max}${k === 'yt' && f === 'legenda' ? ' bytes' : ''}`;
      sm.classList.toggle('over', n > max);
    }
    if (ag.sel) { $('#ag-salvo').textContent = ''; clearTimeout(ag._t); ag._t = setTimeout(() => agSalvar(true), 1200); }
  });
  ed.addEventListener('change', e => {
    if (e.target.id === 'cp-grid') { ag.capaGrid = e.target.checked; $('.cp-opcoes')?.classList.toggle('grid3x4', ag.capaGrid); return; }
    if (e.target.id === 'ag-up') return agUpload(e.target.files[0]);
    if (e.target.dataset?.f === 'on') {
      const sec = e.target.closest('.ag-net');
      sec.classList.toggle('on', e.target.checked);
      sec.classList.toggle('off', !e.target.checked);
    }
    if (ag.sel && (e.target.dataset?.f || e.target.dataset?.o)) agSalvar(true);
  });
}

function agColetarSeguro() { try { return $('#ag-editor .ag-net') ? agColetar() : {}; } catch { return {}; } }

async function agUpload(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  toast('Enviando o vídeo…', false, 60000);
  try {
    const r = await fetch('/api/agenda-upload', { method: 'POST', body: fd }).then(x => x.json());
    ag.arquivos = null;
    toast('Vídeo enviado ✓');
    if (ag.sel) { const p = await api(`/api/agenda/${ag.sel.id}`, { method: 'PUT', json: { arquivo: r.arquivo } }); ag.sel = p; return agEditor(); }
    return agNovo({ arquivo: r.arquivo, dia: ag.escolher?.dia, k: ag.escolher?.k });
  } catch (e) { toast('Não enviou: ' + e.message, true); }
}
