// Editor de vídeos — interface. Sem build: JS puro.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const state = {
  status: null,
  p: null,          // projeto
  c: null,          // dados calculados pelo servidor (trechos, legendas, inserções)
  history: [], future: [],
  wave: [],
  curWord: -1,
  ovEls: {},
  motionEls: {},
  sel: null,        // [i0, i1]
  filter: 'all',
  lastOut: 0,
  formatos: [],
};

const ENGINE_LABEL = {
  regras: 'Regras locais (grátis)',
  ollama: 'IA local Ollama (grátis)',
  claude_api: 'Claude API (pago)',
};
const TYPE_INFO = {
  text: ['Aa', 'Texto'], media: ['▣', 'B-roll'], motion: ['✦', 'Motion'], sfx: ['♪', 'Som'],
  zoom: ['⊕', 'Zoom'], flash: ['✺', 'Flash'], behind: ['◐', 'Texto atrás'], perspective: ['◇', '3D'],
  emphasis: ['★', 'Destaque'],
};
const VISUAL = new Set(['text', 'media', 'motion', 'behind', 'perspective', 'emphasis']);
const SOURCE_HINT = {
  wikipedia: 'Fotos reais de pessoas, empresas, lugares e eventos citados — e prints de artigos.',
  commons: 'Fotos históricas, documentos, mapas, ilustrações e vídeos (Wikimedia Commons).',
  arquivo: 'Filmes antigos de domínio público — ótimos para metáforas visuais. Busque em inglês.',
  nasa: 'Imagens e vídeos da NASA (domínio público).',
  noticias: 'Manchetes recentes: vira um card limpo com logo, título e foto da matéria. (RSS para uso pessoal)',
  site: 'Cole a URL de qualquer página para virar um card de manchete ou um print.',
  meus: 'Arquivos que você já subiu ou baixou neste projeto.',
};

// ------------------------------------------------------------------ utilidades
const fmt = (t) => {
  t = Math.max(0, t || 0);
  return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
};
async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json !== undefined) {
    o.body = JSON.stringify(o.json);
    o.headers = { 'Content-Type': 'application/json' };
    delete o.json;
  }
  const r = await fetch(path, o);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(msg);
  }
  return r.json();
}
function toast(msg, err = false, ms = 3500) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast' + (err ? ' err' : '');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add('hidden'), ms);
}
function show(view) { $$('.view').forEach(v => v.classList.toggle('hidden', v.id !== view)); }
async function waitJob(id, onProgress) {
  while (true) {
    const j = await api(`/api/jobs/${id}`);
    onProgress && onProgress(j);
    if (j.status === 'done') return j;
    if (j.status === 'error') throw new Error(j.message || 'Falhou');
    await new Promise(r => setTimeout(r, 700));
  }
}
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const mediaUrl = (f) => `/media/${state.p.id}/${f}`;
const assetUrl = (f) => mediaUrl('assets/' + encodeURIComponent(f));
const isVideo = f => /\.(mp4|mov|m4v|webm|mkv)$/i.test(f || '');
const uid = () => Math.random().toString(36).slice(2, 10);
function dialog(html) {
  $('#dialog-body').innerHTML = html;
  $('#dialog').classList.remove('hidden');
  return $('#dialog-body');
}
$$('[data-close]').forEach(b => b.onclick = () => b.closest('.modal').classList.add('hidden'));

async function loadStatus() {
  state.status = await api('/api/status');
  state.formatos = await api('/api/formatos');
  const eng = state.status.engines;
  const opts = Object.entries(ENGINE_LABEL).map(([k, v]) =>
    `<option value="${k}" ${eng[k] ? '' : 'disabled'}>${v}${eng[k] ? '' : ' — indisponível'}</option>`).join('');
  $('#opt-engine').innerHTML = opts;
  $('#plan-engine').innerHTML = opts;
  const best = eng.claude_api ? 'claude_api' : eng.ollama ? 'ollama' : 'regras';
  $('#opt-engine').value = best;
  $('#plan-engine').value = best;
  const fopts = '<option value="">Padrão</option>' + state.formatos.map(f => `<option value="${esc(f.slug)}">${esc(f.name)}</option>`).join('');
  $('#opt-formato').innerHTML = fopts;
  $('#proj-formato').innerHTML = fopts;
  const pill = $('#engine-pill');
  pill.textContent = eng.claude_api ? 'Claude API ligada' : eng.ollama ? 'IA local (Ollama) ligada' : 'Modo 100% gratuito';
  pill.classList.toggle('on', true);
  if (document.activeElement !== $('#vocab')) $('#vocab').value = (state.status.vocab || []).join('\n');
}

// ------------------------------------------------------------------ início
async function loadHome() {
  show('home');
  history.replaceState(null, '', '/');
  await loadStatus();
  const list = await api('/api/projects');
  const box = $('#projects');
  box.innerHTML = list.length ? '' : '<div class="empty">Nenhum projeto ainda.</div>';
  for (const p of list) {
    const el = document.createElement('div');
    el.className = 'pcard';
    el.innerHTML = `<div class="thumb" style="background-image:url('/media/${p.id}/thumb.jpg')"></div>
      <div class="meta"><div class="name"></div><div class="sub">${fmt(p.duration)} · ${new Date(p.updated * 1000).toLocaleDateString('pt-BR')}</div></div>
      <button class="del" title="Apagar">✕</button>`;
    $('.name', el).textContent = p.name;
    el.onclick = () => openProject(p.id);
    $('.del', el).onclick = async (e) => {
      e.stopPropagation();
      if (!confirm(`Apagar o projeto "${p.name}"?`)) return;
      await api(`/api/projects/${p.id}`, { method: 'DELETE' });
      loadHome();
    };
    box.appendChild(el);
  }
}

function setupDrop() {
  const drop = $('#drop');
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', e => { const f = e.dataTransfer.files[0]; if (f) upload(f); });
  $('#file').onchange = e => { const f = e.target.files[0]; if (f) upload(f); };
}

function upload(file) {
  show('processing');
  $('#proc-title').textContent = 'Enviando vídeo…';
  $('#proc-msg').textContent = file.name;
  const fd = new FormData();
  fd.append('file', file);
  fd.append('language', $('#opt-lang').value);
  fd.append('engine', $('#opt-engine').value);
  fd.append('formato', $('#opt-formato').value);
  fd.append('autofill', $('#opt-autofill').checked ? 'true' : 'false');
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/projects');
  xhr.upload.onprogress = e => { if (e.lengthComputable) $('#proc-bar').style.width = (e.loaded / e.total * 100) + '%'; };
  xhr.onload = async () => {
    if (xhr.status >= 300) {
      let m = 'Falha no envio';
      try { m = JSON.parse(xhr.responseText).detail; } catch {}
      toast(m, true); loadHome(); return;
    }
    const { project, job } = JSON.parse(xhr.responseText);
    await processing(project.id, job.id);
  };
  xhr.onerror = () => { toast('Falha no envio', true); loadHome(); };
  xhr.send(fd);
}

async function processing(pid, jobId) {
  show('processing');
  $('#proc-title').textContent = 'Editando seu vídeo…';
  $('#proc-bar').style.width = '0%';
  try {
    await waitJob(jobId, j => {
      $('#proc-bar').style.width = (j.progress * 100) + '%';
      $('#proc-msg').textContent = j.message || '';
    });
  } catch (e) { toast('Erro no processamento: ' + e.message, true, 8000); }
  openProject(pid);
}

// ------------------------------------------------------------------ formatos (referências)
async function loadFormatos() {
  show('formatos');
  history.replaceState(null, '', '#formatos');
  state.formatos = await api('/api/formatos');
  const box = $('#fmt-list');
  box.innerHTML = state.formatos.length ? '' : '<p class="empty">Nenhum formato ainda. Crie um e mande 2 a 5 vídeos de referência.</p>';
  for (const f of state.formatos) {
    const el = document.createElement('div');
    el.className = 'fmt';
    const m = f.metrics || {};
    el.innerHTML = `<div class="row"><h3></h3><div class="spacer"></div>
        <button class="tool add-ref">＋ Adicionar referências</button><button class="x ghost del">Apagar</button></div>
      ${f.metrics ? `<div class="metrics">
        <span>ritmo <b>${m.cuts_per_min}</b> cortes/min</span><span>plano médio <b>${m.avg_shot}s</b></span>
        <span>fala <b>${m.wpm}</b> palavras/min</span><span>tela <b>${m.aspect}</b></span>
        <span>estímulo visual a cada <b>${m.visual_interval}s</b></span><span>música <b>${m.music ? 'sim' : 'não'}</b></span></div>` : ''}
      <div class="brief"></div>
      <div class="label">Observações de estilo (o que você admira nessas referências — o planejador segue isso):</div>
      <textarea class="notes" placeholder="Ex.: usa muita manchete de jornal como prova, filmes antigos como metáfora, texto grande atrás da pessoa no gancho, cortes secos, legenda amarela…"></textarea>
      <div class="refs"></div>`;
    $('h3', el).textContent = f.name;
    $('.brief', el).textContent = f.brief || 'Adicione vídeos de referência para gerar o formato.';
    const notes = $('.notes', el);
    notes.value = f.notes || '';
    notes.onchange = async () => { await api(`/api/formatos/${f.slug}`, { method: 'PATCH', json: { notes: notes.value } }); toast('Observações salvas'); loadFormatos(); };
    $('.del', el).onclick = async () => { if (confirm(`Apagar o formato "${f.name}"?`)) { await api(`/api/formatos/${f.slug}`, { method: 'DELETE' }); loadFormatos(); } };
    $('.add-ref', el).onclick = () => addReferences(f.slug);
    const refs = $('.refs', el);
    for (const r of f.refs || []) {
      const stem = r.file.replace(/\.[^.]+$/, '');
      const rd = document.createElement('div');
      rd.className = 'ref';
      rd.innerHTML = `<img src="/formatos-media/${f.slug}/${encodeURIComponent(stem)}.sheet.jpg"><button class="x" title="Remover">✕</button>
        <div class="m"><b>${esc(r.file.replace(/^[a-f0-9]{6}_/, ''))}</b><br>${r.duration}s · ${r.aspect} · ${r.cuts_per_min} cortes/min · ${r.wpm} ppm${r.music ? ' · música' : ''}<br>
        <i>${esc(r.hook || '')}</i></div>`;
      $('.x', rd).onclick = async () => { await api(`/api/formatos/${f.slug}/refs/${encodeURIComponent(stem)}`, { method: 'DELETE' }); loadFormatos(); };
      refs.appendChild(rd);
    }
    box.appendChild(el);
  }
}

function addReferences(slug) {
  const inp = $('#ref-input');
  inp.value = '';
  inp.onchange = async () => {
    const files = [...inp.files];
    for (const [k, f] of files.entries()) {
      const fd = new FormData(); fd.append('file', f);
      toast(`Enviando referência ${k + 1}/${files.length}…`, false, 60000);
      try {
        const job = await api(`/api/formatos/${slug}/refs`, { method: 'POST', body: fd });
        await waitJob(job.id, j => toast(`Analisando ${f.name}: ${j.message || ''} ${Math.round(j.progress * 100)}%`, false, 60000));
      } catch (e) { toast(e.message, true, 8000); }
    }
    toast('Formato atualizado!');
    loadFormatos();
  };
  inp.click();
}

// ------------------------------------------------------------------ editor
async function openProject(pid) {
  const p = await api(`/api/projects/${pid}`);
  if (p.status === 'processing' && p.job) {
    try { await api(`/api/jobs/${p.job}`); return processing(pid, p.job); } catch {}
  }
  if (p.status !== 'ready') { toast('Esse projeto não terminou de processar.', true); return loadHome(); }
  if (!state.status) await loadStatus();
  history.replaceState(null, '', '#' + pid);
  state.p = p; state.c = p.computed; state.history = []; state.future = [];
  state.ovEls = {}; $('#ov-layer').innerHTML = '';
  state.motionEls = {}; $('#motion-layer').innerHTML = '';
  show('editor');
  $('#pname').value = p.name;
  $('#proj-formato').value = p.formato || '';
  const v = $('#video');
  v.src = mediaUrl(p.preview || p.source.file);
  v.currentTime = state.c.segments[0]?.start || 0;
  if (!p.preview && p.source.hdr !== null) ensureProxy(p);
  api(`/api/projects/${pid}/waveform`).then(w => { state.wave = w; drawTimeline(); });
  tl.zoom = 1; tl.v0 = 0; tl.sel = null; $('#tl-zoom').value = 1;
  state.gradeCss = '';
  renderAll();
  updateGradePreview();
}

async function ensureProxy(p) {
  // vídeos HDR do iPhone: a prévia usa uma cópia com cor normal (senão o navegador mostra "estourado")
  try {
    const job = await api(`/api/projects/${p.id}/proxy`, { method: 'POST' });
    const j = await waitJob(job.id);
    if (j.result.preview && state.p?.id === p.id) {
      const v = $('#video'), t = v.currentTime;
      v.src = mediaUrl('preview.mp4'); v.currentTime = t;
      state.p.preview = 'preview.mp4';
      toast('Prévia com cor corrigida pronta');
    }
  } catch {}
}

function applyServer(p) { state.p = p; state.c = p.computed; renderAll(); }

function snapshot() { return { deleted: state.p.deleted, overlays: state.p.overlays, settings: state.p.settings, manual: state.p.manual || [] }; }
async function patch(body, record = true) {
  const regrade = body.settings && ('grade' in body.settings || 'grade_strength' in body.settings);
  if (record) {
    state.history.push(snapshot());
    if (state.history.length > 200) state.history.shift();
    state.future = [];
  }
  try { applyServer(await api(`/api/projects/${state.p.id}`, { method: 'PATCH', json: body })); if (regrade) updateGradePreview(); }
  catch (e) { toast(e.message, true); }
}
function undo() { const h = state.history.pop(); if (!h) return; state.future.push(snapshot()); patch(h, false); }
function redo() { const h = state.future.pop(); if (!h) return; state.history.push(snapshot()); patch(h, false); }

function renderAll() {
  renderStats();
  renderTranscript();
  renderAnalysis();
  renderOverlays();
  renderStyle();
  layoutFrame();
  drawTimeline();
  tick(true);
}

function renderStats() {
  const c = state.c, p = state.p;
  const pend = p.overlays.filter(o => o.type === 'media' && !o.file).length;
  $('#stats').innerHTML = `${fmt(p.source.duration)} → <b>${fmt(c.duration)}</b> · ${c.cuts.length} cortes · ${c.overlays.length} inserções${pend ? ` · <span style="color:var(--ov)">${pend} B-roll pendentes</span>` : ''}`;
  $('#t-tot').textContent = fmt(c.duration);
  $('#ov-count').textContent = c.overlays.length || '';
}

// ------------------------------------------------------------------ transcrição
function renderTranscript() {
  const box = $('#transcript');
  const scroll = box.scrollTop;
  const { words } = state.p;
  const del = new Set(state.p.deleted);
  const aiDel = new Set();
  const reasons = {};
  for (const c of state.p.ai_cuts || []) for (let i = c.start; i <= c.end; i++) { aiDel.add(i); reasons[i] = c.reason; }
  const ovWords = new Set();
  for (const o of state.p.overlays) if (VISUAL.has(o.type)) for (let i = o.w0; i <= (o.w1 ?? o.w0); i++) ovWords.add(i);
  const maxPause = state.c.settings.max_pause;

  if (!words.length) { box.innerHTML = '<p class="hint">Nenhuma fala detectada neste vídeo.</p>'; return; }
  let html = '<p>';
  for (let k = 0; k < words.length; k++) {
    const w = words[k];
    if (k > 0) {
      const gap = w.start - words[k - 1].end;
      const sentenceEnd = /[.?!]$/.test(words[k - 1].w);
      if (gap > 1.6 || (sentenceEnd && gap > 0.9)) html += '</p><p>';
      if (gap >= 0.5) html += `<span class="pause${gap > maxPause ? ' cut' : ''}">${gap.toFixed(1)}s</span> `;
    }
    if (!w.w) { html += `<span class="w" data-i="${k}" hidden></span>`; continue; }
    let cls = 'w';
    if (del.has(k)) cls += ' del' + (aiDel.has(k) ? ' ai' : '');
    if (ovWords.has(k)) cls += ' ovw';
    if ((w.p ?? 1) < 0.5 && !w.edited) cls += ' dub';
    if (w.edited || w.fixed) cls += ' edited';
    const tip = reasons[k] ? `Cortado: ${reasons[k]}` : w.fixed && w.fixed !== true ? `Corrigido: ${w.fixed}` : '';
    const title = tip ? ` title="${esc(tip)}"` : '';
    html += `<span class="${cls}" data-i="${k}"${title}>${esc(w.w)}</span> `;
  }
  box.innerHTML = html + '</p>';
  box.scrollTop = scroll;
  state.curWord = -1;
}

function selectionRange() {
  const s = window.getSelection();
  if (!s || s.isCollapsed || !s.rangeCount) return null;
  const box = $('#transcript');
  if (!box.contains(s.anchorNode) || !box.contains(s.focusNode)) return null;
  const r = s.getRangeAt(0);
  const spans = $$('[data-i]', box).filter(el => r.intersectsNode(el));
  if (!spans.length) return null;
  return [+spans[0].dataset.i, +spans.at(-1).dataset.i];
}

function updateSelbar() {
  const r = selectionRange();
  const bar = $('#selbar');
  state.sel = r;
  if (!r) { bar.classList.add('hidden'); return; }
  const rect = window.getSelection().getRangeAt(0).getBoundingClientRect();
  bar.classList.remove('hidden');
  const bw = bar.offsetWidth;
  bar.style.left = Math.max(8, Math.min(window.innerWidth - bw - 8, rect.left + rect.width / 2 - bw / 2)) + 'px';
  bar.style.top = Math.max(8, rect.top - 46) + 'px';
}
function clearSel() { window.getSelection().removeAllRanges(); $('#selbar').classList.add('hidden'); }

function setDeleted(range, cut) {
  const d = new Set(state.p.deleted);
  for (let i = range[0]; i <= range[1]; i++) cut ? d.add(i) : d.delete(i);
  clearSel();
  patch({ deleted: [...d] });
}

// ------------------------------------------------------------------ edição do texto (legenda)
async function saveWords(i0, i1, text) {
  const old = state.p.words.slice(i0, i1 + 1).map(w => w.w).filter(Boolean).join(' ');
  if (text.trim() === old.trim()) return;
  state.history.push(snapshot());
  try {
    const r = await api(`/api/projects/${state.p.id}/words`, { method: 'POST', json: { i0, i1, text } });
    applyServer(r);
    toast(r.learned?.length ? `Texto corrigido · "${r.learned.join(', ')}" entrou no vocabulário` : 'Texto corrigido');
  } catch (e) { toast(e.message, true); }
}

function editWordsInline([i0, i1]) {
  const box = $('#transcript');
  const spans = $$('[data-i]', box).filter(el => +el.dataset.i >= i0 && +el.dataset.i <= i1);
  if (!spans.length) return;
  const text = state.p.words.slice(i0, i1 + 1).map(w => w.w).filter(Boolean).join(' ');
  const inp = document.createElement('input');
  inp.className = 'w-edit';
  inp.value = text;
  inp.style.width = Math.max(80, text.length * 9 + 30) + 'px';
  spans[0].before(inp);
  spans.forEach(sp => sp.hidden = true);
  inp.focus(); inp.select();
  let done = false;
  const finish = save => {
    if (done) return; done = true;
    if (save) saveWords(i0, i1, inp.value); else { inp.remove(); spans.forEach(sp => sp.hidden = !sp.textContent); }
  };
  inp.addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); });
  inp.addEventListener('blur', () => finish(true));
}

function setupCaptionEditing() {
  // com o vídeo pausado, clicar na legenda/destaque permite corrigir o texto ali mesmo
  $('#cap-layer').addEventListener('click', e => {
    const el = e.target.closest('[data-i0]');
    if (!el || !$('#video').paused) return;
    e.stopPropagation();
    if (el.isContentEditable) return;
    const i0 = +el.dataset.i0, i1 = +el.dataset.i1;
    state.editingCap = true;
    el.textContent = state.p.words.slice(i0, i1 + 1).map(w => w.w).filter(Boolean).join(' ');
    el.contentEditable = 'true';
    el.focus();
    const sel = window.getSelection(); sel.selectAllChildren(el); sel.collapseToEnd();
    let done = false;
    const finish = save => {
      if (done) return; done = true;
      el.contentEditable = 'false';
      state.editingCap = false;
      $('#cap-layer')._h = null;
      if (save) saveWords(i0, i1, el.textContent.replace(/\s+/g, ' ').trim());
    };
    el.addEventListener('keydown', ev => {
      ev.stopPropagation();
      if (ev.key === 'Enter') { ev.preventDefault(); finish(true); }
      if (ev.key === 'Escape') finish(false);
    });
    el.addEventListener('blur', () => finish(true), { once: true });
  });
}

function setupTranscript() {
  const box = $('#transcript');
  box.addEventListener('click', e => {
    const w = e.target.closest('[data-i]');
    if (!w || !window.getSelection().isCollapsed) return;
    $('#video').currentTime = state.p.words[+w.dataset.i].start;
    tick(true);
  });
  box.addEventListener('dblclick', e => {
    const w = e.target.closest('[data-i]');
    if (!w) return;
    window.getSelection().removeAllRanges();
    const i = +w.dataset.i;
    editWordsInline([i, i]);
  });
  document.addEventListener('selectionchange', () => requestAnimationFrame(updateSelbar));
  $('#selbar').addEventListener('mousedown', e => e.preventDefault());
  $('#selbar').addEventListener('click', e => {
    const act = e.target.closest('[data-act]')?.dataset.act;
    const r = state.sel;
    if (!act || !r) return;
    const words = state.p.words.slice(r[0], r[1] + 1).map(w => w.w).join(' ');
    const base = { w0: r[0], w1: r[1] };
    if (act === 'cut') return setDeleted(r, true);
    if (act === 'restore') return setDeleted(r, false);
    clearSel();
    if (act === 'edit') return editWordsInline(r);
    if (act === 'emphasis') return addOverlay({ type: 'emphasis', key: '', ...base });
    if (act === 'search') return openSearch({ ...base, query: words, source: 'wikipedia' });
    if (act === 'media') return pickAsset(file => addOverlay({ type: 'media', file, layout: 'full', ...base }));
    if (act === 'text') return addOverlay({ type: 'text', style: 'keyword', text: words.slice(0, 40), ...base });
    if (act === 'motion') return addOverlay({ type: 'motion', template: 'lettering', params: { text: words.slice(0, 60) }, ...base });
    if (act === 'sfx') return addOverlay({ type: 'sfx', sfx: 'pop', w0: r[0], w1: r[0] });
    if (act === 'zoom') return addOverlay({ type: 'zoom', ...base });
    if (act === 'behind') return addOverlay({ type: 'behind', text: words.split(' ').slice(0, 2).join(' '), ...base });
    if (act === 'perspective') return addOverlay({ type: 'perspective', ...base });
  });
}

// ------------------------------------------------------------------ plano / análise
function renderAnalysis() {
  const box = $('#analysis');
  const pl = state.p.plan;
  if (!pl || !pl.analysis) { box.innerHTML = ''; return; }
  const a = pl.analysis;
  const label = { regras: 'regras locais', ollama: 'IA local', claude_api: 'Claude', claude_code: 'Claude Code' }[pl.engine] || pl.engine;
  box.innerHTML = `<div class="hint">Plano gerado por <b>${esc(label)}</b>.</div>
    ${a.hook ? `<div class="hook"><b>Gancho:</b> ${esc(a.hook)}</div>` : ''}
    ${a.summary && pl.engine !== 'regras' ? `<p class="muted">${esc(a.summary)}</p>` : ''}
    <div class="chips">${(a.sections || []).map(s => `<span class="chip" data-w="${s.start}">${esc(s.title)}</span>`).join('')}</div>`;
  $$('.chip', box).forEach(c => c.onclick = () => { $('#video').currentTime = state.p.words[+c.dataset.w].start; tick(true); });
}

async function runJob(btn, path, body, okMsg) {
  const label = btn.textContent;
  btn.disabled = true; btn.textContent = '⏳ trabalhando…';
  try {
    const job = await api(`/api/projects/${state.p.id}/${path}`, { method: 'POST', json: body || {} });
    state.history.push(snapshot());
    const j = await waitJob(job.id, j => { if (j.message) btn.textContent = '⏳ ' + j.message.slice(0, 40); });
    applyServer(await api(`/api/projects/${state.p.id}`));
    toast(okMsg(j.result), false, 6000);
    return j.result;
  } catch (e) { toast(e.message, true, 9000); }
  finally { btn.disabled = false; btn.textContent = label; }
}

// ------------------------------------------------------------------ inserções
function addOverlay(o) {
  o.id = uid();
  patch({ overlays: [...state.p.overlays, o] });
  document.querySelector('.tabs [data-tab="edicao"]').click();
  state.focus = o.id;
  toast(`${TYPE_INFO[o.type][1]} adicionado`);
}
function editOverlay(id, changes) {
  patch({ overlays: state.p.overlays.map(o => o.id === id ? { ...o, ...changes, auto: false } : o) });
}
function removeOverlay(id) { patch({ overlays: state.p.overlays.filter(o => o.id !== id) }); }

function pickAsset(cb, accept = 'image/*,video/*') {
  const inp = $('#asset-input');
  inp.accept = accept;
  inp.value = '';
  inp.onchange = async () => {
    const f = inp.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    toast('Enviando arquivo…');
    try { const r = await api(`/api/projects/${state.p.id}/assets`, { method: 'POST', body: fd }); cb(r.file, r.kind); }
    catch (e) { toast(e.message, true); }
  };
  inp.click();
}

function wordsText(w0, w1) {
  const t = state.p.words.slice(w0, (w1 ?? w0) + 1).map(w => w.w).join(' ');
  return t.length > 80 ? t.slice(0, 80) + '…' : t;
}

const MOTION_FIELDS = {
  lettering: [['text', 'Frase'], ['highlight', 'Palavras em destaque']],
  icone: [['icon', 'Emoji/ícone'], ['label', 'Rótulo']],
  lista: [['title', 'Título'], ['items', 'Itens (um por linha)', 'lines']],
  contador: [['value', 'Número'], ['prefix', 'Antes (ex.: R$ )'], ['suffix', 'Depois (ex.: mil)'], ['label', 'Legenda']],
  comparacao: [['left_label', 'Rótulo esquerda'], ['left', 'Esquerda'], ['right_label', 'Rótulo direita'], ['right', 'Direita']],
  card3d: [],
  carrossel3d: [],
};

function renderOverlays() {
  const filters = $('#ov-filters');
  const counts = {};
  for (const o of state.c.overlays) counts[o.type] = (counts[o.type] || 0) + 1;
  filters.innerHTML = `<span class="chip ${state.filter === 'all' ? 'on' : ''}" data-f="all">Tudo ${state.c.overlays.length}</span>` +
    Object.entries(counts).map(([t, n]) => `<span class="chip ${state.filter === t ? 'on' : ''}" data-f="${t}">${TYPE_INFO[t]?.[1] || t} ${n}</span>`).join('');
  $$('.chip', filters).forEach(c => c.onclick = () => { state.filter = c.dataset.f; renderOverlays(); });

  const list = $('#ov-list');
  list.innerHTML = '';
  const ovs = state.c.overlays.filter(o => state.filter === 'all' || o.type === state.filter).sort((a, b) => a.a - b.a);
  if (!ovs.length) list.innerHTML = '<p class="hint">Nenhuma inserção. Gere um plano ou selecione palavras na aba Fala.</p>';
  for (const o of ovs) {
    const el = document.createElement('div');
    el.className = 'card' + (state.focus === o.id ? ' focus' : '');
    const [ic, name] = TYPE_INFO[o.type] || ['?', o.type];
    el.innerHTML = `<div class="row"><span class="icon">${ic}</span><b>${name}</b><span class="muted">${fmt(o.a)}</span>
      ${o.auto ? '<span class="auto">auto</span>' : ''}<div class="spacer"></div>
      <button class="act go">ver</button><button class="x" title="Remover">✕</button></div>
      <div class="fields"></div>
      <div class="quote">“${esc(wordsText(o.w0, o.w1))}”${o.reason ? ` · <i>${esc(o.reason)}</i>` : ''}</div>`;
    const fields = $('.fields', el);
    $('.x', el).onclick = () => removeOverlay(o.id);
    $('.go', el).onclick = () => { $('#video').currentTime = Math.max(0, state.p.words[o.w0].start - 0.3); tick(true); };

    if (o.type === 'text') {
      fields.innerHTML = `<input type="text" class="txt"><select class="sty"><option value="title">Título no topo</option><option value="keyword">Palavra grande no centro</option><option value="lower">Faixa inferior (nome)</option></select>`;
      const t = $('.txt', fields); t.value = o.text || ''; t.onchange = () => editOverlay(o.id, { text: t.value });
      const s = $('.sty', fields); s.value = o.style || 'title'; s.onchange = () => editOverlay(o.id, { style: s.value });
    } else if (o.type === 'emphasis') {
      const words = (o.layout?.lines || []).flatMap(l => l.words.map(t => t.w));
      fields.innerHTML = `<label>Palavra em dourado <select class="key">${words.map(w => `<option>${esc(w)}</option>`).join('')}</select></label>
        <label>Modelo <select class="var"><option value="">Automático</option><option value="bigend">Justificado (palavra-chave enorme)</option><option value="stack">Bloco à direita</option></select></label>`;
      const k = $('.key', fields); k.value = (o.layout?.lines || []).find(l => l.gold)?.words[0]?.w || '';
      k.onchange = () => editOverlay(o.id, { key: k.value });
      const v = $('.var', fields); v.value = o.variant || ''; v.onchange = () => editOverlay(o.id, { variant: v.value || null });
    } else if (o.type === 'behind') {
      fields.innerHTML = `<input type="text" class="txt" placeholder="1–2 palavras">`;
      const t = $('.txt', fields); t.value = o.text || ''; t.onchange = () => editOverlay(o.id, { text: t.value });
    } else if (o.type === 'sfx') {
      fields.innerHTML = `<div class="row"><select class="sx">${state.status.sfx.map(s => `<option value="${s.name}">${esc(s.cat)} · ${esc(s.desc)}</option>`).join('')}</select><button class="act play-sfx">▶</button></div>`;
      const s = $('.sx', fields); s.value = o.sfx; s.onchange = () => editOverlay(o.id, { sfx: s.value });
      $('.play-sfx', fields).onclick = () => playSfx(s.value);
      const more = document.createElement('button'); more.className = 'act'; more.textContent = 'escolher outro…';
      more.onclick = () => openSfxPicker(o); $('.row', fields).appendChild(more);
    } else if (o.type === 'media') {
      if (o.file) {
        fields.innerHTML = `<div class="row">${isVideo(o.file) ? `<video class="thumb" src="${assetUrl(o.file)}" muted></video>` : `<img class="thumb" src="${assetUrl(o.file)}">`}
          <select class="lay"><option value="full">Tela cheia</option><option value="card">Card (fundo desfocado)</option><option value="card3d">Card 3D</option><option value="pip">Janela</option></select>
          <button class="act swap">trocar</button></div>`;
        const s = $('.lay', fields); s.value = o.layout || 'full'; s.onchange = () => editOverlay(o.id, { layout: s.value });
      } else {
        fields.innerHTML = `<div class="pending">⏳ Pendente: ${esc(o.desc || o.query || '')}</div>
          <div class="row"><button class="act swap">🔎 buscar (${esc(o.source || 'commons')})</button><button class="act up">＋ meu arquivo</button></div>`;
        $('.up', fields).onclick = () => pickAsset(file => editOverlay(o.id, { file }));
      }
      $('.swap', fields).onclick = () => openSearch({ overlay: o.id, query: o.query || wordsText(o.w0, o.w1), source: o.source || 'commons' });
    } else if (o.type === 'motion') {
      fields.innerHTML = `<select class="tpl">${Object.keys(state.status.templates).map(t => `<option value="${t}">${t}</option>`).join('')}</select>`;
      const s = $('.tpl', fields); s.value = o.template; s.onchange = () => editOverlay(o.id, { template: s.value });
      for (const [key, label, kind] of MOTION_FIELDS[o.template] || []) {
        const lab = document.createElement('label');
        lab.textContent = label;
        const inp = document.createElement(kind === 'lines' ? 'textarea' : 'input');
        const val = (o.params || {})[key];
        inp.value = kind === 'lines' ? (val || []).join('\n') : (val ?? '');
        inp.onchange = () => editOverlay(o.id, { params: { ...(o.params || {}), [key]: kind === 'lines' ? inp.value.split('\n').filter(Boolean) : inp.value } });
        lab.appendChild(inp);
        fields.appendChild(lab);
      }
      if (o.template === 'card3d') {
        const b = document.createElement('button'); b.className = 'act'; b.textContent = o.file ? 'trocar imagem' : '＋ escolher imagem';
        b.onclick = () => pickAsset(file => editOverlay(o.id, { file }), 'image/*'); fields.appendChild(b);
      }
      if (o.template === 'carrossel3d') {
        const b = document.createElement('button'); b.className = 'act'; b.textContent = `＋ imagens (${(o.params?.files || []).length})`;
        b.onclick = () => pickAsset(file => editOverlay(o.id, { params: { ...(o.params || {}), files: [...(o.params?.files || []), file] } }), 'image/*');
        fields.appendChild(b);
      }
    }
    list.appendChild(el);
  }
  state.focus = null;
}

const sfxCache = {};
function playSfx(name, vol = 1) {
  const s = state.status.sfx.find(x => x.name === name); if (!s) return;
  const a = sfxCache[name] || (sfxCache[name] = new Audio('/sfx/' + encodeURIComponent(s.file)));
  a.volume = Math.min(1, vol); a.currentTime = 0; a.play().catch(() => {});
}

// ------------------------------------------------------------------ busca de materiais
const search = { ctx: null, source: 'wikipedia', results: [] };
function openSearch(ctx) {
  search.ctx = ctx;
  search.source = ctx.source && ctx.source !== 'proprio' ? ctx.source : 'wikipedia';
  const tabs = $('#src-tabs');
  const srcs = { ...state.status.sources, meus: 'Meus arquivos' };
  tabs.innerHTML = Object.entries(srcs).map(([k, v]) => `<button data-v="${k}">${esc(v.replace(/ \(.*/, ''))}</button>`).join('');
  $$('button', tabs).forEach(b => b.onclick = () => { search.source = b.dataset.v; syncTabs(); doSearch(); });
  $('#src-q').value = ctx.query || '';
  $('#src-detail').classList.add('hidden');
  syncTabs();
  $('#search').classList.remove('hidden');
  doSearch();
}
function syncTabs() {
  $$('#src-tabs button').forEach(b => b.classList.toggle('on', b.dataset.v === search.source));
  $('#src-hint').textContent = SOURCE_HINT[search.source] || '';
}
async function doSearch() {
  const q = $('#src-q').value.trim();
  const box = $('#src-results');
  $('#src-detail').classList.add('hidden');
  if (search.source === 'meus') {
    const assets = await api(`/api/projects/${state.p.id}/assets`);
    search.results = assets.map(a => ({ mine: true, kind: a.kind, file: a.file, title: a.file.replace(/^[a-f0-9]{6}_/, ''), thumb: a.kind === 'image' ? assetUrl(a.file) : null }));
  } else {
    if (!q) { box.innerHTML = ''; return; }
    box.innerHTML = '<p class="hint">Buscando…</p>';
    try { search.results = await api(`/api/sources/search?source=${search.source}&q=${encodeURIComponent(q)}&lang=${state.p.language || 'pt'}`); }
    catch (e) { box.innerHTML = `<p class="hint">${esc(e.message)}</p>`; return; }
  }
  box.innerHTML = search.results.length ? '' : '<p class="hint">Nada encontrado. Tente outras palavras (em inglês costuma render mais no Commons/Arquivo/NASA).</p>';
  search.results.forEach((r, k) => {
    const el = document.createElement('div');
    el.className = 'res';
    const icon = r.kind === 'video' ? '▶' : r.kind === 'page' ? '📰' : '';
    el.innerHTML = `<div class="th" style="${r.thumb ? `background-image:url('${esc(r.thumb)}')` : ''}">${r.thumb ? '' : icon}</div>
      <div class="tt"></div><div class="kd">${r.kind === 'page' ? 'manchete / print' : r.kind === 'video' ? 'vídeo' : 'imagem'}</div>`;
    $('.tt', el).textContent = r.title;
    el.onclick = () => detail(r);
    box.appendChild(el);
  });
}

async function detail(r) {
  const d = $('#src-detail');
  d.classList.remove('hidden');
  if (r.mine) return useMaterial(r);
  let media = '';
  if (r.kind === 'image') media = `<img src="${esc(r.url || r.thumb)}">`;
  if (r.kind === 'video') media = '<p class="hint">Carregando prévia…</p>';
  if (r.kind === 'page') media = `<p>${esc(r.desc || '')}</p>`;
  d.innerHTML = `<b></b><div class="credit"></div>${media}
    <div class="row" style="margin-top:10px">
      ${r.kind === 'video' ? `<label class="muted">Início <input type="number" id="cl-start" value="0" min="0" step="0.5" style="width:80px"> s</label>
         <label class="muted">Duração <input type="number" id="cl-len" value="8" min="1" max="30" step="0.5" style="width:70px"> s</label>
         <button class="act" id="cl-here">usar o ponto atual da prévia</button>` : ''}
      ${r.kind === 'page' ? `<select id="pg-mode"><option value="card">Card de manchete limpo</option><option value="print">Print da página</option></select>` : ''}
      <div class="spacer"></div><a class="act" href="${esc(r.page_url || '#')}" target="_blank" rel="noopener">abrir fonte ↗</a>
      <button class="primary" id="use">Usar no vídeo</button></div>`;
  $('b', d).textContent = r.title;
  $('.credit', d).textContent = `${r.credit || ''} · licença: ${r.license || '?'}`;
  if (r.kind === 'video') {
    try {
      const { url } = await api('/api/sources/resolve', { method: 'POST', json: r });
      d.querySelector('.hint').outerHTML = `<video id="cl-vid" src="${esc(url)}" controls muted preload="metadata"></video>`;
      $('#cl-here').onclick = () => { $('#cl-start').value = $('#cl-vid').currentTime.toFixed(1); };
    } catch (e) { d.querySelector('.hint').textContent = 'Sem prévia: ' + e.message; }
  }
  $('#use').onclick = () => useMaterial(r);
  d.scrollIntoView({ behavior: 'smooth' });
}

async function useMaterial(r) {
  const ctx = search.ctx;
  $('#search').classList.add('hidden');
  if (r.mine) {
    if (ctx.overlay) return editOverlay(ctx.overlay, { file: r.file });
    return addOverlay({ type: 'media', file: r.file, layout: 'full', w0: ctx.w0, w1: ctx.w1 });
  }
  let oid = ctx.overlay;
  if (!oid) {   // cria a inserção já no lugar certo, depois preenche com o arquivo
    oid = uid();
    await patch({ overlays: [...state.p.overlays, { id: oid, type: 'media', file: null, layout: r.kind === 'page' ? 'card' : 'full', w0: ctx.w0, w1: ctx.w1, query: $('#src-q').value, source: search.source }] });
  }
  toast('Baixando material…', false, 30000);
  try {
    const job = await api(`/api/projects/${state.p.id}/fetch`, { method: 'POST', json: {
      result: r, overlay_id: oid,
      start: +($('#cl-start')?.value || 0), length: +($('#cl-len')?.value || 8), mode: $('#pg-mode')?.value || 'card' } });
    await waitJob(job.id);
    applyServer(await api(`/api/projects/${state.p.id}`));
    toast('Material adicionado ✓');
  } catch (e) { toast(e.message, true, 8000); }
}

// ------------------------------------------------------------------ estilo
function renderStyle() {
  const s = state.c.settings;
  $$('.seg[data-setting]').forEach(seg => {
    $$('button', seg).forEach(b => b.classList.toggle('on', String(s[seg.dataset.setting]) === b.dataset.v));
  });
  $('#set-upper').checked = !!s.uppercase;
  $('#set-accent').value = s.accent || '#C29A5B';
  const styles = state.status.styles || {};
  $('#set-style').innerHTML = Object.entries(styles).map(([k, v]) => `<option value="${k}">${esc(v.name)}</option>`).join('');
  $('#set-style').value = s.style || 'padrao';
  $('#style-default').checked = (state.status.default_style || 'padrao') === (s.style || 'padrao');
  const cur = styles[s.style || 'padrao'] || {};
  $('#style-desc').textContent = cur.description || '';
  $('#style-palette').innerHTML = Object.entries(cur.palette || {}).map(([n, h]) => `<span title="${h}"><i style="background:${h}"></i>${esc(n)}</span>`).join('');
  $('#set-capbox').checked = !!s.caption_box;
  $('#set-progress').checked = !!s.progress_bar;
  $('#set-voice').checked = !!s.voice;
  $('#set-inserts').checked = !!s.inserts;
  const sliders = [['#set-pause', 'max_pause', '#v-pause', v => v.toFixed(2) + 's'], ['#set-pad', 'pad', '#v-pad', v => v.toFixed(2) + 's'],
    ['#set-vol', 'music_volume', '#v-vol', v => Math.round(v * 100) + '%'], ['#set-sfx', 'sfx_volume', '#v-sfx', v => Math.round(v * 100) + '%'],
    ['#set-zoom', 'zoom_strength', '#v-zoom', v => '+' + Math.round((v - 1) * 100) + '%'],
    ['#set-grade', 'grade_strength', '#v-grade', v => Math.round(v * 100) + '%']];
  for (const [id, key, lab, f] of sliders) { $(id).value = s[key]; $(lab).textContent = f(+s[key]); }
  const mb = $('#music-box');
  mb.innerHTML = '';
  if (s.music) {
    mb.innerHTML = `<div class="card"><div class="row"><span>🎵</span><span class="name"></span><div class="spacer"></div><button class="x">✕</button></div></div>`;
    $('.name', mb).textContent = s.music.replace(/^[a-f0-9]{6}_/, '');
    $('.x', mb).onclick = () => patch({ settings: { music: null } });
  } else {
    const b = document.createElement('button');
    b.className = 'tool'; b.textContent = '＋ Adicionar música';
    b.onclick = () => pickAsset(file => patch({ settings: { music: file } }), 'audio/*');
    mb.appendChild(b);
  }
}

function setupStyle() {
  $$('.seg[data-setting]').forEach(seg => seg.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    patch({ settings: { [seg.dataset.setting]: b.dataset.v } });
  }));
  $('#set-upper').onchange = e => patch({ settings: { uppercase: e.target.checked } });
  $('#set-accent').onchange = e => patch({ settings: { accent: e.target.value } });
  $('#set-capbox').onchange = e => patch({ settings: { caption_box: e.target.checked } });
  $('#set-progress').onchange = e => patch({ settings: { progress_bar: e.target.checked } });
  const applyStyle = async () => {
    state.history.push(snapshot());
    applyServer(await api(`/api/projects/${state.p.id}/style`, { method: 'POST', json: { slug: $('#set-style').value, default: $('#style-default').checked } }));
    state.status = await api('/api/status');
    renderStyle(); updateGradePreview();
    toast('Identidade visual aplicada');
  };
  $('#set-style').onchange = applyStyle;
  $('#style-default').onchange = applyStyle;
  $('#set-voice').onchange = e => patch({ settings: { voice: e.target.checked } });
  $('#set-inserts').onchange = e => patch({ settings: { inserts: e.target.checked } });
  const live = (id, key, label, f) => {
    const el = $(id);
    el.oninput = () => { $(label).textContent = f(+el.value); };
    el.onchange = () => patch({ settings: { [key]: +el.value } });
  };
  live('#set-pause', 'max_pause', '#v-pause', v => v.toFixed(2) + 's');
  live('#set-pad', 'pad', '#v-pad', v => v.toFixed(2) + 's');
  live('#set-vol', 'music_volume', '#v-vol', v => Math.round(v * 100) + '%');
  live('#set-sfx', 'sfx_volume', '#v-sfx', v => Math.round(v * 100) + '%');
  live('#set-zoom', 'zoom_strength', '#v-zoom', v => '+' + Math.round((v - 1) * 100) + '%');
  live('#set-grade', 'grade_strength', '#v-grade', v => Math.round(v * 100) + '%');
}

// ------------------------------------------------------------------ player / prévia
const LOOK_CSS = {
  none: '', cinema: 'contrast(1.08) saturate(1.05) sepia(.12) hue-rotate(-6deg)', quente: 'sepia(.22) saturate(1.12)',
  frio: 'hue-rotate(12deg) saturate(.92) contrast(1.05)', pb: 'grayscale(1) contrast(1.18)', vintage: 'sepia(.45) contrast(.92) saturate(.85)',
  vivido: 'saturate(1.3) contrast(1.06)', kronos: 'url(#kronoslook)',
};
function aspect() {
  const f = state.c.settings.format, s = state.p.source;
  return { '9:16': 9 / 16, '1:1': 1, '16:9': 16 / 9 }[f] || (s.width / s.height) || 16 / 9;
}
function layoutFrame() {
  if (!state.c) return;
  const stage = $('.stage'), fr = $('#frame');
  const W = stage.clientWidth, H = stage.clientHeight, a = aspect();
  let w = W, h = W / a;
  if (h > H) { h = H; w = H * a; }
  fr.style.width = w + 'px'; fr.style.height = h + 'px';
  fr.classList.toggle('vertical', a < 1);
  fr.classList.toggle('contain', state.c.settings.format === 'original');
  $('#video').style.filter = [state.gradeCss, LOOK_CSS[state.c.settings.look]].filter(Boolean).join(' ');
  const st = state.c.settings;
  const hexA = (h, a) => { const n = parseInt((h || '#000000').slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
  fr.style.setProperty('--cap-color', st.caption_color || '#fff');
  fr.style.setProperty('--cap-shade', hexA(st.caption_outline, .7));
  fr.style.setProperty('--cap-box', hexA(st.caption_box_color, st.caption_box_opacity ?? .78));
  fr.style.setProperty('--progress', st.progress_color || st.accent);
  $('#progress-layer').style.display = st.progress_bar ? 'block' : 'none';
  document.body.classList.toggle('no-inserts', !state.c.settings.inserts);
}

function segIndexAt(t) {
  const segs = state.c.segments;
  for (let k = 0; k < segs.length; k++) if (t >= segs[k].start - 0.001 && t < segs[k].end) return k;
  return -1;
}
function toOutput(t) {
  for (const s of state.c.segments) {
    if (t < s.start) return s.out;
    if (t <= s.end) return s.out + (t - s.start);
  }
  const l = state.c.segments.at(-1);
  return l ? l.out + l.end - l.start : 0;
}

function loop() {
  requestAnimationFrame(loop);
  try { tick(); } catch (e) { console.error(e); }
}

function tick(force = false) {
  if (!state.c || $('#editor').classList.contains('hidden')) return;
  const v = $('#video');
  const segs = state.c.segments;
  let t = v.currentTime;
  let k = segIndexAt(t);
  if (!v.paused && k < 0) {
    const next = segs.find(s => s.start > t);
    if (next) { v.currentTime = next.start; t = next.start; k = segs.indexOf(next); } else v.pause();
  } else if (!v.paused && k >= 0 && segs[k].end - t < 0.03) {
    const n = segs[k + 1];
    if (!n) v.pause();
    else if (n.start - segs[k].end > 0.01) { v.currentTime = n.start; t = n.start; k++; }
  }
  const out = toOutput(t);
  $('#t-cur').textContent = fmt(out);
  $('#play').textContent = v.paused ? '▶' : '❚❚';
  $('#frame').classList.toggle('paused', v.paused);
  v.style.transform = k >= 0 && segs[k].zoom > 1 ? `scale(${segs[k].zoom})` : '';

  const active = state.c.overlays.filter(o => out >= o.a && out < o.b);
  $('#frame').classList.toggle('persp', active.some(o => o.type === 'perspective'));
  const fl = state.c.overlays.find(o => o.type === 'flash' && out >= o.a && out < o.a + 0.12);
  $('#flash-layer').style.opacity = fl ? (out - fl.a < 0.05 ? 0.85 : 0.35) : 0;
  if (!v.paused && out > state.lastOut && out - state.lastOut < 0.5) {
    for (const o of state.c.overlays) if (o.type === 'sfx' && o.a > state.lastOut && o.a <= out) playSfx(o.sfx, state.c.settings.sfx_volume * 1.4);
  }
  state.lastOut = out;

  const pb = $('#progress-layer div'); if (pb) pb.style.width = (100 * out / (state.c.duration || 1)).toFixed(2) + '%';
  renderCaption(out, active);
  renderOverlayPreview(out, v.paused, active);
  renderMotionPreview(out, active);
  highlightWord(t);
  drawPlayhead(t, force);
}

function applyCase(text, mode) {
  if (mode === 'upper') return text.toUpperCase();
  if (mode === 'lower') return text.split(' ').map(w => (w.length >= 2 && w === w.toUpperCase() && /[A-ZÀ-Ý]{2}/.test(w)) ? w : w.toLowerCase()).join(' ');
  return text;
}

function renderCaption(out, active) {
  const s = state.c.settings, layer = $('#cap-layer');
  if (state.editingCap) return;   // não redesenha enquanto você digita
  const kase = s.caption_case || 'lower';
  const [FW] = state.c.frame || [1080, 1920];
  const k = $('#frame').clientWidth / FW;    // escala: pixels do vídeo final -> prévia
  let html = '';
  const em = active.find(o => o.type === 'emphasis' && o.layout);
  if (em) {
    const L = em.layout;
    const toks = L.lines.flatMap(l => l.words);
    const total = L.lines.reduce((h, l) => h + l.size * 0.98, 0);
    const right = L.align === 'right';
    const pos = right ? `right:${(FW - L.x) * k}px;text-align:right` : `left:${L.x * k}px;transform:translateX(-50%);text-align:center`;
    const lines = L.lines.map(l => `<span class="ln${l.gold ? ' gold' : ''}" style="font-size:${l.size * k}px;letter-spacing:${-l.size * 0.045 * k}px">` +
      l.words.map(t => `<span class="t${out + 0.001 < Math.max(em.a, t.a) ? ' hide' : ''}">${esc(applyCase(t.w, kase))}</span>`).join(' ') + '</span>').join('');
    const i0 = toks[0].i, i1 = toks.at(-1).i;
    html = `<div class="emph" data-i0="${i0}" data-i1="${i1}" title="Clique para corrigir o texto" style="top:${(L.y - total / 2) * k}px;${pos};--gold:${s.accent || '#C29A5B'}">${lines}</div>`;
  } else if (s.captions !== 'none') {
    const c = state.c.captions.find(c => out >= c.a && out < c.b);
    if (c) {
      const i0 = c.words[0].i, i1 = c.words.at(-1).i;
      const cls = 'cap ' + (s.captions === 'clean' ? 'clean' + (s.caption_box ? ' boxed' : '') : s.captions === 'classic' ? 'classic' : '');
      const ws = c.words.map((w, j) => {
        const next = c.words[j + 1];
        const on = s.captions === 'pop' && out >= w.a && out < (next ? next.a : c.b);
        const t = esc(applyCase(w.w, kase));
        return on ? `<span class="hi">${t}</span>` : t;
      });
      let txt = ws.join(' ');
      if (s.captions === 'clean') txt = txt.replace(/[,;:]$/, '');
      html = `<div class="${cls}" data-i0="${i0}" data-i1="${i1}" title="Clique para corrigir o texto">${txt}</div>`;
    }
  }
  layer.classList.toggle('clean', !!em || s.captions === 'clean');
  if (layer._h !== html) { layer.innerHTML = html; layer._h = html; }
  const up = s.uppercase ? 'text-transform:uppercase' : '';
  const th = active.filter(o => o.type === 'text').map(t =>
    `<div class="${t.style === 'keyword' ? 'kw' : t.style === 'lower' ? 'lower' : 'ttl'}" style="${up}">${esc(t.text)}</div>`).join('');
  const tl = $('#title-layer');
  if (tl._h !== th) { tl.innerHTML = th; tl._h = th; }
  const bh = active.filter(o => o.type === 'behind').map(o => `<div>${esc(o.text)}</div>`).join('');
  const bl = $('#behind-layer');
  if (bl._h !== bh) { bl.innerHTML = bh; bl._h = bh; }
}

function renderOverlayPreview(out, paused, active) {
  const layer = $('#ov-layer');
  const on = new Set();
  for (const o of active) {
    if (o.type !== 'media' || !o.file || o.layout === 'card3d' && !isVideo(o.file)) continue;
    on.add(o.id);
    let el = state.ovEls[o.id];
    const key = o.file + '|' + o.layout;
    if (!el || el._key !== key) {
      el?.remove();
      const vid = isVideo(o.file);
      const src = assetUrl(o.file);
      const tag = vid ? `<video src="${src}" muted loop playsinline></video>` : `<img src="${src}">`;
      el = document.createElement('div');
      if (o.layout === 'card' || o.layout === 'card3d') {
        el.className = 'card';
        el.innerHTML = `<div class="bgimg" style="background-image:url('${vid ? '' : src}')"></div>` + tag.replace(/<(video|img)/, '<$1 class="fg"');
      } else {
        el.innerHTML = tag.replace(/<(video|img)/, `<$1 class="ov${o.layout === 'pip' ? ' pip' : ''}"`);
        el.style.cssText = 'position:absolute;inset:0';
      }
      el._key = key;
      layer.appendChild(el);
      state.ovEls[o.id] = el;
    }
    el.style.display = '';
    const vEl = el.querySelector('video');
    if (vEl) {
      const want = out - o.a + (o.clip_start || 0);
      if (vEl.duration && Math.abs(vEl.currentTime - (want % vEl.duration)) > 0.35) vEl.currentTime = want % vEl.duration;
      if (paused && !vEl.paused) vEl.pause();
      if (!paused && vEl.paused) vEl.play().catch(() => {});
    }
  }
  for (const [id, el] of Object.entries(state.ovEls)) {
    if (!on.has(id)) { el.style.display = 'none'; el.querySelector('video')?.pause(); }
  }
}

function motionSrc(o) {
  const vertical = aspect() < 1;
  const params = { ...(o.params || {}), dur: +(o.b - o.a).toFixed(2), vertical };
  let tpl = o.template;
  if (o.type === 'media') { tpl = 'card3d'; params.src = assetUrl(o.file); }
  if (tpl === 'card3d' && o.type === 'motion' && o.file) params.src = assetUrl(o.file);
  if (tpl === 'carrossel3d') params.files = (params.files || []).map(assetUrl);
  return `/motion/${tpl}.html#${encodeURIComponent(JSON.stringify(params))}`;
}
function renderMotionPreview(out, active) {
  const layer = $('#motion-layer');
  const on = new Set();
  for (const o of active) {
    const isMotion = o.type === 'motion' || (o.type === 'media' && o.layout === 'card3d' && o.file && !isVideo(o.file));
    if (!isMotion) continue;
    on.add(o.id);
    const src = motionSrc(o);
    let el = state.motionEls[o.id];
    if (!el || el._src !== src) {
      el?.remove();
      el = document.createElement('iframe');
      el.src = src; el._src = src;
      layer.appendChild(el);
      state.motionEls[o.id] = el;
    }
    el.style.display = '';
    try { el.contentWindow.__seek && el.contentWindow.__seek(out - o.a); } catch {}
  }
  for (const [id, el] of Object.entries(state.motionEls)) if (!on.has(id)) el.style.display = 'none';
}

function highlightWord(t) {
  const words = state.p.words;
  let i = -1, lo = 0, hi = words.length - 1;
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (words[m].end < t) lo = m + 1; else if (words[m].start > t) hi = m - 1; else { i = m; break; }
  }
  if (i === state.curWord) return;
  $('#transcript .w.cur')?.classList.remove('cur');
  state.curWord = i;
  if (i < 0) return;
  const el = $(`#transcript [data-i="${i}"]`);
  if (!el) return;
  el.classList.add('cur');
  if (!$('#video').paused) {
    const box = $('#transcript'), r = el.getBoundingClientRect(), br = box.getBoundingClientRect();
    if (r.top < br.top + 30 || r.bottom > br.bottom - 60) box.scrollTop += r.top - br.top - br.height / 3;
  }
}

function togglePlay() {
  const v = $('#video');
  if (v.paused) {
    const segs = state.c.segments, last = segs.at(-1);
    if (!last) return;
    if (v.currentTime >= last.end - 0.05) v.currentTime = segs[0].start;
    v.play();
  } else v.pause();
}

// ------------------------------------------------------------------ timeline (editor por tempo)
const tl = { zoom: 1, v0: 0, sel: null, markIn: null, drag: null };
let tlBase = null;

function tlView() {
  const dur = state.p.source.duration;
  const span = dur / tl.zoom;
  tl.v0 = Math.max(0, Math.min(dur - span, tl.v0));
  return { dur, span, v0: tl.v0, v1: tl.v0 + span };
}
const tlX = (t, W) => { const v = tlView(); return (t - v.v0) / v.span * W; };
const tlT = (x, W) => { const v = tlView(); return v.v0 + x / W * v.span; };

function drawTimeline() {
  if (!state.c) return;
  const cv = $('#timeline');
  const dpr = devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext('2d');
  g.scale(dpr, dpr);
  const v = tlView();
  const x = t => tlX(t, W);
  const css = getComputedStyle(document.documentElement);
  const col = n => css.getPropertyValue(n).trim();
  const top = 26, bot = H - 18;
  g.fillStyle = '#2a161a';
  g.fillRect(0, top, W, bot - top);
  for (const s of state.c.segments) {
    if (s.end < v.v0 || s.start > v.v1) continue;
    g.fillStyle = s.zoom > 1.2 ? '#1b4e49' : '#123a37';
    g.fillRect(x(s.start), top, Math.max(1, x(s.end) - x(s.start)), bot - top);
  }
  const wave = state.wave;
  if (wave.length) {
    const mid = (top + bot) / 2, amp = (bot - top - 6) / 2;
    for (let px = 0; px < W; px++) {
      const t = tlT(px, W);
      const p = wave[Math.floor(t / v.dur * wave.length)] || 0;
      g.fillStyle = segIndexAt(t) >= 0 ? col('--accent') : '#6b3640';
      const h = Math.max(1, p * amp);
      g.fillRect(px, mid - h, 1, h * 2);
    }
  }
  // palavras (quando há zoom suficiente)
  const pxPerSec = W / v.span;
  if (pxPerSec > 45) {
    g.font = '11px Inter, sans-serif';
    g.textBaseline = 'bottom';
    const del = new Set(state.p.deleted);
    for (const w of state.p.words) {
      if (!w.w || w.end < v.v0 || w.start > v.v1) continue;
      g.fillStyle = del.has(w.i) ? '#a15d68' : '#e9ebf0';
      g.fillText(w.w, x(w.start) + 1, top - 2, Math.max(8, x(w.end) - x(w.start) + 30));
    }
  }
  // inserções: visuais em cima, sons como marcadores
  for (const o of state.p.overlays) {
    const a = state.p.words[o.w0]?.start ?? 0, b = state.p.words[o.w1 ?? o.w0]?.end ?? a;
    if (b < v.v0 || a > v.v1) continue;
    const vis = VISUAL.has(o.type);
    g.fillStyle = o.type === 'emphasis' ? (state.c.settings.accent || '#C29A5B') : vis ? col('--ov') : '#c9a2ff';
    if (vis) g.fillRect(x(a), 2, Math.max(3, x(b) - x(a)), 6);
    else { g.beginPath(); g.arc(x(a), bot + 9, 5, 0, 7); g.fill(); }
  }
  // régua
  g.fillStyle = '#8b91a0'; g.font = '10px Inter, sans-serif'; g.textBaseline = 'top';
  const step = [0.5, 1, 2, 5, 10, 15, 30, 60].find(st => st * pxPerSec > 70) || 60;
  for (let t = Math.ceil(v.v0 / step) * step; t < v.v1; t += step) {
    g.fillRect(x(t), bot, 1, 4);
    g.fillText(fmt(t) + (step < 1 ? '.' + Math.round((t % 1) * 10) : ''), x(t) + 2, bot + 4);
  }
  // seleção
  if (tl.sel) {
    const [a, b] = tl.sel;
    g.fillStyle = 'rgba(255,255,255,.16)';
    g.fillRect(x(a), 0, x(b) - x(a), H);
    g.fillStyle = '#fff';
    g.fillRect(x(a), 0, 1, H); g.fillRect(x(b), 0, 1, H);
  } else if (tl.markIn != null) {
    g.fillStyle = '#ffd60a'; g.fillRect(x(tl.markIn), 0, 2, H);
  }
  tlBase = g.getImageData(0, 0, cv.width, cv.height);
  drawPlayhead($('#video').currentTime, true);
  updateSelUI();
}
let lastHead = -1;
function drawPlayhead(t, force) {
  const cv = $('#timeline');
  if (!tlBase) return;
  const W = cv.clientWidth;
  // acompanha a agulha quando está com zoom e tocando
  const v = tlView();
  if (!$('#video').paused && tl.zoom > 1 && (t > v.v1 - v.span * 0.1 || t < v.v0)) { tl.v0 = t - v.span * 0.2; drawTimeline(); return; }
  const px = Math.round(tlX(t, W));
  if (px === lastHead && !force) return;
  lastHead = px;
  const g = cv.getContext('2d');
  g.putImageData(tlBase, 0, 0);
  g.fillStyle = '#fff';
  g.fillRect(px - 1, 0, 2, cv.clientHeight);
}
function updateSelUI() {
  const box = $('#tl-sel');
  if (!tl.sel) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  $('#tl-sel-txt').textContent = `${tl.sel[0].toFixed(2)}s → ${tl.sel[1].toFixed(2)}s (${(tl.sel[1] - tl.sel[0]).toFixed(2)}s)`;
}
function setZoom(z, anchorT) {
  const old = tlView();
  tl.zoom = Math.max(1, Math.min(80, z));
  const span = old.dur / tl.zoom;
  const t = anchorT ?? $('#video').currentTime;
  const frac = (t - old.v0) / old.span;   // o ponto âncora fica no mesmo lugar da tela
  tl.v0 = t - frac * span;
  $('#tl-zoom').value = tl.zoom;
  drawTimeline();
}
async function rangeEdit(mode, range) {
  const r = range || tl.sel || autoRange(mode);
  if (!r) return toast(mode === 'cut' ? 'Selecione um trecho na timeline (arraste) ou posicione a agulha numa palavra.' : 'Posicione a agulha num trecho cortado (vermelho) ou selecione um trecho.', true);
  state.history.push(snapshot());
  try {
    applyServer(await api(`/api/projects/${state.p.id}/range`, { method: 'POST', json: { a: r[0], b: r[1], mode } }));
    toast(mode === 'cut' ? 'Trecho cortado' : 'Trecho restaurado');
  } catch (e) { toast(e.message, true); }
  tl.sel = null; tl.markIn = null; drawTimeline();
}
function autoRange(mode) {
  // sem seleção: X corta a palavra sob a agulha; R restaura o trecho cortado onde a agulha está
  const t = $('#video').currentTime;
  if (mode === 'cut') {
    const w = state.p.words.find(w => w.w && t >= w.start - 0.05 && t <= w.end + 0.05);
    return w ? [w.start, w.end] : null;
  }
  if (segIndexAt(t) >= 0) return null;
  const segs = state.c.segments;
  const prev = [...segs].reverse().find(s => s.end <= t), next = segs.find(s => s.start >= t);
  return [prev ? prev.end : 0, next ? next.start : state.p.source.duration];
}
function setupTimeline() {
  const cv = $('#timeline');
  const tAt = e => { const r = cv.getBoundingClientRect(); return Math.max(0, Math.min(state.p.source.duration, tlT(e.clientX - r.left, r.width))); };
  cv.addEventListener('mousedown', e => {
    const r = cv.getBoundingClientRect();
    // clique num marcador de som abre o seletor de efeitos
    if (e.clientY - r.top > cv.clientHeight - 18) {
      const t = tAt(e);
      const o = state.c.overlays.find(o => o.type === 'sfx' && Math.abs((state.p.words[o.w0]?.start ?? -9) - t) < tlView().span / r.width * 8);
      if (o) return openSfxPicker(o);
    }
    const t0 = tAt(e), x0 = e.clientX;
    let dragging = false;
    const move = ev => {
      if (!dragging && Math.abs(ev.clientX - x0) > 4) dragging = true;
      if (dragging) { const t1 = tAt(ev); tl.sel = [Math.min(t0, t1), Math.max(t0, t1)]; drawTimeline(); }
    };
    const up = ev => {
      removeEventListener('mousemove', move); removeEventListener('mouseup', up);
      if (!dragging) { tl.sel = null; $('#video').currentTime = t0; tick(true); drawTimeline(); }
    };
    addEventListener('mousemove', move); addEventListener('mouseup', up);
  });
  cv.addEventListener('wheel', e => {
    e.preventDefault();
    const horizontal = Math.abs(e.deltaX) > Math.abs(e.deltaY) || e.shiftKey;
    if (horizontal) {   // trackpad para o lado ou shift+scroll: anda pela timeline
      tl.v0 += (e.deltaX || e.deltaY) / cv.clientWidth * tlView().span; drawTimeline(); return;
    }
    // scroll (ou pinça no trackpad): zoom mantendo fixo o ponto sob o cursor
    const factor = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0025));
    setZoom(tl.zoom * factor, tAt(e), e);
  }, { passive: false });
  $('#tl-zoom').oninput = e => setZoom(+e.target.value);
  $('#tl-in').onclick = () => setZoom(tl.zoom * 1.6);
  $('#tl-out').onclick = () => setZoom(tl.zoom / 1.6);
  $('#tl-cut').onclick = () => rangeEdit('cut');
  $('#tl-keep').onclick = () => rangeEdit('keep');
  $('#tl-clear').onclick = () => { tl.sel = null; tl.markIn = null; drawTimeline(); };
}

// ------------------------------------------------------------------ efeitos sonoros (seletor)
function openSfxPicker(o) {
  const lib = state.status.sfx;
  const cats = [...new Set(lib.map(s => s.cat))];
  const body = dialog(`<h3>Efeito sonoro</h3><p class="hint">Clique no ▶ para ouvir · clique no nome para usar.
      Sons livres para uso comercial (Mixkit / Freesound CC0). Para usar os seus, coloque arquivos na pasta <code>sfx/</code>.</p>
    <div class="sfx-grid">${cats.map(c => `<div class="sfx-cat"><h4>${esc(c)}</h4><div class="opts">${lib.filter(s => s.cat === c).map(s =>
      `<div class="sfx-opt ${s.name === o.sfx ? 'on' : ''}" data-n="${esc(s.name)}" title="${esc(s.desc)}"><span class="pl" data-play="${esc(s.name)}">▶</span>${esc(s.desc.split(' — ')[0])}</div>`).join('')}</div></div>`).join('')}</div>
    <div class="row" style="margin-top:12px"><button class="tool" id="sfx-remove">Remover este som</button></div>`);
  body.addEventListener('click', e => {
    const pl = e.target.closest('[data-play]');
    if (pl) { e.stopPropagation(); return playSfx(pl.dataset.play); }
    const opt = e.target.closest('[data-n]');
    if (opt) { editOverlay(o.id, { sfx: opt.dataset.n }); playSfx(opt.dataset.n); $('#dialog').classList.add('hidden'); }
  });
  $('#sfx-remove', body).onclick = () => { removeOverlay(o.id); $('#dialog').classList.add('hidden'); };
}

// ------------------------------------------------------------------ cor automática na prévia
async function updateGradePreview() {
  const s = state.c.settings;
  let svg = $('#grade-svg');
  if (!svg) {
    svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.id = 'grade-svg'; svg.setAttribute('width', 0); svg.setAttribute('height', 0); svg.style.position = 'absolute';
    document.body.appendChild(svg);
  }
  state.gradeCss = '';
  const kronos = `<filter id="kronoslook" color-interpolation-filters="sRGB"><feComponentTransfer>
      <feFuncR type="table" tableValues="0.082 0.29 0.535 0.775 0.99"/><feFuncG type="table" tableValues="0.047 0.255 0.5 0.745 0.97"/>
      <feFuncB type="table" tableValues="0.024 0.215 0.45 0.69 0.91"/></feComponentTransfer><feColorMatrix type="saturate" values="0.86"/></filter>`;
  svg.innerHTML = kronos;
  if (s.grade === 'auto') {
    try {
      const g = await api(`/api/projects/${state.p.id}/grade`);
      if (g.gains) {
        const lo = g.black, hi = g.white, e = (1 / g.gamma).toFixed(3);
        const fn = k => { const sl = (g.gains[k] / (hi - lo)).toFixed(4), ic = (-lo / (hi - lo) * g.gains[k]).toFixed(4);
          return `<feFuncR/>`.replace('R', 'RGB'[k]).replace('/>', ` type="linear" slope="${sl}" intercept="${ic}"/>`); };
        svg.innerHTML = kronos + `<filter id="autograde" color-interpolation-filters="sRGB"><feComponentTransfer>${fn(0)}${fn(1)}${fn(2)}</feComponentTransfer>
          <feComponentTransfer><feFuncR type="gamma" exponent="${e}"/><feFuncG type="gamma" exponent="${e}"/><feFuncB type="gamma" exponent="${e}"/></feComponentTransfer></filter>`;
        state.gradeCss = `url(#autograde) contrast(${g.contrast || 1}) saturate(${g.saturation})`;
      }
    } catch {}
  }
  layoutFrame();
}

// ------------------------------------------------------------------ exportação
async function exportVideo() {
  $('#video').pause();
  const pend = state.p.overlays.filter(o => o.type === 'media' && !o.file).length;
  if (pend && !confirm(`${pend} B-roll(s) ainda sem material serão ignorados. Exportar mesmo assim?`)) return;
  $('#modal').classList.remove('hidden');
  $('#modal-title').textContent = 'Exportando…';
  $('#exp-bar').style.width = '0%';
  $('#exp-msg').textContent = '';
  $('#exp-result').innerHTML = '';
  try {
    const job = await api(`/api/projects/${state.p.id}/render`, { method: 'POST' });
    const j = await waitJob(job.id, j => {
      $('#exp-bar').style.width = (j.progress * 100) + '%';
      $('#exp-msg').textContent = `${j.message || ''} ${Math.round(j.progress * 100)}%`;
    });
    $('#modal-title').textContent = 'Pronto! 🎉';
    $('#exp-msg').textContent = j.result.file;
    $('#exp-result').innerHTML = `<video controls src="${j.result.url}"></video>
      <div class="row"><a class="primary" href="${j.result.url}" download="${esc(j.result.file)}">Baixar MP4</a>
      ${j.result.credits ? `<a class="act" href="${j.result.credits}" target="_blank">créditos dos materiais</a>` : ''}</div>`;
  } catch (e) {
    $('#modal-title').textContent = 'Erro na exportação';
    $('#exp-msg').textContent = e.message;
  }
}

// ------------------------------------------------------------------ eventos gerais
function setup() {
  setupDrop();
  setupTranscript();
  setupStyle();
  setupTimeline();
  setupCaptionEditing();
  $('#vocab').onchange = async e => { await api('/api/vocab', { method: 'PUT', json: { text: e.target.value } }); toast('Vocabulário salvo'); };
  $('#go-formatos').onclick = loadFormatos;
  $$('.back-home').forEach(b => b.onclick = loadHome);
  $('#fmt-create').onclick = async () => {
    const name = $('#fmt-name').value.trim(); if (!name) return toast('Dê um nome ao formato', true);
    const f = await api('/api/formatos', { method: 'POST', json: { name } });
    $('#fmt-name').value = '';
    await loadFormatos();
    addReferences(f.slug);
  };
  $('#back').onclick = () => { $('#video').pause(); loadHome(); };
  $('#play').onclick = togglePlay;
  $('#frame').addEventListener('click', togglePlay);
  $('#undo').onclick = undo;
  $('#redo').onclick = redo;
  $('#export').onclick = exportVideo;
  $('#modal-close').onclick = () => { $('#modal').classList.add('hidden'); $('#exp-result').innerHTML = ''; };
  $('#pname').onchange = e => patch({ name: e.target.value }, false);
  $$('.tabs button').forEach(b => b.onclick = () => {
    $$('.tabs button').forEach(x => x.classList.toggle('on', x === b));
    $$('.tab').forEach(t => t.classList.toggle('hidden', t.id !== 'tab-' + b.dataset.tab));
  });
  $('#btn-autocut').onclick = async () => {
    state.history.push(snapshot());
    applyServer(await api(`/api/projects/${state.p.id}/autocut`, { method: 'POST', json: {} }));
    toast(`Hesitações cortadas · pausas acima de ${state.c.settings.max_pause}s removidas`);
  };
  $('#btn-clean').onclick = e => runJob(e.currentTarget, 'plan', { engine: $('#plan-engine').value }, r => `${r.cuts} trechos cortados (passe o mouse nas palavras roxas para ver o motivo) · plano atualizado`);
  $('#btn-restore-all').onclick = () => patch({ deleted: [], manual: [] });
  $('#btn-reprocess').onclick = e => {
    if (!confirm('Transcrever de novo com o motor mais preciso? Os cortes e destaques serão refeitos (suas correções de texto neste vídeo se perdem).')) return;
    runJob(e.currentTarget, 'reprocess', {}, r => `Transcrição refeita: ${r.words} palavras`);
  };
  $('#btn-plan').onclick = e => runJob(e.currentTarget, 'plan', { engine: $('#plan-engine').value }, r => `Plano pronto: ${r.items} inserções, ${r.cuts} cortes`);
  $('#btn-autofill').onclick = e => runJob(e.currentTarget, 'autofill', {}, r => `${r.filled} de ${r.pending} materiais encontrados` + (r.errors.length ? ` · ${r.errors.length} sem resultado` : ''));
  $('#btn-cc').onclick = async () => {
    const r = await api(`/api/projects/${state.p.id}/plan`, { method: 'POST', json: { engine: 'claude_code' } });
    const body = dialog(`<h3>Pedir ao Claude Code (grátis com sua assinatura)</h3>
      <p class="muted">Preparei o roteiro e as instruções em <code>${esc(r.brief)}</code>. Cole este pedido no Claude Code (na pasta do editor):</p>
      <textarea readonly style="width:100%;min-height:90px">${esc(r.prompt)}</textarea>
      <div class="row" style="margin-top:10px"><button class="primary" id="cc-copy">Copiar pedido</button>
      <span class="muted">Quando ele terminar, clique em <b>Carregar plano do Claude Code</b>.</span></div>`);
    $('#cc-copy', body).onclick = () => { navigator.clipboard.writeText(r.prompt); toast('Copiado!'); };
  };
  $('#btn-cc-load').onclick = e => runJob(e.currentTarget, 'plan/load', {}, r => `Plano do Claude Code aplicado: ${r.items} inserções, ${r.cuts} cortes`);
  $('#proj-formato').onchange = async e => {
    state.history.push(snapshot());
    applyServer(await api(`/api/projects/${state.p.id}/formato`, { method: 'POST', json: { slug: e.target.value } }));
    toast('Formato aplicado. Gere o plano de novo para seguir o ritmo dele.');
  };
  $('#src-go').onclick = doSearch;
  $('#src-q').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

  document.addEventListener('keydown', e => {
    if ($('#editor').classList.contains('hidden') || !$('#search').classList.contains('hidden')) return;
    if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) || document.activeElement.isContentEditable) return;
    if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
    else if (e.key === 'x' || e.key === 'X') { e.preventDefault(); if (state.sel) setDeleted(state.sel, true); else rangeEdit('cut'); }
    else if (e.key === 'r' || e.key === 'R') { e.preventDefault(); rangeEdit('keep'); }
    else if (e.key === 'i' || e.key === 'I') { tl.markIn = $('#video').currentTime; tl.sel = null; drawTimeline(); toast('Início marcado — vá até o fim e aperte O'); }
    else if ((e.key === 'o' || e.key === 'O') && tl.markIn != null) { const t = $('#video').currentTime; tl.sel = [Math.min(tl.markIn, t), Math.max(tl.markIn, t)]; tl.markIn = null; drawTimeline(); }
    else if (e.key === '=' || e.key === '+') setZoom(tl.zoom * 1.6);
    else if (e.key === '-') setZoom(tl.zoom / 1.6);
    else if ((e.key === 'Delete' || e.key === 'Backspace') && state.sel) { e.preventDefault(); setDeleted(state.sel, true); }
    else if ((e.key === 'Delete' || e.key === 'Backspace') && tl.sel) { e.preventDefault(); rangeEdit('cut'); }
    else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    else if (e.key === 'ArrowLeft') { $('#video').currentTime -= 2; }
    else if (e.key === 'ArrowRight') { $('#video').currentTime += 2; }
  });
  new ResizeObserver(() => { layoutFrame(); drawTimeline(); }).observe($('.stage-col'));
  loop();
}

function route() {
  const h = location.hash.slice(1);
  if (h === 'formatos') return loadStatus().then(loadFormatos);
  if (h && h !== state.p?.id) return openProject(h).catch(() => loadHome());
  if (!h) return loadHome();
}
setup();
window.addEventListener('hashchange', () => { $('#video').pause(); route(); });
route();
