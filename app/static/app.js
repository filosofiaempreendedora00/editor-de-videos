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
  sel: null,        // [i0, i1]
};

// ------------------------------------------------------------------ utilidades
const fmt = (t) => {
  t = Math.max(0, t || 0);
  const m = Math.floor(t / 60), s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
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
    try { msg = (await r.json()).detail || msg; } catch {}
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
function show(view) {
  $$('.view').forEach(v => v.classList.toggle('hidden', v.id !== view));
}
async function waitJob(id, onProgress) {
  while (true) {
    const j = await api(`/api/jobs/${id}`);
    onProgress && onProgress(j);
    if (j.status === 'done') return j;
    if (j.status === 'error') throw new Error(j.message || 'Falhou');
    await new Promise(r => setTimeout(r, 700));
  }
}
const mediaUrl = (f) => `/media/${state.p.id}/${f}`;
const assetUrl = (f) => mediaUrl('assets/' + encodeURIComponent(f));

// ------------------------------------------------------------------ início
async function loadHome() {
  show('home');
  history.replaceState(null, '', '/');
  state.status = await api('/api/status');
  const pill = $('#ai-pill');
  pill.textContent = state.status.ai ? `IA ligada · ${state.status.model}` : 'IA desligada (sem chave no .env)';
  pill.classList.toggle('on', state.status.ai);
  $('#opt-ai').checked = state.status.ai;
  $('#opt-ai').disabled = !state.status.ai;
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
  fd.append('auto_ai', $('#opt-ai').checked ? 'true' : 'false');
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
  $('#proc-title').textContent = 'Preparando seu vídeo…';
  $('#proc-bar').style.width = '0%';
  try {
    await waitJob(jobId, j => {
      $('#proc-bar').style.width = (j.progress * 100) + '%';
      $('#proc-msg').textContent = j.message || '';
    });
  } catch (e) {
    toast('Erro no processamento: ' + e.message, true, 8000);
  }
  openProject(pid);
}

// ------------------------------------------------------------------ editor
async function openProject(pid) {
  const p = await api(`/api/projects/${pid}`);
  if (p.status === 'processing' && p.job) {
    try { await api(`/api/jobs/${p.job}`); return processing(pid, p.job); } catch {}
  }
  if (p.status !== 'ready') { toast('Esse projeto não terminou de processar.', true); return loadHome(); }
  if (!state.status) state.status = await api('/api/status');
  history.replaceState(null, '', '#' + pid);
  state.p = p; state.c = p.computed; state.history = []; state.future = [];
  state.ovEls = {}; $('#ov-layer').innerHTML = '';
  show('editor');
  $('#pname').value = p.name;
  const v = $('#video');
  v.src = mediaUrl(p.source.file);
  v.currentTime = state.c.segments[0]?.start || 0;
  api(`/api/projects/${pid}/waveform`).then(w => { state.wave = w; drawTimeline(); });
  renderAll();
}

function applyServer(p) {
  state.p = p; state.c = p.computed;
  renderAll();
}

async function patch(body, record = true) {
  if (record) {
    state.history.push({ deleted: state.p.deleted, overlays: state.p.overlays, settings: state.p.settings });
    if (state.history.length > 200) state.history.shift();
    state.future = [];
  }
  try {
    applyServer(await api(`/api/projects/${state.p.id}`, { method: 'PATCH', json: body }));
  } catch (e) { toast(e.message, true); }
}
function undo() {
  const h = state.history.pop(); if (!h) return;
  state.future.push({ deleted: state.p.deleted, overlays: state.p.overlays, settings: state.p.settings });
  patch(h, false);
}
function redo() {
  const h = state.future.pop(); if (!h) return;
  state.history.push({ deleted: state.p.deleted, overlays: state.p.overlays, settings: state.p.settings });
  patch(h, false);
}

function renderAll() {
  renderStats();
  renderTranscript();
  renderOverlays();
  renderStyle();
  layoutFrame();
  drawTimeline();
  tick(true);
}

function renderStats() {
  const c = state.c, p = state.p;
  $('#stats').innerHTML = `${fmt(p.source.duration)} → <b>${fmt(c.duration)}</b> · ${c.segments.length} cortes · −${Math.round(c.removed_seconds)}s`;
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
  for (const o of state.p.overlays) for (let i = o.w0; i <= o.w1; i++) ovWords.add(i);
  const maxPause = state.c.settings.max_pause;

  if (!words.length) { box.innerHTML = '<p class="hint">Nenhuma fala detectada neste vídeo.</p>'; return; }
  let html = '<p>';
  for (let k = 0; k < words.length; k++) {
    const w = words[k];
    if (k > 0) {
      const gap = w.start - words[k - 1].end;
      const sentenceEnd = /[.?!]$/.test(words[k - 1].w);
      if (gap > 1.6 || (sentenceEnd && gap > 0.9)) html += '</p><p>';
      if (gap >= 0.5) html += `<span class="pause${gap > maxPause ? ' cut' : ''}" title="pausa">${gap.toFixed(1)}s</span> `;
    }
    let cls = 'w';
    if (del.has(k)) cls += ' del' + (aiDel.has(k) ? ' ai' : '');
    if (ovWords.has(k)) cls += ' ovw';
    const title = reasons[k] ? ` title="IA: ${escapeAttr(reasons[k])}"` : '';
    html += `<span class="${cls}" data-i="${k}"${title}>${escapeHtml(w.w)}</span> `;
  }
  box.innerHTML = html + '</p>';
  box.scrollTop = scroll;
  state.curWord = -1;
}
const escapeHtml = s => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const escapeAttr = s => escapeHtml(s).replace(/"/g, '&quot;');

function selectionRange() {
  const s = window.getSelection();
  if (!s || s.isCollapsed) return null;
  const box = $('#transcript');
  if (!box.contains(s.anchorNode) || !box.contains(s.focusNode)) return null;
  const idx = (node, preferNext) => {
    let el = node.nodeType === 3 ? node.parentElement : node;
    const w = el.closest && el.closest('[data-i]');
    if (w) return +w.dataset.i;
    // seleção começou num espaço/pausa: procura a palavra vizinha
    let n = el;
    while (n && n !== box) {
      const sib = preferNext ? n.nextElementSibling : n.previousElementSibling;
      if (sib) { const q = sib.matches('[data-i]') ? sib : (preferNext ? sib.querySelector('[data-i]') : [...sib.querySelectorAll('[data-i]')].pop()); if (q) return +q.dataset.i; n = sib; }
      else n = n.parentElement;
    }
    return null;
  };
  const r = s.getRangeAt(0);
  const a = idx(r.startContainer, true), b = idx(r.endContainer, false);
  if (a == null || b == null) return null;
  return [Math.min(a, b), Math.max(a, b)];
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

function setDeleted(range, cut) {
  const d = new Set(state.p.deleted);
  for (let i = range[0]; i <= range[1]; i++) cut ? d.add(i) : d.delete(i);
  window.getSelection().removeAllRanges();
  $('#selbar').classList.add('hidden');
  patch({ deleted: [...d] });
}

function setupTranscript() {
  const box = $('#transcript');
  box.addEventListener('click', e => {
    const w = e.target.closest('[data-i]');
    if (!w || !window.getSelection().isCollapsed) return;
    const word = state.p.words[+w.dataset.i];
    $('#video').currentTime = word.start;
    tick(true);
  });
  box.addEventListener('dblclick', e => {
    const w = e.target.closest('[data-i]');
    if (!w) return;
    window.getSelection().removeAllRanges();
    const i = +w.dataset.i;
    setDeleted([i, i], !state.p.deleted.includes(i));
  });
  document.addEventListener('selectionchange', () => requestAnimationFrame(updateSelbar));
  $('#selbar').addEventListener('mousedown', e => e.preventDefault());
  $('#selbar').addEventListener('click', e => {
    const act = e.target.closest('[data-act]')?.dataset.act;
    const r = state.sel;
    if (!act || !r) return;
    if (act === 'cut') setDeleted(r, true);
    if (act === 'restore') setDeleted(r, false);
    if (act === 'media') pickAsset(file => addOverlay({ type: 'media', file, w0: r[0], w1: r[1], layout: 'full' }));
    if (act === 'text') {
      const guess = state.p.words.slice(r[0], r[1] + 1).map(w => w.w).join(' ');
      const text = prompt('Texto que aparece na tela:', guess.slice(0, 60));
      if (text) addOverlay({ type: 'text', text, w0: r[0], w1: r[1] });
    }
  });
}

// ------------------------------------------------------------------ inserções
function addOverlay(o) {
  o.id = Math.random().toString(36).slice(2, 10);
  window.getSelection().removeAllRanges();
  $('#selbar').classList.add('hidden');
  patch({ overlays: [...state.p.overlays, o] });
  toast('Inserção adicionada');
}

function pickAsset(cb, accept = 'image/*,video/*') {
  const inp = $('#asset-input');
  inp.accept = accept;
  inp.value = '';
  inp.onchange = async () => {
    const f = inp.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    toast('Enviando arquivo…');
    try {
      const r = await api(`/api/projects/${state.p.id}/assets`, { method: 'POST', body: fd });
      cb(r.file, r.kind);
    } catch (e) { toast(e.message, true); }
  };
  inp.click();
}

function wordsText(w0, w1) {
  const t = state.p.words.slice(w0, w1 + 1).map(w => w.w).join(' ');
  return t.length > 90 ? t.slice(0, 90) + '…' : t;
}

function renderOverlays() {
  const list = $('#ov-list');
  list.innerHTML = '';
  const ovs = [...state.c.overlays].sort((a, b) => a.a - b.a);
  if (ovs.length) list.insertAdjacentHTML('beforeend', '<div class="group-title">Na timeline</div>');
  for (const o of ovs) {
    const el = document.createElement('div');
    el.className = 'card';
    const isMedia = o.type === 'media';
    const isVid = isMedia && /\.(mp4|mov|m4v|webm|mkv)$/i.test(o.file);
    el.innerHTML = `<div class="row">
        <span class="kind">${isMedia ? 'Mídia' : 'Texto'} · ${fmt(o.a)}</span><div class="spacer"></div>
        <button class="act go">ver</button><button class="x" title="Remover">✕</button></div>
      <div class="row" style="margin-top:6px">
        ${isMedia ? (isVid ? `<video class="thumb" src="${assetUrl(o.file)}" muted></video>` : `<img class="thumb" src="${assetUrl(o.file)}">`)
                  : '<input type="text" class="txt">'}
        ${isMedia ? `<select class="layout"><option value="full">Tela cheia</option><option value="pip">Janela</option></select>` : ''}
      </div>
      <div class="quote">“${escapeHtml(wordsText(o.w0, o.w1))}”</div>`;
    if (!isMedia) { const t = $('.txt', el); t.value = o.text; t.onchange = () => editOverlay(o.id, { text: t.value }); }
    else { const s = $('.layout', el); s.value = o.layout || 'full'; s.onchange = () => editOverlay(o.id, { layout: s.value }); }
    $('.x', el).onclick = () => patch({ overlays: state.p.overlays.filter(x => x.id !== o.id) });
    $('.go', el).onclick = () => { $('#video').currentTime = state.p.words[o.w0].start; tick(true); };
    list.appendChild(el);
  }

  const sl = $('#sugg-list');
  sl.innerHTML = '';
  const sugg = state.p.suggestions || [];
  if (sugg.length) sl.insertAdjacentHTML('beforeend', '<div class="group-title">Ideias de imagens de apoio (B-roll)</div>');
  for (const s of sugg) {
    const el = document.createElement('div');
    el.className = 'card';
    el.innerHTML = `<div class="row"><span class="kind sug">Sugestão IA</span><div class="spacer"></div>
        <button class="act add">＋ adicionar arquivo</button>
        <a class="act" target="_blank" rel="noopener">buscar</a>
        <button class="x" title="Descartar">✕</button></div>
      <div style="margin-top:4px"></div>
      <div class="quote">“${escapeHtml(wordsText(s.w0, s.w1))}”</div>`;
    el.children[1].textContent = s.text;
    const a = $('a', el);
    a.href = 'https://www.pexels.com/search/' + encodeURIComponent(s.query || s.text) + '/';
    $('.x', el).onclick = () => patch({ suggestions: sugg.filter(x => x.id !== s.id) });
    $('.add', el).onclick = () => pickAsset(file => {
      const o = { id: Math.random().toString(36).slice(2, 10), type: 'media', file, w0: s.w0, w1: s.w1, layout: 'full' };
      patch({ overlays: [...state.p.overlays, o], suggestions: sugg.filter(x => x.id !== s.id) });
    });
    sl.appendChild(el);
  }
  if (!ovs.length && !sugg.length) list.innerHTML = '<p class="hint">Nenhuma inserção ainda.</p>';
}

function editOverlay(id, changes) {
  patch({ overlays: state.p.overlays.map(o => o.id === id ? { ...o, ...changes } : o) });
}

// ------------------------------------------------------------------ estilo
function renderStyle() {
  const s = state.c.settings;
  $$('.seg[data-setting]').forEach(seg => {
    $$('button', seg).forEach(b => b.classList.toggle('on', String(s[seg.dataset.setting]) === b.dataset.v));
  });
  $('#set-upper').checked = !!s.uppercase;
  $('#set-pause').value = s.max_pause; $('#v-pause').textContent = s.max_pause.toFixed(2) + 's';
  $('#set-pad').value = s.pad; $('#v-pad').textContent = s.pad.toFixed(2) + 's';
  $('#set-vol').value = s.music_volume; $('#v-vol').textContent = Math.round(s.music_volume * 100) + '%';
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
  const live = (id, key, label, f) => {
    const el = $(id);
    el.oninput = () => { $(label).textContent = f(+el.value); };
    el.onchange = () => patch({ settings: { [key]: +el.value } });
  };
  live('#set-pause', 'max_pause', '#v-pause', v => v.toFixed(2) + 's');
  live('#set-pad', 'pad', '#v-pad', v => v.toFixed(2) + 's');
  live('#set-vol', 'music_volume', '#v-vol', v => Math.round(v * 100) + '%');
}

// ------------------------------------------------------------------ player / preview
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

let raf = 0;
function loop() {
  raf = requestAnimationFrame(loop);
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
    if (next) { v.currentTime = next.start; t = next.start; k = segs.indexOf(next); }
    else { v.pause(); }
  } else if (!v.paused && k >= 0 && segs[k].end - t < 0.03) {
    // pula o corte um pouco antes, para não ouvir o começo da parte removida
    const n = segs[k + 1];
    if (n) { v.currentTime = n.start; t = n.start; k++; } else v.pause();
  }
  const out = toOutput(t);
  $('#t-cur').textContent = fmt(out);
  $('#play').textContent = v.paused ? '▶' : '❚❚';

  // zoom alternado
  const zoom = state.c.settings.transition === 'zoom' && k >= 0 && k % 2 === 1;
  v.style.transform = zoom ? 'scale(1.15)' : '';

  renderCaption(out);
  renderOverlayPreview(out, v.paused);
  highlightWord(t);
  drawPlayhead(t, force);
}

function renderCaption(out) {
  const s = state.c.settings, layer = $('#cap-layer');
  let html = '';
  if (s.captions !== 'none') {
    const c = state.c.captions.find(c => out >= c.a && out < c.b);
    if (c) {
      const cls = 'cap' + (s.captions === 'classic' ? ' classic' : '') + (s.uppercase ? ' upper' : '');
      const ws = c.words.map((w, j) => {
        const next = c.words[j + 1];
        const on = s.captions === 'pop' && out >= w.a && out < (next ? next.a : c.b);
        return on ? `<span class="hi">${escapeHtml(w.w)}</span>` : escapeHtml(w.w);
      });
      html = `<div class="${cls}">${ws.join(' ')}</div>`;
    }
  }
  if (layer._h !== html) { layer.innerHTML = html; layer._h = html; }
  const tl = $('#title-layer');
  const t = state.c.overlays.find(o => o.type === 'text' && out >= o.a && out < o.b);
  const th = t ? `<div class="ttl${s.uppercase ? ' upper' : ''}" style="${s.uppercase ? 'text-transform:uppercase' : ''}">${escapeHtml(t.text)}</div>` : '';
  if (tl._h !== th) { tl.innerHTML = th; tl._h = th; }
}

function renderOverlayPreview(out, paused) {
  const layer = $('#ov-layer');
  const active = new Set();
  for (const o of state.c.overlays) {
    if (o.type !== 'media' || out < o.a || out >= o.b) continue;
    active.add(o.id);
    let el = state.ovEls[o.id];
    const isVid = /\.(mp4|mov|m4v|webm|mkv)$/i.test(o.file);
    if (!el || el._file !== o.file) {
      el?.remove();
      el = document.createElement(isVid ? 'video' : 'img');
      el.src = assetUrl(o.file); el._file = o.file;
      if (isVid) { el.muted = true; el.loop = true; el.playsInline = true; }
      layer.appendChild(el);
      state.ovEls[o.id] = el;
    }
    el.className = 'ov' + (o.layout === 'pip' ? ' pip' : '');
    el.style.display = '';
    if (isVid) {
      const want = out - o.a;
      if (el.duration && Math.abs((el.currentTime % el.duration) - (want % el.duration)) > 0.35) el.currentTime = want % el.duration;
      if (paused && !el.paused) el.pause();
      if (!paused && el.paused) el.play().catch(() => {});
    }
  }
  for (const [id, el] of Object.entries(state.ovEls)) {
    if (!active.has(id)) { el.style.display = 'none'; if (el.pause) el.pause(); }
  }
}

function highlightWord(t) {
  const words = state.p.words;
  let i = -1;
  // busca binária pela palavra no tempo t
  let lo = 0, hi = words.length - 1;
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
    const segs = state.c.segments;
    const last = segs.at(-1);
    if (!last) return;
    if (v.currentTime >= last.end - 0.05) v.currentTime = segs[0].start;
    v.play();
  } else v.pause();
}

// ------------------------------------------------------------------ timeline
let tlBase = null;
function drawTimeline() {
  if (!state.c) return;
  const cv = $('#timeline');
  const dpr = devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext('2d');
  g.scale(dpr, dpr);
  const dur = state.p.source.duration;
  const x = t => t / dur * W;
  const css = getComputedStyle(document.documentElement);
  const col = n => css.getPropertyValue(n).trim();
  // base: área cortada
  g.fillStyle = '#2a161a';
  g.fillRect(0, 22, W, H - 30);
  // trechos mantidos
  g.fillStyle = '#123a37';
  for (const s of state.c.segments) g.fillRect(x(s.start), 22, Math.max(1, x(s.end) - x(s.start)), H - 30);
  // forma de onda
  const wave = state.wave;
  if (wave.length) {
    const mid = 22 + (H - 30) / 2, amp = (H - 34) / 2;
    for (let px = 0; px < W; px++) {
      const t = px / W * dur;
      const p = wave[Math.floor(px / W * wave.length)] || 0;
      g.fillStyle = segIndexAt(t) >= 0 ? col('--accent') : '#6b3640';
      const h = Math.max(1, p * amp);
      g.fillRect(px, mid - h, 1, h * 2);
    }
  }
  // inserções (faixa superior) — posicionadas no tempo original
  for (const o of state.c.overlays) {
    const a = state.p.words[o.w0]?.start ?? 0, b = state.p.words[o.w1]?.end ?? a;
    g.fillStyle = o.type === 'media' ? col('--ov') : '#c9a2ff';
    g.fillRect(x(a), 6, Math.max(3, x(b) - x(a)), 10);
  }
  tlBase = g.getImageData(0, 0, cv.width, cv.height);
  drawPlayhead($('#video').currentTime, true);
}
let lastHead = -1;
function drawPlayhead(t, force) {
  const cv = $('#timeline');
  if (!tlBase) return;
  const W = cv.clientWidth, dur = state.p.source.duration;
  const px = Math.round(t / dur * W);
  if (px === lastHead && !force) return;
  lastHead = px;
  const g = cv.getContext('2d');
  g.putImageData(tlBase, 0, 0);
  g.fillStyle = '#fff';
  g.fillRect(px - 1, 0, 2, cv.clientHeight);
}
function setupTimeline() {
  const cv = $('#timeline');
  const seek = e => {
    const r = cv.getBoundingClientRect();
    $('#video').currentTime = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * state.p.source.duration;
    tick(true);
  };
  cv.addEventListener('mousedown', e => {
    seek(e);
    const move = ev => seek(ev);
    const up = () => { removeEventListener('mousemove', move); removeEventListener('mouseup', up); };
    addEventListener('mousemove', move); addEventListener('mouseup', up);
  });
}

// ------------------------------------------------------------------ IA e exportação
async function runAI(btn, path, okMsg) {
  if (!state.status.ai) return toast('IA desligada: coloque sua ANTHROPIC_API_KEY no arquivo .env e reinicie o editor.', true, 7000);
  const label = btn.textContent;
  btn.disabled = true; btn.textContent = '⏳ Claude pensando…';
  try {
    const job = await api(`/api/projects/${state.p.id}/${path}`, { method: 'POST' });
    state.history.push({ deleted: state.p.deleted, overlays: state.p.overlays, settings: state.p.settings });
    const j = await waitJob(job.id);
    applyServer(await api(`/api/projects/${state.p.id}`));
    toast(okMsg(j.result));
  } catch (e) { toast(e.message, true, 8000); }
  finally { btn.disabled = false; btn.textContent = label; }
}

async function exportVideo() {
  $('#video').pause();
  const m = $('#modal');
  m.classList.remove('hidden');
  $('#modal-title').textContent = 'Exportando…';
  $('#exp-bar').style.width = '0%';
  $('#exp-msg').textContent = '';
  $('#exp-result').innerHTML = '';
  try {
    const job = await api(`/api/projects/${state.p.id}/render`, { method: 'POST' });
    const j = await waitJob(job.id, j => {
      $('#exp-bar').style.width = (j.progress * 100) + '%';
      $('#exp-msg').textContent = `${Math.round(j.progress * 100)}%`;
    });
    $('#modal-title').textContent = 'Pronto! 🎉';
    $('#exp-msg').textContent = j.result.file;
    $('#exp-result').innerHTML = `<video controls src="${j.result.url}"></video>
      <a class="primary" href="${j.result.url}" download="${escapeAttr(j.result.file)}">Baixar MP4</a>`;
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
    state.history.push({ deleted: state.p.deleted, overlays: state.p.overlays, settings: state.p.settings });
    applyServer(await api(`/api/projects/${state.p.id}/autocut`, { method: 'POST', json: {} }));
    toast(`Hesitações cortadas · pausas acima de ${state.c.settings.max_pause}s removidas`);
  };
  $('#btn-restore-all').onclick = () => patch({ deleted: [] });
  $('#btn-ai-clean').onclick = e => runAI(e.currentTarget, 'ai/clean', r => `IA removeu ${r.cuts.length} trechos (passe o mouse nas palavras roxas para ver o motivo)`);
  $('#btn-ai-suggest').onclick = e => runAI(e.currentTarget, 'ai/suggest', r => `${r.items.length} sugestões criadas`);

  document.addEventListener('keydown', e => {
    if ($('#editor').classList.contains('hidden')) return;
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if (typing) return;
    if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
    else if ((e.key === 'Delete' || e.key === 'Backspace') && state.sel) { e.preventDefault(); setDeleted(state.sel, true); }
    else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    else if (e.key === 'ArrowLeft') { $('#video').currentTime -= 2; }
    else if (e.key === 'ArrowRight') { $('#video').currentTime += 2; }
  });
  new ResizeObserver(() => { layoutFrame(); drawTimeline(); }).observe($('.stage-col'));
  loop();
}

setup();
const initial = location.hash.slice(1);
if (initial) openProject(initial).catch(() => loadHome()); else loadHome();
