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
  zoom: ['⊕', 'Zoom'], flash: ['✺', 'Flash'], transition: ['☀', 'Transição'], behind: ['◐', 'Texto atrás'], perspective: ['◇', '3D'],
  emphasis: ['★', 'Destaque'], greenscreen: ['🟩', 'Tela verde'],
};
const VISUAL = new Set(['text', 'media', 'motion', 'behind', 'perspective', 'emphasis', 'greenscreen']);
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
  // troca o elemento: os cliques de diálogos anteriores não se acumulam
  const old = $('#dialog-body'), body = old.cloneNode(false);
  old.replaceWith(body);
  body.innerHTML = html;
  $('#dialog').classList.remove('hidden');
  return body;
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

// ------------------------------------------------------------------ envio (vídeo principal + arquivos de apoio)
const stage = { main: [], extra: [] };
const natKey = n => n.toLowerCase().split(/(\d+)/).map((t, i) => i % 2 ? t.padStart(12, '0') : t).join('');
const byName = (a, b) => natKey(a.name) < natKey(b.name) ? -1 : natKey(a.name) > natKey(b.name) ? 1 : 0;
const isVid = f => f.type.startsWith('video/') || /\.(mp4|mov|m4v|webm|mkv|avi)$/i.test(f.name);
const isImg = f => f.type.startsWith('image/') || /\.(png|jpe?g|webp|gif|heic)$/i.test(f.name);
const fmtSize = n => n > 1e9 ? (n / 1e9).toFixed(1) + ' GB' : (n / 1e6).toFixed(0) + ' MB';

function stageFiles(files, col) {
  for (const f of files) {
    if (!isVid(f) && !isImg(f)) { toast(`${f.name}: formato não suportado`, true); continue; }
    if ([...stage.main, ...stage.extra].some(x => x.name === f.name && x.size === f.size)) continue;
    // vídeos vão para a gravação principal; imagens sempre são apoio
    (col === 'extra' || !isVid(f) ? stage.extra : stage.main).push(f);
  }
  renderStage();
}

function renderStage() {
  stage.main.sort(byName);
  stage.extra.sort(byName);
  const any = stage.main.length + stage.extra.length > 0;
  $('#upstage').classList.toggle('hidden', !any);
  $('#drop').classList.toggle('compact', any);
  $('.drop-title', $('#drop')).textContent = any ? '＋ Arraste mais arquivos aqui' : 'Arraste seu vídeo cru aqui';
  const row = (f, col, k) => {
    const url = f._url || (f._url = URL.createObjectURL(f));
    const th = isVid(f) ? `<video src="${url}#t=0.5" muted preload="metadata"></video>` : `<img src="${url}">`;
    const move = isVid(f) ? `<button class="act mv" title="${col === 'main' ? 'Usar como vídeo de apoio (B-roll)' : 'Usar como parte da gravação principal'}">${col === 'main' ? '→ apoio' : '← principal'}</button>` : '';
    return `<div class="up-item" data-col="${col}" data-k="${k}">${th}
      <div class="up-name">${col === 'main' && stage.main.length > 1 ? `<b>${k + 1}.</b> ` : ''}${esc(f.name)}<div class="muted">${fmtSize(f.size)}</div></div>
      ${move}<button class="x" title="Tirar">✕</button></div>`;
  };
  $('#up-main').innerHTML = stage.main.map((f, k) => row(f, 'main', k)).join('') ||
    '<div class="hint">Falta o vídeo principal: arraste sua gravação.</div>';
  $('#up-extra').innerHTML = stage.extra.map((f, k) => row(f, 'extra', k)).join('') ||
    '<div class="hint">Opcional. Arraste aqui prints e vídeos que você quer mostrar.</div>';
  const n = stage.main.length;
  $('#up-info').textContent = n > 1 ? `${n} gravações serão juntadas nessa ordem` : '';
  $('#up-go').disabled = !n;
}

function setupDrop() {
  const drop = $('#drop');
  const over = (el, on) => el.classList.toggle('over', on);
  for (const el of [drop, ...$$('.up-col')]) {
    ['dragenter', 'dragover'].forEach(ev => el.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); over(el, true); }));
    ['dragleave', 'drop'].forEach(ev => el.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); over(el, false); }));
    el.addEventListener('drop', e => stageFiles([...e.dataTransfer.files], el.dataset.col === 'extra' ? 'extra' : null));
  }
  $('#file').onchange = e => { stageFiles([...e.target.files]); e.target.value = ''; };
  $('#up-add').onclick = () => $('#file').click();
  $('#up-clear').onclick = () => { stage.main = []; stage.extra = []; renderStage(); };
  $('#upstage').addEventListener('click', e => {
    const it = e.target.closest('.up-item'); if (!it) return;
    const from = stage[it.dataset.col], k = +it.dataset.k;
    if (e.target.closest('.x')) from.splice(k, 1);
    else if (e.target.closest('.mv')) (it.dataset.col === 'main' ? stage.extra : stage.main).push(from.splice(k, 1)[0]);
    else return;
    renderStage();
  });
  $('#up-go').onclick = () => upload(stage.main, stage.extra);
}

function upload(mains, extras = []) {
  // nome no formato das exportações do editor ("...-20261003-235315.mp4"): provavelmente já editado
  const exported = mains.filter(f => /-\d{8}-\d{6}\.mp4$/i.test(f.name));
  if (exported.length &&
      !confirm(`"${exported[0].name}" parece ser um vídeo EXPORTADO por este editor (já cortado e com legendas gravadas na imagem).\n\nPara editar, use o vídeo cru original. Continuar mesmo assim?`)) {
    return;
  }
  show('processing');
  $('#proc-title').textContent = mains.length > 1 ? `Enviando ${mains.length} gravações…` : 'Enviando vídeo…';
  $('#proc-msg').textContent = mains.map(f => f.name).join(', ') + (extras.length ? ` + ${extras.length} de apoio` : '');
  const fd = new FormData();
  mains.forEach(f => fd.append('file', f));
  extras.forEach(f => fd.append('extras', f));
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
    stage.main = []; stage.extra = []; renderStage();
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

// ------------------------------------------------------------------ referências (links salvos)
const REF_KIND = { perfil: '👤 Perfil', reel: '🎬 Reel', post: '🖼 Post', story: '⏱ Story', video: '🎬 Vídeo', link: '🔗 Link' };
const refsState = { items: [], kind: 'all', q: '' };

async function loadRefs() {
  show('refs');
  history.replaceState(null, '', '#refs');
  refsState.items = await api('/api/refs');
  renderRefs();
  refreshSync();
}

function renderRefs() {
  const all = refsState.items;
  $('#ref-count').textContent = `${all.length} ${all.length === 1 ? 'referência' : 'referências'}`;
  const counts = {};
  all.forEach(r => counts[r.kind] = (counts[r.kind] || 0) + 1);
  $('#ref-kinds').innerHTML = `<button class="rf-chip ${refsState.kind === 'all' ? 'on' : ''}" data-k="all">Tudo <b>${all.length}</b></button>` +
    Object.entries(counts).map(([k, n]) => `<button class="rf-chip ${refsState.kind === k ? 'on' : ''}" data-k="${k}">${REF_KIND[k] || k} <b>${n}</b></button>`).join('');
  const q = refsState.q.toLowerCase().replace(/^[@#]/, '');
  const list = all.filter(r => (refsState.kind === 'all' || r.kind === refsState.kind) &&
    (!q || [r.url, r.handle, r.note, r.caption, ...(r.tags || [])].join(' ').toLowerCase().includes(q)))
    .sort((a, b) => b.added.localeCompare(a.added));
  const box = $('#ref-list');
  box.innerHTML = list.length ? '' : `<p class="rf-empty">${all.length ? 'Nada com esse filtro.' : 'Nenhuma referência ainda. Cole um link acima.'}</p>`;
  const SITE = { instagram: 'Instagram', tiktok: 'TikTok', youtube: 'YouTube' };
  const profile = r => r.handle ? (r.site === 'instagram' ? `https://instagram.com/${r.handle}/` :
    r.site === 'tiktok' ? `https://www.tiktok.com/@${r.handle}` : r.site === 'youtube' ? `https://www.youtube.com/@${r.handle}` : r.url) : r.url;
  for (const r of list) {
    const el = document.createElement('article');
    el.className = 'rf-item';
    const date = `${r.added.slice(8, 10)}/${r.added.slice(5, 7)}/${r.added.slice(0, 4)}`;
    const initial = (r.handle || r.site || '?')[0].toUpperCase();
    el.innerHTML = `
      <a class="rf-thumb" href="${esc(r.url)}" target="_blank" rel="noopener">
        ${r.thumb ? `<img src="/api/refs/thumb/${esc(r.thumb.split('/').pop())}" loading="lazy" alt="">` : `<span class="rf-ph">${esc(initial)}</span>`}
        <span class="rf-kind">${REF_KIND[r.kind] || r.kind}</span>
      </a>
      <div class="rf-body">
        <div class="rf-who">
          <span class="rf-avatar">${esc(initial)}</span>
          <div class="rf-who-txt">
            ${r.handle ? `<a class="rf-handle" href="${esc(profile(r))}" target="_blank" rel="noopener">@${esc(r.handle)}</a>`
              : `<button class="rf-handle unknown set-handle">@ quem é? <small>clique para preencher</small></button>`}
            <span class="rf-meta">${esc(SITE[r.site] || r.site)} · salvo em ${date}</span>
          </div>
        </div>
        ${r.caption ? `<p class="rf-caption">${esc(r.caption)}</p>` : ''}
        ${(r.learned || []).length ? `<div class="rf-learned"><b>✓ Aprendido e aplicado no editor</b><ul>${r.learned.map(l => `<li>${esc(l)}</li>`).join('')}</ul></div>` : ''}
        <label class="rf-field"><span>Nota</span><input class="rf-note" placeholder="O que você gostou nessa referência?" value="${esc(r.note || '')}"></label>
        <label class="rf-field"><span>Etiquetas</span><input class="rf-tags" placeholder="gancho, cor, legenda" value="${esc((r.tags || []).join(', '))}"></label>
        <div class="rf-actions">
          <a class="rf-link" href="${esc(r.url)}" target="_blank" rel="noopener">Abrir ↗</a>
          <button class="rf-link copy">Copiar link</button>
          ${r.handle ? '<button class="rf-link set-handle">Editar @</button>' : ''}
          <div class="spacer"></div>
          <button class="rf-link danger del">Apagar</button>
        </div>
      </div>`;
    const save = changes => api(`/api/refs/${r.id}`, { method: 'PATCH', json: changes })
      .then(nr => { Object.assign(r, nr); toast('Salvo'); refreshSync(); return nr; }).catch(e => toast(e.message, true));
    $('.rf-note', el).onchange = e => save({ note: e.target.value });
    $('.rf-tags', el).onchange = e => save({ tags: e.target.value });
    $('.copy', el).onclick = () => navigator.clipboard.writeText(r.url).then(() => toast('Link copiado'));
    $$('.set-handle', el).forEach(b => b.onclick = async () => {
      const h = prompt('@ da pessoa (sem o @):', r.handle || '');
      if (h === null) return;
      await save({ handle: h });
      renderRefs();
    });
    $('.del', el).onclick = async () => {
      if (!confirm(`Apagar a referência${r.handle ? ' de @' + r.handle : ''}?`)) return;
      await api(`/api/refs/${r.id}`, { method: 'DELETE' });
      refsState.items = refsState.items.filter(x => x.id !== r.id);
      renderRefs(); refreshSync();
    };
    box.appendChild(el);
  }
}

// selo "salvo no GitHub": acompanha o envio que o servidor faz sozinho a cada alteração
async function refreshSync(tries = 12) {
  let s;
  try { s = await api('/api/refs/sync'); } catch { return; }
  const b = $('#ref-sync');
  const hhmm = s.at ? s.at.slice(11, 16) : '';
  b.className = 'rf-sync ' + s.state;
  b.textContent = s.state === 'ok' ? `☁ Salvo no GitHub${hhmm ? ' às ' + hhmm : ''}` :
    s.state === 'sending' ? '⏳ Enviando para o GitHub…' :
    s.state === 'error' ? '⚠ Não foi para o GitHub — tentar de novo' : '☁ Salvo no seu Mac e no GitHub';
  b.title = s.state === 'error' ? s.msg : 'Os links ficam em referencias/links.json e vão sozinhos para o GitHub';
  if (s.state === 'sending' && tries > 0) setTimeout(() => refreshSync(tries - 1), 1500);
}

function setupRefs() {
  $('#go-refs').onclick = loadRefs;
  $('#ref-add').onclick = async () => {
    const text = $('#ref-text').value.trim();
    if (!text) return toast('Cole pelo menos um link', true);
    try {
      $('#ref-add').disabled = true; $('#ref-add').textContent = 'Buscando @…';
      const r = await api('/api/refs', { method: 'POST', json: { text, note: $('#ref-note').value, tags: $('#ref-tags').value } })
        .finally(() => { $('#ref-add').disabled = false; $('#ref-add').textContent = 'Salvar'; });
      toast(`${r.added.length} salva(s)` + (r.updated.length ? ` · ${r.updated.length} já existia(m) (atualizada)` : ''));
      setTimeout(refreshSync, 300);
      $('#ref-text').value = ''; $('#ref-note').value = ''; $('#ref-tags').value = '';
      refsState.items = await api('/api/refs');
      renderRefs();
    } catch (e) { toast(e.message, true); }
  };
  $('#ref-text').addEventListener('keydown', e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) $('#ref-add').click(); });
  $('#ref-search').oninput = e => { refsState.q = e.target.value.trim(); renderRefs(); };
  $('#ref-sync').onclick = () => api('/api/refs/sync', { method: 'POST' }).then(() => setTimeout(refreshSync, 300));
  $('#ref-kinds').onclick = e => { const c = e.target.closest('[data-k]'); if (c) { refsState.kind = c.dataset.k; renderRefs(); } };
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
  seqKnown = new Set();
  for (const id in musicEls) { musicEls[id].pause(); delete musicEls[id]; }
  state.musicSel = null;
  state.ovEls = {}; $('#ov-layer').innerHTML = '';
  state.motionEls = {}; $('#motion-layer').innerHTML = '';
  show('editor');
  $('#pname').value = p.name;
  $('#proj-formato').value = p.formato || '';
  const v = $('#video');
  v.src = mediaUrl(p.preview || p.source.file) + (p.preview === 'preview_bg.mp4' ? `?s=${p.settings.bg_scene}&t=${Math.round(p.updated || 0)}` : '');
  v.currentTime = state.c.segments[0]?.start || 0;
  if (!p.preview && p.source.hdr !== null) ensureProxy(p);
  api(`/api/projects/${pid}/waveform`).then(w => { state.wave = w; drawTimeline(); });
  tl.zoom = 1; tl.v0 = 0; tl.sel = null; tl.seg = null; tl.trim = null; $('#tl-zoom').value = 1;
  state.showCuts = false;                       // sempre abre na prévia "lisa", já cortada
  $('#show-cuts').classList.remove('on'); $('#show-cuts').textContent = '👁 Ver cortes';
  state.gradeCss = '';
  renderAll();
  updateGradePreview();
  loadMyFiles(true);
  showBusy(false);
  const scene = p.settings.bg_scene || 'none';
  if (p.bg_job) followBgJob(p.bg_job, scene);
  else if (p.cutout_job) followJob(p.cutout_job, 'Recortando você do fundo…');
  else if (!p.cutout && p.overlays.some(o => o.type === 'greenscreen')) ensureCutout();
  else if (scene !== 'none' && p.preview !== 'preview_bg.mp4') setScene(scene);
}

// ------------------------------------------------------------------ seus arquivos (prints e vídeos de apoio)
async function loadMyFiles(hint) {
  const box = $('#my-files');
  let files = [];
  try { files = await api(`/api/projects/${state.p.id}/assets`); } catch {}
  files = files.filter(a => !a.credit && (a.kind === 'image' || a.kind === 'video'))
    .sort((a, b) => natKey(a.file.replace(/^[a-f0-9]{6}_/, '')) < natKey(b.file.replace(/^[a-f0-9]{6}_/, '')) ? -1 : 1);
  box.innerHTML = files.length ? files.map(a => {
    const url = assetUrl(a.file), name = a.file.replace(/^[a-f0-9]{6}_/, '');
    const used = state.p.overlays.some(o => o.file === a.file);
    return `<button class="my-file${used ? ' used' : ''}" data-file="${esc(a.file)}" title="Inserir “${esc(name)}” onde a agulha está">
      ${a.kind === 'video' ? `<video src="${url}#t=0.5" muted preload="metadata"></video>` : `<img src="${url}" loading="lazy">`}
      <span>${esc(name)}</span></button>`;
  }).join('') : '<p class="hint">Nenhum arquivo. Use “＋ adicionar” para mandar prints, fotos ou vídeos.</p>';
  if (hint && files.length && !state.p.overlays.some(o => o.type === 'media' && o.file))
    toast(`📎 ${files.length} arquivo(s) de apoio na aba Edição: posicione a agulha e clique para inserir.`, false, 7000);
}

// cria "você no canto" na agulha (~6 s): com 1 print usa ele; com vários, pergunta qual
async function addCornerAtHead() {
  const W = state.p.words, w0 = wordAtHead();
  let w1 = w0;
  while (w1 + 1 < W.length && W[w1 + 1].end - W[w0].start <= 6) w1++;
  let files = [];
  try { files = (await api(`/api/projects/${state.p.id}/assets`)).filter(a => a.kind === 'image' && !a.credit); } catch {}
  if (files.length === 1) return addGreenscreen(files[0].file, [w0, w1]);
  return pickGreenscreenFile([w0, w1]);
}

// troca o print de um trecho de tela verde (entre os seus arquivos)
async function chooseGsImage(o) {
  let files = [];
  try { files = (await api(`/api/projects/${state.p.id}/assets`)).filter(a => a.kind === 'image' && !a.credit); } catch {}
  const body = dialog(`<h3>🟩 Qual print fica de fundo neste trecho?</h3>
    <div class="my-files-grid">${files.map(a => `<button class="my-file${a.file === o.file ? ' on' : ''}" data-f="${esc(a.file)}"><img src="${assetUrl(a.file)}"><span>${esc(a.file.replace(/^[a-f0-9]{6}_/, ''))}</span></button>`).join('')}
    <button class="my-file" data-up="1"><span class="bg-ph">＋</span><span>Enviar outro</span></button></div>`);
  body.onclick = e => {
    const b = e.target.closest('[data-f]');
    if (b) { $('#dialog').classList.add('hidden'); editOverlay(o.id, { file: b.dataset.f }); toast('Print do trecho trocado'); return; }
    if (e.target.closest('[data-up]')) pickAsset(file => { $('#dialog').classList.add('hidden'); loadMyFiles(); editOverlay(o.id, { file }); }, 'image/*');
  };
}

async function pickGreenscreenFile(range) {
  let files = [];
  try { files = (await api(`/api/projects/${state.p.id}/assets`)).filter(a => a.kind === 'image' && !a.credit); } catch {}
  const body = dialog(`<h3>🟩 Tela verde neste trecho</h3><p class="hint">Escolha o print que fica de fundo (você vai para o canto).</p>
    <div class="my-files-grid">${files.map(a => `<button class="my-file" data-f="${esc(a.file)}"><img src="${assetUrl(a.file)}"><span>${esc(a.file.replace(/^[a-f0-9]{6}_/, ''))}</span></button>`).join('')}
    <button class="my-file" data-up="1"><span class="bg-ph">＋</span><span>Enviar print</span></button></div>`);
  body.onclick = e => {
    const b = e.target.closest('[data-f]');
    if (b) { $('#dialog').classList.add('hidden'); return addGreenscreen(b.dataset.f, range); }
    if (e.target.closest('[data-up]')) pickAsset(file => { $('#dialog').classList.add('hidden'); loadMyFiles(); addGreenscreen(file, range); }, 'image/*');
  };
}

async function addGreenscreen(file, range) {
  const body = { file };
  const r = range || state.sel;
  if (r) { body.w0 = r[0]; body.w1 = r[1]; }
  toast(r ? 'Aplicando a tela verde no trecho selecionado…' : 'Procurando o trecho em que você lê esse print…');
  try {
    let res = await api(`/api/projects/${state.p.id}/greenscreen`, { method: 'POST', json: body });
    if (!res.found && !r && !res.overlay) {
      // não achou a leitura: usa a agulha e ~8 s (dá para esticar no cartão)
      const W = state.p.words, w0 = wordAtHead();
      let w1 = w0;
      while (w1 + 1 < W.length && W[w1 + 1].end - W[w0].start <= 8) w1++;
      res = await api(`/api/projects/${state.p.id}/greenscreen`, { method: 'POST', json: { file, w0, w1 } });
      toast('Não achei você lendo esse print — coloquei a tela verde na agulha (~8 s). Ajuste a duração no cartão.', false, 7000);
    } else if (res.found) {
      toast('🟩 Achei você lendo o print — tela verde aplicada nesse trecho', false, 6000);
    }
    state.history.push(snapshot());
    applyServer(res.project);
    document.querySelector('.tabs [data-tab="edicao"]').click();
    state.focus = res.overlay?.id;
    ensureCutout();
  } catch (e) { toast(e.message, true); }
}

function wordAtHead() {
  const t = $('#video').currentTime, W = state.p.words, del = new Set(state.p.deleted);
  const w0 = W.findIndex(w => w.end > t && !del.has(w.i));
  return w0 < 0 ? W.length - 1 : w0;
}

function insertFileAtHead(file) {
  const W = state.p.words, w0 = wordAtHead();
  // dura ~3 s de fala (dá para esticar/encolher no cartão)
  let w1 = w0;
  while (w1 + 1 < W.length && W[w1 + 1].end - W[w0].start <= 3) w1++;
  // imagem brotando na tela leva um clique (a única hora em que esse tipo de som entra)
  const n = state.p.overlays.filter(o => o.type === 'sfx' && /^click/.test(o.sfx)).length;
  const media = { id: uid(), type: 'media', file, layout: isVideo(file) ? 'full' : 'card', w0, w1 };
  const click = { id: uid(), type: 'sfx', sfx: ['click_classico', 'click_mouse'][n % 2], w0, w1: w0, reason: 'imagem entrando' };
  patch({ overlays: [...state.p.overlays, media, click] });
  document.querySelector('.tabs [data-tab="edicao"]').click();
  state.focus = media.id;
  toast('Arquivo inserido (com clique)');
  setTimeout(() => loadMyFiles(), 300);
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

function applyServer(p) {
  const before = state.c?.cuts || [];
  state.p = p; state.c = p.computed;
  pulseChanges(before, state.c.cuts);
  renderAll();
}

// intervalos que estavam em A e não estão em B
function minusIntervals(A, B) {
  const out = [];
  for (const a of A) {
    let parts = [[a.start, a.end]];
    for (const b of B) parts = parts.flatMap(([x, y]) => (b.end <= x || b.start >= y) ? [[x, y]] :
      [[x, Math.min(y, b.start)], [Math.max(x, b.end), y]].filter(([p, q]) => q - p > 0.02));
    out.push(...parts);
  }
  return out;
}
// ao cortar (ou restaurar), o trecho pisca na timeline: dá para ver o que mudou
function pulseChanges(before, after) {
  if (!before.length) return;
  const cut = minusIntervals(before, after), kept = minusIntervals(after, before);
  if (!cut.length && !kept.length) return;
  tl.pulse = { cut, kept, t0: performance.now() };
  const step = () => { drawTimeline(); if (tl.pulse && performance.now() - tl.pulse.t0 < 700) requestAnimationFrame(step); else { tl.pulse = null; drawTimeline(); } };
  requestAnimationFrame(step);
}

function snapshot() { return { deleted: state.p.deleted, overlays: state.p.overlays, settings: state.p.settings, manual: state.p.manual || [], order: state.p.order || [], splits: state.p.splits || [], music: state.p.music || [] }; }
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
  renderScenes();
  renderLibrary();
  renderSeqbar();
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
  const outside = e => { if (e.target !== inp) finish(true); };
  setTimeout(() => document.addEventListener('mousedown', outside, true), 0);
  const finish = save => {
    if (done) return; done = true;
    document.removeEventListener('mousedown', outside, true);
    const value = inp.value;
    // o campo SEMPRE fecha (mesmo sem mudança ou se der erro); a transcrição volta ao normal na hora
    inp.remove(); spans.forEach(sp => sp.hidden = !sp.textContent);
    if (save) saveWords(i0, i1, value);
  };
  inp.addEventListener('keydown', e => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    if (e.key === 'Escape') { e.preventDefault(); finish(false); }
  });
  inp.addEventListener('blur', () => finish(true));
}

function setupCaptionEditing() {
  // Vídeo pausado: clique numa PALAVRA da legenda/destaque e corrija ali mesmo. Só aquela palavra
  // vira editável — fonte, tamanho, cor e linhas ficam exatamente como estão; nada dá play.
  const layer = $('#cap-layer');
  const stop = e => { if (e.target.closest('[data-i]') && $('#video').paused) e.stopPropagation(); };
  layer.addEventListener('mousedown', stop);
  layer.addEventListener('dblclick', stop);
  layer.addEventListener('click', e => {
    const el = e.target.closest('[data-i]');
    if (!el || !$('#video').paused) return;
    e.stopPropagation(); e.preventDefault();
    if (el.isContentEditable) return;
    const i = +el.dataset.i;
    const original = state.p.words[i].w;
    state.editingCap = true;
    el.textContent = original;
    el.contentEditable = 'true';
    el.spellcheck = false;
    el.focus();
    const sel = window.getSelection(); sel.selectAllChildren(el);
    let done = false;
    const finish = save => {
      if (done) return; done = true;
      el.contentEditable = 'false';
      state.editingCap = false;
      layer._h = null;
      const txt = el.textContent.replace(/\s+/g, ' ').trim();
      if (save && txt && txt !== original) saveWords(i, i, txt);
      else { el.textContent = original; tick(true); }
    };
    el.addEventListener('keydown', ev => {
      ev.stopPropagation();
      if (ev.key === 'Enter') { ev.preventDefault(); el.blur(); }
      if (ev.key === 'Escape') { ev.preventDefault(); finish(false); el.blur(); }
    });
    el.addEventListener('blur', () => finish(true), { once: true });
  });
}

function setupTranscript() {
  const box = $('#transcript');
  box.addEventListener('click', e => {
    const w = e.target.closest('[data-i]');
    if (!w || !window.getSelection().isCollapsed) return;
    if (state.editMode) { editWordsInline([+w.dataset.i, +w.dataset.i]); return; }
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
    if (act === 'greenscreen') return pickGreenscreenFile(r);
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
    // cartão recolhido: uma linha (ícone, nome, tempo, trecho); abre ao clicar
    const open = state.focus === o.id || state.openCards?.has(o.id);
    el.className = 'card compact' + (open ? ' open focus' : '');
    const [ic, name] = TYPE_INFO[o.type] || ['?', o.type];
    el.innerHTML = `<div class="row card-head"><span class="icon">${ic}</span><b>${name}</b><span class="muted">${fmt(o.a)}</span>
      <span class="card-sub">${esc(wordsText(o.w0, o.w1))}</span><div class="spacer"></div>
      <button class="act go" title="Ir para esse ponto">▶</button><button class="x" title="Remover">✕</button></div>
      <div class="fields"></div>
      <div class="quote">“${esc(wordsText(o.w0, o.w1))}”${o.reason ? ` · <i>${esc(o.reason)}</i>` : ''}</div>`;
    $('.card-head', el).addEventListener('click', ev => {
      selectItem('overlay', o.id);
      if (ev.target.closest('button')) return;
      state.openCards = state.openCards || new Set();
      if (el.classList.toggle('open')) state.openCards.add(o.id); else { state.openCards.delete(o.id); if (state.focus === o.id) state.focus = null; }
    });
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
        <label>Modelo <select class="var"><option value="">Automático</option><option value="bigend">Justificado (palavra-chave enorme)</option><option value="stack">Bloco à direita</option><option value="atras">✦ Especial: palavra gigante atrás da cabeça</option></select></label>`;
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
          <select class="lay"><option value="viral">Modelo viral (quadro no fundo escuro)</option><option value="full">Tela cheia</option><option value="card">Card (fundo desfocado)</option><option value="card3d">Card 3D</option><option value="pip">Janela</option></select>
          <button class="act swap">trocar</button></div>
          <div class="row"><span class="muted">Duração</span><button class="act shorter" title="Termina uma palavra antes">−</button>
          <span class="dur">${(state.p.words[o.w1].end - state.p.words[o.w0].start).toFixed(1)} s</span>
          <button class="act longer" title="Termina uma palavra depois">＋</button></div>`;
        const s = $('.lay', fields); s.value = o.layout || 'full'; s.onchange = () => editOverlay(o.id, { layout: s.value });
        $('.shorter', fields).onclick = () => o.w1 > o.w0 && editOverlay(o.id, { w1: o.w1 - 1 });
        $('.longer', fields).onclick = () => o.w1 + 1 < state.p.words.length && editOverlay(o.id, { w1: o.w1 + 1 });
      } else {
        fields.innerHTML = `<div class="pending">⏳ Pendente: ${esc(o.desc || o.query || '')}</div>
          <div class="row"><button class="act swap">🔎 buscar (${esc(o.source || 'commons')})</button><button class="act up">＋ meu arquivo</button></div>`;
        $('.up', fields).onclick = () => pickAsset(file => editOverlay(o.id, { file }));
      }
      $('.swap', fields).onclick = () => openSearch({ overlay: o.id, query: o.query || wordsText(o.w0, o.w1), source: o.source || 'commons' });
    } else if (o.type === 'greenscreen') {
      fields.innerHTML = `<div class="row"><img class="thumb" src="${assetUrl(o.file)}">
          <select class="corner"><option value="bl">Eu no canto esquerdo</option><option value="br">Eu no canto direito</option></select>
          <select class="size"><option value="0.42">Pequeno</option><option value="0.52">Médio</option><option value="0.62">Grande</option></select></div>
        <div class="row"><span class="muted">Duração</span><button class="act shorter">−</button>
          <span class="dur">${(state.p.words[o.w1].end - state.p.words[o.w0].start).toFixed(1)} s</span><button class="act longer">＋</button>
          <span class="muted">· na exportação você sai recortado</span></div>`;
      const c = $('.corner', fields); c.value = o.corner || 'bl'; c.onchange = () => editOverlay(o.id, { corner: c.value });
      const th = $('.thumb', fields); th.title = 'Clique para trocar o print deste trecho'; th.style.cursor = 'pointer';
      th.onclick = () => chooseGsImage(o);
      const z = $('.size', fields); z.value = String(o.size || 0.52); z.onchange = () => editOverlay(o.id, { size: +z.value });
      $('.shorter', fields).onclick = () => o.w1 > o.w0 && editOverlay(o.id, { w1: o.w1 - 1 });
      $('.longer', fields).onclick = () => o.w1 + 1 < state.p.words.length && editOverlay(o.id, { w1: o.w1 + 1 });
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
    $$('button', seg).forEach(b => b.classList.toggle('on', seg.dataset.setting === 'speed'
      ? Math.abs((+s.speed || 1) - +b.dataset.v) < 0.001 : String(s[seg.dataset.setting]) === b.dataset.v));
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
    const key = seg.dataset.setting, val = key === 'speed' ? +b.dataset.v : b.dataset.v;
    patch({ settings: { [key]: val } });
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
  vivido: 'saturate(1.3) contrast(1.06)', kronos: 'sepia(.14) saturate(.86) contrast(.93) brightness(1.03)',
};
function aspect() {
  const f = state.c.settings.format, s = state.p.source;
  return { '9:16': 9 / 16, '1:1': 1, '16:9': 16 / 9 }[f] || (s.width / s.height) || 16 / 9;
}
function layoutFrame() {
  if (!state.c) return;
  const stage = $('.stage'), fr = $('#frame');
  // zera antes de medir: senão o próprio vídeo (grande, ex.: saindo da tela cheia) infla a área
  fr.style.width = '0px'; fr.style.height = '0px';
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
  const segs = state.c.segments;
  for (const s of segs) if (t >= s.start && t <= s.end) return s.out + (t - s.start);
  let nxt = null;
  for (const s of segs) if (s.start > t && (!nxt || s.start < nxt.start)) nxt = s;
  if (nxt) return nxt.out;
  const l = segs.reduce((a, b) => (!a || b.end > a.end ? b : a), null);
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
  const seeAll = state.showCuts;
  if (seeAll) {
    if (!v.paused && t >= state.p.source.duration - 0.05) v.pause();
  } else if (!v.paused && k < 0) {
    const next = segs.find(s => s.start > t);
    if (next) { v.currentTime = next.start; t = next.start; k = segs.indexOf(next); } else v.pause();
  } else if (!v.paused && k >= 0 && segs[k].end - t < 0.03) {
    const n = segs[k + 1];
    if (!n) v.pause();
    else if (Math.abs(n.start - segs[k].end) > 0.01) { v.currentTime = n.start; t = n.start; k++; }
  }
  const out = toOutput(t);
  const sp = +state.c.settings.speed || 1;
  syncMusic(out, !v.paused && !seeAll);
  if (Math.abs(v.playbackRate - sp) > 0.001) { v.playbackRate = sp; v.preservesPitch = true; }
  const inCut = seeAll && k < 0;
  $('#frame').classList.toggle('in-cut', inCut);
  $('#t-cur').textContent = seeAll ? `${fmt(t)} no original` : fmt(out / sp);
  $('#t-tot').textContent = fmt(state.c.duration / sp);
  $('#play').textContent = v.paused ? '▶' : '❚❚';
  $('#frame').classList.toggle('paused', v.paused);
  // enquadramento do trecho × zoom suave contínuo (mesma conta do render)
  let zs = 1;
  if (k >= 0) {
    const p = segs[k], pr = Math.max(0, Math.min(1, (t - p.start) / Math.max(0.01, p.end - p.start)));
    zs = (p.zoom || 1) * ((p.kb0 ?? 1) + ((p.kb1 ?? 1) - (p.kb0 ?? 1)) * pr);
  }
  v.style.transform = zs > 1.0005 ? `scale(${zs.toFixed(4)})` : '';
  const gs = state.c.overlays.find(o => o.type === 'greenscreen' && out >= o.a && out < o.b);
  const gl = $('#gs-layer'), wrap = $('#vid-wrap'), cut = $('#cut-video');
  // o recorte começa a tocar ESCONDIDO 1,5 s antes do trecho: quando aparece, já está rodando (sem travar)
  const soon = state.p.cutout && state.c.overlays.find(o => o.type === 'greenscreen' && out >= o.a - 1.5 && out < o.b);
  if (soon) {
    const url = mediaUrl(state.p.cutout);
    if (cut.dataset.src !== url) { cut.src = url; cut.dataset.src = url; cut.preload = 'auto'; }
    if (v.paused) {
      if (!cut.paused) cut.pause();
      if (!cut._starting && Math.abs(cut.currentTime - t) > 0.04) cut.currentTime = t;
    } else if (cut.paused) {
      // dá a partida UMA vez e deixa arrancar (reposicionar a cada quadro era o "primeiro segundo travado")
      if (!cut._starting) {
        cut._starting = true;
        cut.playbackRate = v.playbackRate;
        cut.currentTime = t + 0.05;
        cut.play().catch(() => {}).finally(() => { cut._starting = false; });
        setTimeout(() => { cut._starting = false; }, 800);     // não arrancou? tenta de novo
      }
    } else {
      const diff = cut.currentTime - t;                       // + = recorte adiantado
      if (Math.abs(diff) > 0.15) { cut.currentTime = t + 0.02; cut.playbackRate = v.playbackRate; }
      else cut.playbackRate = v.playbackRate * (1 - Math.max(-0.12, Math.min(0.12, diff * 2.5)));
    }
  } else if (!cut.paused) cut.pause();
  if (gs) {
    const img = $('#gs-img'), url = assetUrl(gs.file);
    if (img.dataset.src !== url) { img.src = url; img.dataset.src = url; }
    gl.classList.remove('hidden');
    // print comprido rola devagar durante a leitura (como no render)
    const fr = $('#frame'), fh = img.naturalHeight * (fr.clientWidth * 0.94) / Math.max(1, img.naturalWidth);
    const room = fr.clientHeight * 0.92;
    const pr = Math.max(0, Math.min(1, (out - gs.a - 0.6) / Math.max(0.1, gs.b - gs.a - 1.2)));
    img.style.transform = fh > room ? `translateY(${-(fh - room) * pr}px)` : '';
    const S = gs.size || 0.52, right = gs.corner === 'br';
    if (state.p.cutout) {                       // recorte pronto: você recortado, igual à exportação
      cut.classList.remove('hidden');
      cut.style.height = (S * 100) + '%';
      cut.style.left = right ? 'auto' : '3%'; cut.style.right = right ? '3%' : 'auto';
      wrap.style.opacity = 0; wrap.style.transform = ''; wrap.classList.remove('gs-on');
    } else {                                    // ainda sem recorte: quadradinho no canto
      cut.classList.add('hidden');
      wrap.style.opacity = '';
      wrap.style.transformOrigin = right ? '100% 100%' : '0% 100%';
      wrap.style.transform = `translateX(${right ? -3 : 3}%) scale(${S})`;
      wrap.classList.add('gs-on');
    }
  } else if (!gl.classList.contains('hidden')) {
    gl.classList.add('hidden'); cut.classList.add('hidden');
    wrap.style.transform = ''; wrap.style.opacity = ''; wrap.classList.remove('gs-on');
  }

  const active = state.c.overlays.filter(o => out >= o.a && out < o.b);
  $('#frame').classList.toggle('persp', active.some(o => o.type === 'perspective'));
  // transições pontuais — mesmos passos (1 por quadro) do render
  const trs = state.c.overlays.filter(o => (o.type === 'transition' || o.type === 'flash') && out >= o.a - 4 / 30 && out < o.a + 5 / 30);
  const lk = trs.find(o => o.type === 'transition' && (o.style || 'leak') === 'leak');
  const LEAK = [[0.18, 0], [0.45, 0], [0.75, 0.2], [0.95, 0.6], [1, 1], [1, 1], [0.7, 0.55], [0.4, 0.22], [0.15, 0.05]];
  const st = lk ? LEAK[Math.min(8, Math.floor((out - lk.a + 4 / 30) * 30))] : [0, 0];
  $('#leak-layer').style.opacity = st[0];
  $('#leak-layer').style.setProperty('--wh', st[1]);
  const DIP = [0.25, 0.55, 0.85, 1, 0.8, 0.45, 0.15], BLUR = [4, 10, 18, 22, 16, 8, 3];
  const step = o => { const k = Math.floor((out - o.a + 3 / 30) * 30); return k >= 0 && k < 7 ? k : -1; };
  const dip = trs.find(o => (o.type === 'flash' || ['branco', 'escuro'].includes(o.style)) && step(o) >= 0);
  const fl = $('#flash-layer');
  fl.style.background = dip && dip.style === 'escuro' ? '#150C06' : '#F5EFE6';
  fl.style.opacity = dip ? DIP[step(dip)] : 0;
  const bl = trs.find(o => o.style === 'desfoque' && step(o) >= 0);
  fl.style.backdropFilter = bl ? `blur(${BLUR[step(bl)] / 2}px)` : '';
  if (bl && !dip) { fl.style.background = 'transparent'; fl.style.opacity = 1; }
  if (!v.paused && out > state.lastOut && out - state.lastOut < 0.5) {
    for (const o of state.c.overlays) {
      if (o.type !== 'sfx') continue;
      const m = state.status.sfx.find(x => x.name === o.sfx) || {};
      const at = o.a - (m.lead || 0);   // adiantado: o pico cai no momento marcado
      if (at > state.lastOut && at <= out) playSfx(o.sfx, (state.c.settings.sfx_volume || 0.9) * Math.pow(10, (m.gain ?? -6) / 20) * 1.6);
    }
  }
  state.lastOut = out;

  const pb = $('#progress-layer div'); if (pb) pb.style.width = (100 * out / (state.c.duration || 1)).toFixed(2) + '%';
  if (inCut) { renderCutCaption(t); highlightWord(t); drawPlayhead(t, force); return; }
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
    // entrada da linha (desfoque → nítido; na frase especial também de cima/de lado): o atraso negativo
    // mantém a animação contínua mesmo quando o HTML é refeito a cada palavra revelada
    const enterCss = l => {
      const t0 = Math.max(em.a, l.words[0].a), dt = out - t0;
      if (dt < 0 || dt > 0.3) return '';
      return `animation:em-${l.enter || 'blur'} .24s ease-out both;animation-delay:${(-dt).toFixed(3)}s;`;
    };
    const lines = L.lines.map(l => {
      const words = l.words.map(t => `<span class="t${out + 0.001 < Math.max(em.a, t.a) ? ' hide' : ''}" data-i="${t.i}">${esc(applyCase(t.w, kase))}</span>`).join(' ');
      let st = `font-size:${l.size * k}px;letter-spacing:${-l.size * 0.045 * k}px;${enterCss(l)}`;
      if (L.per_line) {
        const x = l.align === 'left' ? `left:${l.x * k}px` : l.align === 'right' ? `right:${(FW - l.x) * k}px` : `left:${l.x * k}px;translate:-50% 0`;
        st += `position:absolute;top:${l.top * k}px;${x};white-space:nowrap;`;
      }
      return `<span class="ln${l.gold ? ' gold' : ''}" style="${st}">${words}</span>`;
    }).join('');
    const i0 = toks[0].i, i1 = toks.at(-1).i;
    html = L.per_line
      ? `<div class="emph special" data-i0="${i0}" data-i1="${i1}" title="Frase especial — na exportação a palavra grande fica ATRÁS da cabeça" style="inset:0;--gold:${s.accent || '#C29A5B'}">${lines}</div>`
      : `<div class="emph" data-i0="${i0}" data-i1="${i1}" title="Clique para corrigir o texto" style="top:${(L.y - total / 2) * k}px;${pos};--gold:${s.accent || '#C29A5B'}">${lines}</div>`;
  } else if (s.captions !== 'none') {
    const c = state.c.captions.find(c => out >= c.a && out < c.b);
    if (c) {
      const i0 = c.words[0].i, i1 = c.words.at(-1).i;
      const cls = 'cap ' + (s.captions === 'clean' ? 'clean' + (s.caption_box ? ' boxed' : '') : s.captions === 'classic' ? 'classic' : '');
      const ws = c.words.map((w, j) => {
        const next = c.words[j + 1];
        const on = s.captions === 'pop' && out >= w.a && out < (next ? next.a : c.b);
        let t = esc(applyCase(w.w, kase));
        if (s.captions === 'clean' && j === c.words.length - 1) t = t.replace(/[,;:]$/, '');
        return `<span data-i="${w.i}"${on ? ' class="hi"' : ''}>${t}</span>`;
      });
      const txt = ws.join(' ');
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

function renderCutCaption(t) {
  // no modo "ver cortes": mostra, riscado, o que foi falado no trecho cortado
  const words = state.p.words;
  const i = words.findIndex(w => w.w && t >= w.start - 0.05 && t <= w.end + 0.15);
  const layer = $('#cap-layer');
  let html = '';
  if (i >= 0) {
    const a = Math.max(0, i - 1), txt = words.slice(a, a + 3).map(w => w.w).filter(Boolean).join(' ');
    html = `<div class="cap clean cutcap">${esc(txt)}</div>`;
  }
  layer.classList.add('clean');
  if (layer._h !== html) { layer.innerHTML = html; layer._h = html; }
  for (const id of ['#title-layer', '#behind-layer']) { $(id).innerHTML = ''; $(id)._h = ''; }
  $('#motion-layer').querySelectorAll('iframe').forEach(f => f.style.display = 'none');
  $('#ov-layer').querySelectorAll(':scope > div').forEach(d => d.style.display = 'none');
}

function toggleShowCuts() {
  state.showCuts = !state.showCuts;
  $('#show-cuts').classList.toggle('on', state.showCuts);
  $('#show-cuts').textContent = state.showCuts ? '👁 Vendo cortes' : '👁 Ver cortes';
  toast(state.showCuts ? 'Vendo o vídeo original: o que foi tirado aparece em vermelho. R restaura o trecho sob a agulha.' : 'Visão de edição: os pedaços encostados, como no vídeo final');
  tl.v0 = 0; tl.zoom = 1; $('#tl-zoom').value = 1;     // o eixo muda (original × final)
  drawTimeline();
  tick(true);
}

function togglePlay() {
  const v = $('#video');
  if (v.paused && state.showCuts) {
    if (v.currentTime >= state.p.source.duration - 0.05) v.currentTime = 0;
    return v.play();
  }
  if (v.paused) {
    const segs = state.c.segments, last = segs.at(-1);
    if (!last) return;
    if (v.currentTime >= last.end - 0.05) v.currentTime = segs[0].start;
    v.play();
  } else v.pause();
}

// ------------------------------------------------------------------ timeline (editor por tempo)
const tl = { zoom: 1, v0: 0, sel: null, markIn: null, drag: null, seg: null, trim: null };
let tlBase = null;
// ---------------------------------------------------------------- timeline estilo CapCut
// Visão de EDIÇÃO (padrão): eixo = tempo do VÍDEO FINAL; os pedaços ficam encostados (excluir um faz o resto
// andar para a esquerda). "Ver cortes" (V): eixo = vídeo original, com o que foi tirado em vermelho.
const editView = () => !state.showCuts;
const musicEnd = () => Math.max(0, ...(state.p?.music || []).map(c => c.start + c.dur));
// na edição, sobra um espaço depois do fim do vídeo (como no CapCut) para a música poder passar do fim
const tlDur = () => editView() ? Math.max(0.1, state.c.duration, musicEnd()) + Math.max(3, state.c.duration * 0.18)
  : state.p.source.duration;
const S2V = t => editView() ? toOutput(t) : t;            // tempo do original -> eixo da timeline
const V2S = tv => editView() ? outToSrc(tv) : tv;         // eixo da timeline -> tempo do original
const segV = s => { const a = S2V(s.start); return [a, editView() ? a + (s.end - s.start) : s.end]; };

function tlView() {
  const dur = tlDur();
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
  const ev = editView();
  const del = new Set(state.p.deleted);
  // fundo: na edição, vazio neutro; vendo cortes, o que foi tirado = vermelho listrado
  g.fillStyle = ev ? '#121418' : '#24141a';
  g.fillRect(0, top, W, bot - top);
  if (!ev) {
    g.save(); g.beginPath(); g.rect(0, top, W, bot - top); g.clip();
    g.strokeStyle = 'rgba(255,93,108,.13)'; g.lineWidth = 1;
    for (let px = -(bot - top); px < W; px += 9) { g.beginPath(); g.moveTo(px, bot); g.lineTo(px + (bot - top), top); g.stroke(); }
    g.restore();
  }
  // cada pedaço = um bloco arredondado (dividir/cortar = blocos separados)
  for (const s of state.c.cuts) {
    const [a, b] = segV(s);
    if (b < v.v0 || a > v.v1) continue;
    const xa = x(a) + 1, w = Math.max(2, x(b) - x(a) - 2);
    g.fillStyle = '#123a37';
    g.beginPath(); g.roundRect ? g.roundRect(xa, top + 1, w, bot - top - 2, 5) : g.rect(xa, top + 1, w, bot - top - 2); g.fill();
    g.strokeStyle = 'rgba(25,211,197,.45)'; g.lineWidth = 1; g.stroke();
  }
  // forma de onda
  const wave = state.wave;
  if (wave.length) {
    const mid = (top + bot) / 2, amp = (bot - top - 6) / 2, sd = state.p.source.duration;
    for (let px = 0; px < W; px++) {
      const tv = tlT(px, W);
      if (tv < 0 || tv > v.dur) continue;
      const t = V2S(tv);
      const p = wave[Math.floor(t / sd * wave.length)] || 0;
      g.fillStyle = ev || segIndexAt(t) >= 0 ? col('--accent') : '#6b3640';
      const h = Math.max(1, p * amp);
      g.fillRect(px, mid - h, 1, h * 2);
    }
  }
  // palavras (com zoom suficiente)
  const pxPerSec = W / v.span;
  if (pxPerSec > 45) {
    g.font = '11px Inter, sans-serif';
    g.textBaseline = 'bottom';
    for (const w of state.p.words) {
      if (!w.w || (ev && del.has(w.i))) continue;
      const a = S2V(w.start);
      if (a < v.v0 - 1 || a > v.v1) continue;
      g.fillStyle = del.has(w.i) ? '#a15d68' : '#e9ebf0';
      g.fillText(w.w, x(a) + 1, top - 2, Math.max(8, (w.end - w.start) * pxPerSec + 30));
    }
  }
  // faixa de cima: visuais (dourado = destaque); zoom = traço fino turquesa
  for (const o of state.p.overlays) {
    if (o.type === 'sfx' || o.type === 'transition' || o.type === 'flash' || LANE_TYPES[o.type]) continue;
    const a = S2V(state.p.words[o.w0]?.start ?? 0), b = Math.max(a, S2V(state.p.words[o.w1 ?? o.w0]?.end ?? 0));
    if (b < v.v0 || a > v.v1) continue;
    if (o.type === 'zoom') { g.fillStyle = 'rgba(95,211,200,.8)'; g.fillRect(x(a), 11, Math.max(3, x(b) - x(a)), 3); continue; }
    if (!VISUAL.has(o.type)) continue;
    g.fillStyle = o.type === 'emphasis' ? (state.c.settings.accent || '#C29A5B') : col('--ov');
    g.fillRect(x(a), 2, Math.max(3, x(b) - x(a)), 6);
  }
  // TELA VERDE: barra verde na faixa de cima — puxe as pontas para mudar a duração, arraste para mover
  for (const o of state.p.overlays) {
    if (!LANE_TYPES[o.type]) continue;
    const dg = tl.dragGs?.id === o.id ? tl.dragGs : null;
    const a = dg ? dg.a : S2V(state.p.words[o.w0]?.start ?? 0);
    const b = dg ? dg.b : Math.max(a + 0.1, S2V(state.p.words[o.w1]?.end ?? 0));
    if (b < v.v0 || a > v.v1) continue;
    const xa = x(a), w = Math.max(8, x(b) - x(a));
    const lt = LANE_TYPES[o.type];
    g.fillStyle = lt.color;
    g.beginPath(); g.roundRect ? g.roundRect(xa, 1, w, 12, 4) : g.rect(xa, 1, w, 12); g.fill();
    if (state.selItem?.id === o.id) { g.strokeStyle = '#fff'; g.lineWidth = 1.5; g.stroke(); }
    g.fillStyle = lt.ink; g.font = '600 9px Inter, sans-serif'; g.textBaseline = 'middle';
    g.fillText(lt.label(o), xa + 6, 7.5, Math.max(0, w - 16));
    g.fillStyle = '#eafff4';
    g.fillRect(xa + 1, 3, 3, 8); g.fillRect(xa + w - 4, 3, 3, 8);
  }
  // sons: bolinha roxa (arrastável); sons que "sobem" mostram a faixa da subida
  for (const o of state.p.overlays) {
    if (o.type !== 'sfx') continue;
    const t = tl.dragSfx?.id === o.id ? tl.dragSfx.t : S2V(sfxT(o));
    const lead = sfxLead(o.sfx);
    if (t < v.v0 - lead || t > v.v1 + 1) continue;
    if (lead > 0.3) { g.fillStyle = 'rgba(201,162,255,.28)'; g.fillRect(x(t - lead), bot + 7, x(t) - x(t - lead), 4); }
    const drag = tl.dragSfx?.id === o.id;
    g.fillStyle = drag ? '#fff' : '#c9a2ff';
    g.beginPath(); g.arc(x(t), bot + 9, drag ? 6.5 : 5, 0, 7); g.fill();
    if (drag) { g.fillStyle = 'rgba(255,255,255,.5)'; g.fillRect(x(t), top, 1, bot - top); }
  }
  // cortes de ritmo (troca de plano sem tirar nada da fala): traço fino
  let lastShot = null;
  for (const p of state.c.segments) {
    const a = ev ? p.out : p.start;
    if (p.shot != null && lastShot != null && p.shot !== lastShot && !p.join && a > v.v0 && a < v.v1) {
      g.fillStyle = 'rgba(255,255,255,.45)';
      g.fillRect(x(a) - 0.5, top + 4, 1.5, bot - top - 8);
    }
    lastShot = p.shot;
  }
  // pulso do que acabou de ser cortado/restaurado (visão de cortes)
  if (tl.pulse && !ev) {
    const k = Math.max(0, 1 - (performance.now() - tl.pulse.t0) / 700);
    g.fillStyle = `rgba(255,93,108,${0.75 * k})`;
    for (const [a, b] of tl.pulse.cut) g.fillRect(x(a), top - 4, Math.max(2, x(b) - x(a)), bot - top + 8);
    g.fillStyle = `rgba(25,211,197,${0.6 * k})`;
    for (const [a, b] of tl.pulse.kept) g.fillRect(x(a), top - 4, Math.max(2, x(b) - x(a)), bot - top + 8);
  }
  // junções: losango = transição (cheio = tem, vazado = corte seco)
  for (const j of joins()) {
    const jt = ev ? j.out : j.t;
    if (jt < v.v0 || jt > v.v1) continue;
    const jx = x(jt), jy = top + 11;
    g.save(); g.translate(jx, jy); g.rotate(Math.PI / 4);
    if (j.tr) { g.fillStyle = '#E0BB6A'; g.fillRect(-6, -6, 12, 12); g.strokeStyle = '#150C06'; g.lineWidth = 1.5; g.strokeRect(-6, -6, 12, 12); }
    else { g.fillStyle = 'rgba(14,15,18,.85)'; g.fillRect(-5, -5, 10, 10); g.strokeStyle = 'rgba(255,255,255,.55)'; g.lineWidth = 1.2; g.strokeRect(-5, -5, 10, 10); }
    g.restore();
  }
  if (ev && v.dur > state.c.duration + 0.05) {
    const xe = x(state.c.duration);
    g.fillStyle = 'rgba(0,0,0,.35)'; g.fillRect(xe, top, W - xe, bot - top);
  }
  // régua
  g.fillStyle = '#8b91a0'; g.font = '10px Inter, sans-serif'; g.textBaseline = 'top';
  const step = [0.5, 1, 2, 5, 10, 15, 30, 60].find(st => st * pxPerSec > 70) || 60;
  for (let t = Math.ceil(v.v0 / step) * step; t < v.v1; t += step) {
    g.fillRect(x(t), bot, 1, 4);
    g.fillText(fmt(t) + (step < 1 ? '.' + Math.round((t % 1) * 10) : ''), x(t) + 2, bot + 4);
  }
  // pedaço selecionado: contorno arredondado + alças; prévia do ajuste ao arrastar a borda
  if (tl.seg) {
    let [a, b] = segV({ start: tl.seg[0], end: tl.seg[1] });
    if (tl.trim) {
      const o = tl.trim.side === 'a' ? a : b, nt = tl.trim.v;
      const lo = Math.min(o, nt), hi = Math.max(o, nt);
      const growing = tl.trim.side === 'a' ? nt < o : nt > o;
      g.fillStyle = growing ? 'rgba(25,211,197,.35)' : 'rgba(255,93,108,.45)';
      g.fillRect(x(lo), top, x(hi) - x(lo), bot - top);
      if (tl.trim.side === 'a') a = nt; else b = nt;
      const d = nt - o;
      g.fillStyle = '#fff'; g.font = 'bold 11px Inter, sans-serif'; g.textBaseline = 'top';
      g.fillText(`${d > 0 ? '+' : ''}${d.toFixed(2)}s`, x(nt) + 6, top + 2);
    }
    const sx = x(a) + 1, sw = Math.max(4, x(b) - x(a) - 2);
    g.save();
    g.shadowColor = 'rgba(255,255,255,.35)'; g.shadowBlur = 8;
    g.strokeStyle = '#fff'; g.lineWidth = 2; g.setLineDash([]);
    g.beginPath(); g.roundRect ? g.roundRect(sx, top + 1, sw, bot - top - 2, 9) : g.rect(sx, top + 1, sw, bot - top - 2); g.stroke();
    g.restore();
    g.fillStyle = '#fff';
    for (const xe of [x(a), x(b)]) {
      g.beginPath(); g.roundRect ? g.roundRect(xe - 4, top + (bot - top) / 2 - 13, 8, 26, 4) : g.rect(xe - 4, top + (bot - top) / 2 - 13, 8, 26); g.fill();
    }
  }
  // intervalo selecionado (shift + arrastar)
  if (tl.sel) {
    const a = S2V(tl.sel[0]), b = Math.max(a, S2V(tl.sel[1]));
    g.fillStyle = 'rgba(255,255,255,.16)';
    g.fillRect(x(a), 0, x(b) - x(a), H);
    g.fillStyle = '#fff';
    g.fillRect(x(a), 0, 1, H); g.fillRect(x(b), 0, 1, H);
  } else if (tl.markIn != null) {
    g.fillStyle = '#ffd60a'; g.fillRect(x(S2V(tl.markIn)), 0, 2, H);
  }
  tlBase = g.getImageData(0, 0, cv.width, cv.height);
  drawMusicLane();
  drawPlayhead($('#video').currentTime, true);
  updateSelUI();
}
let lastHead = -1;
function drawPlayhead(t, force) {
  const cv = $('#timeline');
  if (!tlBase) return;
  const W = cv.clientWidth;
  const tv = S2V(t);
  // acompanha a agulha quando está com zoom e tocando
  const v = tlView();
  if (tl.zoom > 1 && !tl.trim && !tl.scrubbing && !tl.dragMusic && (tv > v.v1 - v.span * 0.06 || tv < v.v0) && (!$('#video').paused || force)) {
    const target = Math.max(0, Math.min(v.dur - v.span, tv - v.span * 0.2));
    if (Math.abs(target - v.v0) > v.span * 0.02) {   // só rola se houver para onde (evita laço no fim)
      tl.v0 = target;
      drawTimeline();
      return;
    }
  }
  const px = Math.round(tlX(tv, W));
  if (px === lastHead && !force) return;
  lastHead = px;
  const g = cv.getContext('2d');
  g.putImageData(tlBase, 0, 0);
  g.fillStyle = '#fff';
  g.fillRect(px - 1, 0, 2, cv.clientHeight);
  g.beginPath();                          // alça para pegar a agulha
  g.moveTo(px - 7, 0); g.lineTo(px + 7, 0); g.lineTo(px + 7, 10); g.lineTo(px, 17); g.lineTo(px - 7, 10); g.closePath();
  g.fill();
  drawMusicHead(tv);
}
function updateSelUI() {
  const box = $('#tl-sel');
  if (!tl.sel && !tl.seg) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  const r = tl.sel || tl.seg;
  $('#tl-sel-txt').textContent = tl.sel ? `intervalo de ${(r[1] - r[0]).toFixed(2)}s` : `pedaço de ${(r[1] - r[0]).toFixed(2)}s`;
}
function setZoom(z, anchorV) {
  const old = tlView();
  tl.zoom = Math.max(1, Math.min(80, z));
  const span = old.dur / tl.zoom;
  const t = anchorV ?? S2V($('#video').currentTime);
  const frac = (t - old.v0) / old.span;   // o ponto âncora fica no mesmo lugar da tela
  tl.v0 = t - frac * span;
  $('#tl-zoom').value = tl.zoom;
  drawTimeline();
}
async function rangeEdit(mode, range, ripple = false) {
  const r = range || tl.sel || autoRange(mode);
  if (!r) return toast(mode === 'cut' ? 'Selecione um pedaço (clique) ou um intervalo (shift + arrastar).' : 'Posicione a agulha num trecho cortado (vermelho) ou selecione um trecho.', true);
  state.history.push(snapshot());
  try {
    applyServer(await api(`/api/projects/${state.p.id}/range`, { method: 'POST', json: { a: r[0], b: r[1], mode, ripple } }));
    toast(mode === 'cut' ? (ripple ? 'Pedaço excluído — o resto veio para a esquerda' : 'Trecho cortado') : 'Trecho restaurado');
  } catch (e) { toast(e.message, true); }
  tl.sel = null; tl.markIn = null; drawTimeline();
}
function autoRange(mode) {
  // R sem seleção: restaura o trecho cortado onde a agulha está (na visão de cortes)
  const t = $('#video').currentTime;
  if (mode === 'cut') return null;
  if (segIndexAt(t) >= 0) return null;
  const segs = state.c.segments;
  const prev = [...segs].reverse().find(s => s.end <= t), next = segs.find(s => s.start >= t);
  return [prev ? prev.end : 0, next ? next.start : state.p.source.duration];
}
function selectSegAt(t) {
  const s = state.c.cuts.find(s => t >= s.start - 0.01 && t <= s.end + 0.01);
  tl.seg = s ? [s.start, s.end] : null;
  tl.sel = null;
  drawTimeline();
}
// DIVIDIR (S / B / X): a lâmina no ponto da agulha — dois cortes = um pedaço
function splitAtHead() {
  const t = +$('#video').currentTime.toFixed(3);
  const s = state.c.cuts.find(s => t > s.start + 0.05 && t < s.end - 0.05);
  if (!s) return toast('Posicione a agulha dentro de um pedaço (longe das pontas) para dividir.', true);
  patch({ splits: [...(state.p.splits || []), t] });
  tl.seg = null;
  toast('Dividido ✂ — clique num pedaço para selecioná-lo; Delete exclui');
}
// ⌘C / ⌘V: copia o item selecionado (música, tela verde, som, destaque…) e cola na agulha
function selectItem(kind, id) { state.selItem = id ? { kind, id } : null; }
function copySelected() {
  const it = state.selItem || (state.musicSel ? { kind: 'music', id: state.musicSel } : null);
  if (!it) return toast('Clique num item (música, trecho verde, som) para selecionar e depois ⌘C.', true);
  const src = it.kind === 'music' ? musicClips().find(c => c.id === it.id) : state.p.overlays.find(o => o.id === it.id);
  if (!src) return;
  state.clip = { kind: it.kind, data: JSON.parse(JSON.stringify(src)) };
  toast(`Copiado: ${it.kind === 'music' ? '♫ ' + (src.title || 'música') : (TYPE_INFO[src.type]?.[1] || src.type)} — ⌘V cola na agulha`);
}
function pasteAtHead() {
  const c = state.clip;
  if (!c) return toast('Nada copiado ainda (selecione um item e ⌘C).', true);
  if (c.kind === 'music') {
    const start = Math.max(0, toOutput($('#video').currentTime));
    const others = musicClips().map(x => (x.start < start && x.start + x.dur > start) ? { ...x, dur: +(start - x.start).toFixed(2) } : x);
    const next = Math.min(1e9, ...others.filter(x => x.start >= start).map(x => x.start));
    const clip = { ...c.data, id: uid(), start: +start.toFixed(2), dur: +Math.max(0.5, Math.min(c.data.dur, next - start)).toFixed(2) };
    state.musicSel = clip.id;
    patch({ music: [...others, clip] });
  } else {
    const W = state.p.words, del = new Set(state.p.deleted), o = c.data;
    const n = Math.max(0, (o.w1 ?? o.w0) - o.w0);
    const w0 = wordAtHead();
    let w1 = w0, k = 0;
    while (k < n && w1 + 1 < W.length) { w1++; if (!del.has(w1)) k++; }
    const no = { ...o, id: uid(), w0, w1, auto: false };
    patch({ overlays: [...state.p.overlays, no] });
    selectItem('overlay', no.id);
  }
  toast('Colado na agulha');
}

function deleteSelected() {
  if (tl.sel) return rangeEdit('cut', tl.sel, true);
  if (tl.seg) { const r = tl.seg; tl.seg = null; return rangeEdit('cut', r, true); }
  if (state.musicSel) return removeMusic(state.musicSel);
  toast('Selecione um pedaço (clique nele) para excluir.', true);
}
function nearHead(e) {
  const cv = $('#timeline'), r = cv.getBoundingClientRect();
  const px = tlX(S2V($('#video').currentTime), r.width);
  const y = e.clientY - r.top;
  return Math.abs(e.clientX - r.left - px) <= (y < 22 ? 10 : 5);   // alça no topo: área maior
}
function edgeAt(e) {
  if (!tl.seg || nearHead(e)) return null;
  const cv = $('#timeline'), r = cv.getBoundingClientRect(), W = r.width, px = e.clientX - r.left;
  const y = e.clientY - r.top;
  const mid = 26 + (cv.clientHeight - 18 - 26) / 2;
  if (Math.abs(y - mid) > 18) return null;      // só nas alças brancas (meio da faixa), de propósito
  const [a, b] = segV({ start: tl.seg[0], end: tl.seg[1] });
  const da = Math.abs(px - tlX(a, W)), db = Math.abs(px - tlX(b, W));
  if (Math.min(da, db) > 6) return null;
  return da <= db ? 'a' : 'b';
}

// coloca o menu dentro da tela (abre para cima/esquerda perto das bordas)
function placeMenu(m, x, y) {
  m.style.left = '0px'; m.style.top = '0px';
  const r = m.getBoundingClientRect(), pad = 8;
  const left = x + r.width + pad > innerWidth ? Math.max(pad, x - r.width) : x;
  const top = y + r.height + pad > innerHeight ? Math.max(pad, y - r.height) : y;
  m.style.left = left + 'px'; m.style.top = top + 'px';
}

// menu do botão direito num pedaço
function clipMenu(ev, seg) {
  document.querySelector('.ctx-menu')?.remove();
  const m = document.createElement('div');
  m.className = 'ctx-menu';
  m.style.left = ev.clientX + 'px'; m.style.top = ev.clientY + 'px';
  m.innerHTML = `<button data-a="split">✂ Dividir aqui <kbd>S</kbd></button>
    <button data-a="del" class="danger">🗑 Excluir pedaço <kbd>Del</kbd></button>
    <button data-a="cancel">Cancelar</button>`;
  document.body.appendChild(m);
  placeMenu(m, ev.clientX, ev.clientY);
  const close = () => { m.remove(); removeEventListener('mousedown', outside, true); };
  const outside = e2 => { if (!m.contains(e2.target)) close(); };
  setTimeout(() => addEventListener('mousedown', outside, true), 0);
  m.onclick = e2 => {
    const a = e2.target.closest('[data-a]')?.dataset.a;
    close();
    if (a === 'split') splitAtHead();
    if (a === 'del' && seg) { tl.seg = [seg.start, seg.end]; deleteSelected(); }
  };
}

function setupTimeline() {
  const cv = $('#timeline');
  const tAt = e => { const r = cv.getBoundingClientRect(); return Math.max(0, Math.min(tlDur(), tlT(e.clientX - r.left, r.width))); };
  cv.addEventListener('contextmenu', e => {
    e.preventDefault();
    const t = V2S(tAt(e));
    const s = state.c.cuts.find(s => t >= s.start - 0.01 && t <= s.end + 0.01);
    if (s) { tl.seg = [s.start, s.end]; drawTimeline(); }
    $('#video').currentTime = t; tick(true);
    clipMenu(e, s);
  });
  cv.addEventListener('mousedown', e => {
    if (e.button !== 0) return;
    const r = cv.getBoundingClientRect();
    state.musicSel = null; drawMusicLane();
    // faixa de sons (embaixo): bolinha = trocar/remover (arrastar = mover); espaço vazio = acrescentar
    if (e.clientY - r.top > cv.clientHeight - 18) {
      const tv = tAt(e), tol = tlView().span / r.width * 9;
      const near = state.p.overlays.filter(o => o.type === 'sfx' && Math.abs(S2V(sfxT(o)) - tv) < tol)
        .sort((a, b) => Math.abs(S2V(sfxT(a)) - tv) - Math.abs(S2V(sfxT(b)) - tv));
      const o = near[0];
      if (!o) return openSfxPicker(null, wordAtTime(V2S(tv)));
      const x0 = e.clientX, grab = S2V(sfxT(o)) - tv;
      let moved = false;
      const move = ev => {
        if (!moved && Math.abs(ev.clientX - x0) < 4) return;
        moved = true;
        tl.dragSfx = { id: o.id, t: Math.max(0, Math.min(tlDur(), tAt(ev) + grab)) };
        drawTimeline();
      };
      const up = () => {
        removeEventListener('mousemove', move); removeEventListener('mouseup', up);
        selectItem('overlay', o.id);
        if (!moved) { tl.dragSfx = null; return openSfxPicker(o); }
        const nt = tl.dragSfx.t;
        tl.dragSfx = null;
        moveSfx(o, V2S(nt));
      };
      addEventListener('mousemove', move); addEventListener('mouseup', up);
      return;
    }
    // barra verde (tela verde): pontas = duração, meio = mover
    if (e.clientY - r.top < 15) {
      const tv = tAt(e), W2 = r.width, px = e.clientX - r.left;
      const hitGs = state.p.overlays.filter(o => LANE_TYPES[o.type]).map(o => {
        const a = S2V(state.p.words[o.w0].start), b = S2V(state.p.words[o.w1].end);
        return { o, xa: tlX(a, W2), xb: tlX(b, W2), a, b };
      }).find(h => px >= h.xa - 6 && px <= h.xb + 6);
      if (hitGs) {
        const edge = Math.abs(px - hitGs.xa) < 8 ? 'a' : Math.abs(px - hitGs.xb) < 8 ? 'b' : null;
        const W = state.p.words, del = new Set(state.p.deleted);
        const keptIdx = W.filter(w => !del.has(w.i) && w.w).map(w => w.i);
        const firstFrom = t => keptIdx.find(i => W[i].start >= t - 0.05) ?? keptIdx.at(-1);
        const lastUpTo = t => [...keptIdx].reverse().find(i => W[i].end <= t + 0.05) ?? keptIdx[0];
        const o = hitGs.o, x0 = e.clientX;
        const A = hitGs.a, B = hitGs.b, dur = B - A, total = tlDur();
        const i0 = keptIdx.indexOf(o.w0), count = Math.max(0, keptIdx.indexOf(o.w1) - i0);
        let moved = false;
        const move = ev => {
          if (!moved && Math.abs(ev.clientX - x0) < 3) return;
          moved = true;
          const d = tAt(ev) - tv;
          let na = A, nb = B;
          if (edge === 'a') na = Math.max(0, Math.min(B - 0.4, A + d));
          else if (edge === 'b') nb = Math.min(state.c.duration, Math.max(A + 0.4, B + d));
          else { na = Math.max(0, Math.min(state.c.duration - dur, A + d)); nb = na + dur; }
          tl.dragGs = { id: o.id, a: na, b: nb };
          drawTimeline();
        };
        const up = () => {
          removeEventListener('mousemove', move); removeEventListener('mouseup', up);
          const dg = tl.dragGs; tl.dragGs = null;
          selectItem('overlay', o.id);
          if (!moved || !dg) { $('#video').currentTime = state.p.words[o.w0].start; tick(true); drawTimeline(); return; }
          let w0 = o.w0, w1 = o.w1;
          if (edge === 'a') w0 = Math.min(firstFrom(V2S(dg.a)), o.w1);
          else if (edge === 'b') w1 = Math.max(lastUpTo(V2S(dg.b)), o.w0);
          else {                                  // mover: mesmo número de palavras
            w0 = firstFrom(V2S(dg.a));
            const k = keptIdx.indexOf(w0);
            w1 = keptIdx[Math.min(keptIdx.length - 1, k + count)];
          }
          editOverlay(o.id, { w0, w1 });
        };
        addEventListener('mousemove', move); addEventListener('mouseup', up);
        return;
      }
    }
    // losango numa junção: escolher a transição daquele corte
    const jy = e.clientY - r.top;
    if (jy >= 26 && jy <= 26 + 22) {
      const tv = tAt(e), tol = tlView().span / r.width * 9;
      const j = joins().find(j => Math.abs((editView() ? j.out : j.t) - tv) < tol);
      if (j) return openTransitionPicker(j);
    }
    const t0 = tAt(e), x0 = e.clientX;
    const v = $('#video');
    const scrubTo = ev => { tl.scrubbing = true; v.currentTime = V2S(tAt(ev)); tick(true); };
    // 1) pegar a agulha (alça ou linha) — tem prioridade sobre tudo
    if (nearHead(e)) {
      const move = ev => scrubTo(ev);
      const up = () => { tl.scrubbing = false; removeEventListener('mousemove', move); removeEventListener('mouseup', up); };
      addEventListener('mousemove', move); addEventListener('mouseup', up);
      return;
    }
    // 2) borda do pedaço selecionado = estender/encurtar (no original: devolve ou tira fala)
    const side = edgeAt(e);
    if (side) {
      const [va, vb] = segV({ start: tl.seg[0], end: tl.seg[1] });
      const origV = side === 'a' ? va : vb, origS = side === 'a' ? tl.seg[0] : tl.seg[1];
      tl.trim = { side, v: origV };
      const move = ev => {
        let tv = tAt(ev);
        if (side === 'a') tv = Math.min(tv, vb - 0.1); else tv = Math.max(tv, va + 0.1);
        tl.trim.v = tv;
        v.currentTime = Math.max(0, Math.min(state.p.source.duration, origS + (tv - origV)));
        drawTimeline();
      };
      const up = async () => {
        removeEventListener('mousemove', move); removeEventListener('mouseup', up);
        const d = tl.trim.v - origV;
        tl.trim = null;
        if (Math.abs(d) < 0.02) return drawTimeline();
        const nt = Math.max(0, Math.min(state.p.source.duration, origS + d)), other = side === 'a' ? tl.seg[1] : tl.seg[0];
        const grow = side === 'a' ? nt < origS : nt > origS;
        await rangeEdit(grow ? 'keep' : 'cut', [Math.min(nt, origS), Math.max(nt, origS)]);
        selectSegAt((nt + other) / 2);
      };
      addEventListener('mousemove', move); addEventListener('mouseup', up);
      return;
    }
    // 3) shift + arrastar = selecionar um intervalo (Delete exclui)
    if (e.shiftKey) {
      tl.seg = null;
      const move = ev => { const t1 = tAt(ev); tl.sel = [V2S(Math.min(t0, t1)), V2S(Math.max(t0, t1))]; drawTimeline(); };
      const up = () => { removeEventListener('mousemove', move); removeEventListener('mouseup', up); };
      addEventListener('mousemove', move); addEventListener('mouseup', up);
      return;
    }
    // 4) clique/arrasto normal = mover a agulha; clique sem arrastar seleciona o pedaço
    let moved = false;
    tl.sel = null;
    scrubTo(e);
    const move = ev => { if (Math.abs(ev.clientX - x0) > 3) moved = true; scrubTo(ev); };
    const up = () => {
      tl.scrubbing = false;
      removeEventListener('mousemove', move); removeEventListener('mouseup', up);
      if (!moved) selectSegAt(V2S(t0)); else drawTimeline();
    };
    addEventListener('mousemove', move); addEventListener('mouseup', up);
  });
  cv.addEventListener('mousemove', e => {
    if (e.buttons) return;
    const r2 = cv.getBoundingClientRect();
    let gsCur = null;
    if (e.clientY - r2.top < 15) {
      const px = e.clientX - r2.left;
      for (const o of state.p.overlays.filter(o => LANE_TYPES[o.type])) {
        const xa = tlX(S2V(state.p.words[o.w0].start), r2.width), xb = tlX(S2V(state.p.words[o.w1].end), r2.width);
        if (px >= xa - 6 && px <= xb + 6) gsCur = (Math.abs(px - xa) < 8 || Math.abs(px - xb) < 8) ? 'ew-resize' : 'grab';
      }
    }
    cv.style.cursor = gsCur || (nearHead(e) ? 'grab' : edgeAt(e) ? 'ew-resize' : 'default');
  });
  const wheel = e => {
    e.preventDefault();
    const horizontal = Math.abs(e.deltaX) > Math.abs(e.deltaY) || e.shiftKey;
    if (horizontal) {   // trackpad para o lado ou shift+scroll: anda pela timeline
      tl.v0 += (e.deltaX || e.deltaY) / cv.clientWidth * tlView().span; drawTimeline(); return;
    }
    const factor = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0025));
    setZoom(tl.zoom * factor, tAt(e), e);
  };
  cv.addEventListener('wheel', wheel, { passive: false });
  $('#music-lane').addEventListener('wheel', wheel, { passive: false });
  $('#tl-zoom').oninput = e => setZoom(+e.target.value);
  $('#tl-in').onclick = () => setZoom(tl.zoom * 1.6);
  $('#tl-out').onclick = () => setZoom(tl.zoom / 1.6);
  $('#tl-split').onclick = splitAtHead;
  $('#tl-cut').onclick = deleteSelected;
  $('#tl-keep').onclick = () => rangeEdit('keep');
  $('#tl-clear').onclick = () => { tl.sel = null; tl.seg = null; tl.markIn = null; drawTimeline(); };
  setupMusicLane();
}

// ------------------------------------------------------------------ faixa de música (estilo CapCut)
// clipes no tempo do VÍDEO EDITADO: {id, file: 'lib:slug'|asset, title, start, in, dur, len, vol, fade}
const M2V = out => editView() ? out : outToSrc(out);
const V2M = tv => editView() ? tv : toOutput(tv);
let musicLib = null;
const musicEls = {};
const musicClips = () => state.p.music || [];

function drawMusicLane() {
  const cv = $('#music-lane');
  if (!cv || !state.c) return;
  const dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext('2d');
  g.scale(dpr, dpr);
  g.fillStyle = '#121418'; g.fillRect(0, 0, W, H);
  const x = t => tlX(t, W);
  const clips = musicClips();
  if (!clips.length) {
    // faixa vazia: um botão claro "＋ Adicionar música" (clique em qualquer ponto da faixa)
    const label = '＋  Adicionar música';
    g.font = '600 12px Inter, sans-serif'; g.textBaseline = 'middle';
    const tw = g.measureText(label).width + 24;
    g.fillStyle = 'rgba(176,160,255,.16)'; g.strokeStyle = 'rgba(176,160,255,.55)'; g.lineWidth = 1;
    g.beginPath(); g.roundRect ? g.roundRect(8, 4, tw, H - 8, 8) : g.rect(8, 4, tw, H - 8); g.fill(); g.stroke();
    g.fillStyle = '#e4ddff'; g.fillText(label, 20, H / 2);
  }
  for (const c of clips) {
    const d = tl.dragMusic?.id === c.id ? tl.dragMusic : c;
    const a = M2V(d.start), b = editView() ? d.start + d.dur : M2V(Math.min(state.c.duration, d.start + d.dur));
    const xa = x(a), w = Math.max(6, x(b) - x(a));
    const sel = state.musicSel === c.id;
    g.fillStyle = sel ? '#4a3b86' : '#3a2f66';
    g.beginPath(); g.roundRect ? g.roundRect(xa + 1, 3, w - 2, H - 6, 6) : g.rect(xa + 1, 3, w - 2, H - 6); g.fill();
    g.strokeStyle = sel ? '#fff' : 'rgba(176,160,255,.7)'; g.lineWidth = sel ? 2 : 1; g.stroke();
    // "ondinha" decorativa
    g.fillStyle = 'rgba(200,190,255,.35)';
    for (let px = xa + 4; px < xa + w - 4; px += 3) {
      const hh = 3 + 6 * Math.abs(Math.sin(px * 0.13 + c.start)) * Math.abs(Math.cos(px * 0.031));
      g.fillRect(px, H / 2 - hh / 2, 1.5, hh);
    }
    g.fillStyle = '#efeaff'; g.font = '600 11px Inter, sans-serif'; g.textBaseline = 'middle';
    g.fillText('♫ ' + (c.title || c.file), xa + 8, H / 2, Math.max(0, w - 16));
    if (sel) {
      g.fillStyle = '#fff';
      for (const xe of [xa + 1, xa + w - 1]) { g.beginPath(); g.roundRect ? g.roundRect(xe - 3, H / 2 - 9, 6, 18, 3) : g.rect(xe - 3, H / 2 - 9, 6, 18); g.fill(); }
    }
  }
  if (editView() && tlDur() > state.c.duration + 0.05) {     // depois do fim do vídeo: escurecido
    const xe = x(state.c.duration);
    g.fillStyle = 'rgba(0,0,0,.45)'; g.fillRect(xe, 0, W - xe, H);
    g.fillStyle = '#ff5d6c'; g.fillRect(xe - 1, 0, 2, H);
    g.fillStyle = '#c8ccd6'; g.font = '10px Inter, sans-serif'; g.textBaseline = 'top';
    g.fillText('fim do vídeo', xe + 4, 2);
  }
  state.musicBase = g.getImageData(0, 0, cv.width, cv.height);
}
function drawMusicHead(tv) {
  const cv = $('#music-lane');
  if (!cv || !state.musicBase) return;
  const g = cv.getContext('2d');
  g.putImageData(state.musicBase, 0, 0);
  g.fillStyle = '#fff';
  g.fillRect(Math.round(tlX(tv, cv.clientWidth)) - 1, 0, 2, cv.clientHeight);
}

async function loadMusicLib() {
  if (!musicLib) { try { musicLib = await api('/api/music'); } catch { musicLib = []; } }
  return musicLib;
}
function audioLen(src) {
  return new Promise(res => { const a = new Audio(); a.preload = 'metadata'; a.src = src;
    a.onloadedmetadata = () => res(a.duration || 0); a.onerror = () => res(0); });
}
const musicSrc = c => c.file.startsWith('lib:') ? `/api/music/${c.file.slice(4)}/file` : assetUrl(c.file);

function addMusicClip(file, title, len) {
  const start = Math.max(0, Math.min(state.c.duration - 1, toOutput($('#video').currentTime)));
  // a música que estiver tocando nesse ponto termina aqui; a nova vai até a próxima (ou até o fim do vídeo)
  const others = musicClips().map(c => (c.start < start && c.start + c.dur > start) ? { ...c, dur: +(start - c.start).toFixed(2) } : c);
  const nextStart = Math.min(1e9, ...others.filter(c => c.start >= start).map(c => c.start));
  const dur = Math.max(1, Math.min(len || 9999, nextStart - start, Math.max(state.c.duration - start, 1)));
  const clip = { id: uid(), file, title, start: +start.toFixed(2), in: 0, dur: +dur.toFixed(2), len: len || null, vol: 0.18, fade: 1.5 };
  state.musicSel = clip.id;
  patch({ music: [...others, clip] }).then(() => flashMusic(clip.id));
  toast(`♫ ${title} adicionada em ${fmt(start)} na faixa de música (embaixo) — arraste para mover, puxe as pontas para aparar`, false, 6000);
}
// mostra onde a música entrou: rola a timeline até ela e pisca
function flashMusic(id) {
  const c = musicClips().find(x => x.id === id);
  if (!c) return;
  const v = tlView();
  if (c.start < v.v0 || c.start > v.v1) { tl.v0 = Math.max(0, c.start - v.span * 0.1); drawTimeline(); }
  const lane = $('#music-lane');
  lane.classList.remove('flash'); void lane.offsetWidth; lane.classList.add('flash');
  lane.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

function removeMusic(id) {
  state.musicSel = null;
  patch({ music: musicClips().filter(c => c.id !== id) });
  toast('Música removida');
}
function editMusic(id, changes, record = true) {
  patch({ music: musicClips().map(c => c.id === id ? { ...c, ...changes } : c) }, record);
}

function replaceMusic(id, file, title, len) {
  const c = musicClips().find(x => x.id === id);
  if (!c) return;
  const others = musicClips().filter(o => o.id !== id);
  const nextStart = Math.min(1e9, ...others.filter(o => o.start >= c.start + 0.01).map(o => o.start));
  const dur = Math.max(0.5, Math.min(len || c.dur, Math.max(c.dur, Math.min(len || c.dur, nextStart - c.start)), nextStart - c.start));
  editMusic(id, { file, title, len: len || null, in: 0, dur: +dur.toFixed(2) });
  toast(`🔁 Música trocada por “${title}”`);
}

async function openMusicPicker(replaceId = null) {
  const lib = await loadMusicLib();
  const cur = replaceId && musicClips().find(c => c.id === replaceId);
  const body = dialog(`<h3>${cur ? 'Trocar a música “' + esc(cur.title || '') + '”' : 'Música'}</h3>
    <p class="hint">▶ para ouvir · “＋ Adicionar” coloca a música a partir da agulha, na faixa de música (depois é só arrastar/aparar).
      Todas instrumentais e liberadas para uso comercial (Mixkit; Kevin MacLeod com crédito automático na exportação).</p>
    ${replaceId ? '' : `<div class="mus-ig">🔥 <b>Quer o áudio que está em alta no Instagram?</b> Ele só pode ser usado <i>dentro</i> do app
      (direitos autorais) — e é justamente lá que ajuda no alcance. Deixe a faixa de música vazia aqui, exporte, e na hora de postar
      toque em <b>“Adicionar áudio”</b> no Instagram e escolha um dos <b>em alta</b>, bem baixinho.</div>`}
    ${[...new Set(lib.map(m => m.group || 'Outras'))].map(g => `<h4 class="mus-group">${esc(g)}</h4>
      <div class="mus-list">${lib.filter(m => (m.group || 'Outras') === g).map(m => `<div class="mus-item">
      <button class="act" data-play="${m.slug}">▶</button>
      <div class="mus-txt"><b>${esc(m.title)}</b><span class="muted">${esc(m.mood)}${m.duration ? ' · ' + fmt(m.duration) : ''}</span></div>
      <button class="mus-add" data-use="${m.slug}">${replaceId ? '🔁 Trocar por esta' : '＋ Adicionar'}</button></div>`).join('')}</div>`).join('')}
    <div class="row" style="margin-top:12px"><button class="tool" id="mus-upload">⬆ Enviar música minha (MP3)</button></div>`);
  let player = null;
  body.addEventListener('click', async e => {
    const pl = e.target.closest('[data-play]');
    if (pl) {
      const m = lib.find(x => x.slug === pl.dataset.play);
      if (player && player._slug === m.slug && !player.paused) { player.pause(); pl.textContent = '▶'; return; }
      player?.pause(); $$('[data-play]', body).forEach(b => b.textContent = '▶');
      player = new Audio(m.src); player._slug = m.slug; player.volume = 0.6; player.play(); pl.textContent = '❚❚';
      return;
    }
    const use = e.target.closest('[data-use]') || (e.target.closest('.mus-txt') && e.target.closest('.mus-item')?.querySelector('[data-use]'));
    if (use) {
      player?.pause();
      const m = lib.find(x => x.slug === use.dataset.use);
      const len = m.duration || await audioLen(m.src);
      $('#dialog').classList.add('hidden');
      if (replaceId) replaceMusic(replaceId, m.file, m.title, len); else addMusicClip(m.file, m.title, len);
    }
  });
  $('#mus-upload', body).onclick = () => pickAsset(async file => {
    player?.pause();
    $('#dialog').classList.add('hidden');
    const title = file.replace(/^[a-f0-9]{6}_/, '').replace(/\.[^.]+$/, ''), len = await audioLen(assetUrl(file));
    if (replaceId) replaceMusic(replaceId, file, title, len); else addMusicClip(file, title, len);
  }, 'audio/*');
  const obs = new MutationObserver(() => { if ($('#dialog').classList.contains('hidden')) { player?.pause(); obs.disconnect(); } });
  obs.observe($('#dialog'), { attributes: true });
}

function musicMenu(ev, c) {
  document.querySelector('.ctx-menu')?.remove();
  const m = document.createElement('div');
  m.className = 'ctx-menu';
  m.style.left = ev.clientX + 'px'; m.style.top = ev.clientY + 'px';
  const pct = v => Math.round(v / 0.36 * 100);
  m.innerHTML = `<div class="ctx-title">♫ ${esc(c.title || '')}</div>
    <div class="ctx-row">🔊 <input type="range" min="0" max="0.6" step="0.01" value="${c.vol ?? 0.18}"><span class="vol-val">${pct(c.vol ?? 0.18)}%</span></div>
    <button data-a="swap">🔁 Trocar música</button>
    <button data-a="split">✂ Dividir a música na agulha</button>
    <button data-a="del" class="danger">🗑 Remover música <kbd>Del</kbd></button>`;
  document.body.appendChild(m);
  placeMenu(m, ev.clientX, ev.clientY);
  $('input', m).oninput = e2 => { $('.vol-val', m).textContent = pct(+e2.target.value) + '%'; };
  const close = () => { m.remove(); removeEventListener('mousedown', outside, true); };
  const outside = e2 => { if (!m.contains(e2.target)) close(); };
  setTimeout(() => addEventListener('mousedown', outside, true), 0);
  $('input', m).onchange = e2 => editMusic(c.id, { vol: +e2.target.value });
  m.onclick = e2 => {
    const a = e2.target.closest('[data-a]')?.dataset.a;
    if (!a) return;
    close();
    if (a === 'del') removeMusic(c.id);
    if (a === 'swap') openMusicPicker(c.id);
    if (a === 'split') {
      const t = toOutput($('#video').currentTime);
      if (t <= c.start + 0.3 || t >= c.start + c.dur - 0.3) return toast('Ponha a agulha dentro da música para dividir.', true);
      const d1 = t - c.start;
      const c2 = { ...c, id: uid(), start: +t.toFixed(2), in: +(c.in + d1).toFixed(2), dur: +(c.dur - d1).toFixed(2) };
      patch({ music: musicClips().flatMap(x => x.id === c.id ? [{ ...x, dur: +d1.toFixed(2) }, c2] : [x]) });
    }
  };
}

function setupMusicLane() {
  const cv = $('#music-lane');
  const vAt = e => { const r = cv.getBoundingClientRect(); return Math.max(0, Math.min(tlDur(), tlT(e.clientX - r.left, r.width))); };
  const hit = e => {
    const r = cv.getBoundingClientRect(), px = e.clientX - r.left, W = r.width;
    for (const c of [...musicClips()].reverse()) {
      const xa = tlX(M2V(c.start), W), xb = tlX(editView() ? c.start + c.dur : M2V(Math.min(state.c.duration, c.start + c.dur)), W);
      if (px >= xa - 4 && px <= xb + 4) return { c, edge: Math.abs(px - xa) < 7 ? 'a' : Math.abs(px - xb) < 7 ? 'b' : null };
    }
    return null;
  };
  cv.addEventListener('dblclick', e => { const h = hit(e); openMusicPicker(h ? h.c.id : null); });
  cv.addEventListener('contextmenu', e => { e.preventDefault(); const h = hit(e); if (h) { state.musicSel = h.c.id; drawMusicLane(); musicMenu(e, h.c); } });
  cv.addEventListener('mousemove', e => { if (e.buttons) return; const h = hit(e); cv.style.cursor = h ? (h.edge ? 'ew-resize' : 'grab') : (musicClips().length ? 'default' : 'pointer'); });
  cv.addEventListener('mousedown', e => {
    if (e.button !== 0) return;
    const h = hit(e);
    if (!h && !musicClips().length) return openMusicPicker();   // faixa vazia: um clique já abre a lista
    if (!h) {                                    // espaço vazio: move a agulha
      state.musicSel = null; tl.seg = null;
      $('#video').currentTime = V2S(vAt(e)); tick(true); drawTimeline();
      return;
    }
    const c = h.c, v0 = vAt(e), x0 = e.clientX;
    state.musicSel = c.id; tl.seg = null; tl.sel = null; selectItem('music', c.id);
    const maxLen = c.len || 1e9;
    // vizinhas: a música não pode passar por cima de outra (pode ter buraco entre elas)
    const others = musicClips().filter(o => o.id !== c.id);
    const prevEnd = Math.max(0, ...others.filter(o => o.start + o.dur <= c.start + 0.01).map(o => o.start + o.dur));
    const nextStart = Math.min(1e9, ...others.filter(o => o.start >= c.start + c.dur - 0.01).map(o => o.start));
    let moved = false;
    const move = ev => {
      if (!moved && Math.abs(ev.clientX - x0) < 3) return;
      moved = true;
      const d = V2M(vAt(ev)) - V2M(v0);
      let nc = { id: c.id, start: c.start, in: c.in || 0, dur: c.dur };
      if (h.edge === 'a') {                    // aparar o começo: a música começa mais adiante (ou volta)
        const dd = Math.max(-Math.min(c.start - prevEnd, c.in || 0), Math.min(c.dur - 0.5, d));
        nc = { ...nc, start: c.start + dd, in: (c.in || 0) + dd, dur: c.dur - dd };
      } else if (h.edge === 'b') {             // aparar/esticar o fim (até o fim da música ou a próxima)
        nc.dur = Math.max(0.5, Math.min(maxLen - (c.in || 0), nextStart - c.start, c.dur + d));
      } else {                                 // mover entre as vizinhas
        nc.start = Math.max(prevEnd, Math.min(nextStart - c.dur, c.start + d));
      }
      tl.dragMusic = nc;
      drawMusicLane(); drawMusicHead(S2V($('#video').currentTime));
    };
    const up = () => {
      removeEventListener('mousemove', move); removeEventListener('mouseup', up);
      const nc = tl.dragMusic; tl.dragMusic = null;
      if (moved && nc) editMusic(c.id, { start: +nc.start.toFixed(2), in: +nc.in.toFixed(2), dur: +nc.dur.toFixed(2) });
      else drawTimeline();
    };
    addEventListener('mousemove', move); addEventListener('mouseup', up);
  });
  $('#tl-add-music').onclick = () => openMusicPicker();
  $('#tl-add-gs').onclick = addCornerAtHead;
}

// prévia: a música toca junto, em 1x (mesmo com o vídeo acelerado), no ponto certo
function syncMusic(out, playing) {
  const sp = +state.c.settings.speed || 1;
  const live = new Set();
  for (const c of musicClips()) {
    const inside = out >= c.start && out < c.start + c.dur;
    let el = musicEls[c.id];
    if (!inside || !playing) { if (el && !el.paused) el.pause(); continue; }
    live.add(c.id);
    if (!el) { el = musicEls[c.id] = new Audio(musicSrc(c)); el.preload = 'auto'; }
    const want = (out - c.start) / sp + (c.in || 0);
    const fadeIn = Math.min(1, (out - c.start) / sp / 0.6), fadeOut = Math.min(1, (c.start + c.dur - out) / sp / (c.fade || 1));
    el.volume = Math.max(0, Math.min(1, (c.vol ?? 0.18) * 1.6 * Math.min(fadeIn, fadeOut)));
    if (el.paused) { el.currentTime = want; el.play().catch(() => {}); }
    else if (Math.abs(el.currentTime - want) > 0.3) el.currentTime = want;
  }
  for (const id in musicEls) if (!live.has(id) && !musicEls[id].paused) musicEls[id].pause();
}

// ------------------------------------------------------------------ efeitos sonoros (seletor)
function openSfxPicker(o, w0) {
  const lib = state.status.sfx;
  const cats = [...new Set(lib.map(s => s.cat))];
  const isNew = !o;
  if (isNew) o = { sfx: null };
  const body = dialog(`<h3>${isNew ? 'Acrescentar som em “' + esc(state.p.words[w0]?.w || '') + '”' : 'Efeito sonoro'}</h3><p class="hint">Clique no ▶ para ouvir · clique no nome para usar.
      Sons livres para uso comercial (Mixkit / Freesound CC0). Para usar os seus, coloque arquivos na pasta <code>sfx/</code>.</p>
    <div class="sfx-grid">${cats.map(c => `<div class="sfx-cat"><h4>${esc(c)}</h4><div class="opts">${lib.filter(s => s.cat === c).map(s =>
      `<div class="sfx-opt ${s.name === o.sfx ? 'on' : ''}" data-n="${esc(s.name)}" title="${esc(s.desc)}"><span class="pl" data-play="${esc(s.name)}">▶</span>${esc(s.desc.split(' — ')[0])}</div>`).join('')}</div></div>`).join('')}</div>
    ${isNew ? '' : '<div class="row" style="margin-top:12px"><button class="tool" id="sfx-remove">Remover este som</button></div>'}`);
  body.addEventListener('click', e => {
    const pl = e.target.closest('[data-play]');
    if (pl) { e.stopPropagation(); return playSfx(pl.dataset.play); }
    const opt = e.target.closest('[data-n]');
    if (!opt) return;
    if (isNew) { o.id = uid(); patch({ overlays: [...state.p.overlays, { id: o.id, type: 'sfx', sfx: opt.dataset.n, w0, w1: w0 }] }); toast('Som acrescentado'); }
    else editOverlay(o.id, { sfx: opt.dataset.n });
    playSfx(opt.dataset.n); $('#dialog').classList.add('hidden');
  });
  if (!isNew) $('#sfx-remove', body).onclick = () => { removeOverlay(o.id); $('#dialog').classList.add('hidden'); };
}

// ------------------------------------------------------------------ trilha de trechos (estilo CapCut)
let seqKnown = new Set();
function renderSeqbar() {
  const bar = $('#seqbar');
  if (!bar || !state.c) return;
  const cuts = state.c.cuts, js = joins();
  const W = state.p.words, del = new Set(state.p.deleted);
  const key = s => s.start.toFixed(2);
  bar.innerHTML = cuts.map((s, k) => {
    const words = W.filter(w => !del.has(w.i) && w.w && w.start >= s.start - 0.05 && w.end <= s.end + 0.05).slice(0, 4).map(w => w.w).join(' ');
    const j = js.find(x => x.k === k);
    const chip = k ? `<button class="sq-join ${j?.tr ? 'on' : ''}" data-j="${k}" title="${j?.tr ? 'Transição: ' + esc(trName(j.tr.type === 'flash' ? 'branco' : j.tr.style)) : 'Corte seco — clique para pôr uma transição'}">◆</button>` : '';
    const born = seqKnown.size && !seqKnown.has(key(s)) ? ' born' : '';
    return chip + `<div class="sq-clip${born}" data-k="${k}" style="flex-grow:${(s.end - s.start).toFixed(2)}" title="Trecho ${k + 1} · ${(s.end - s.start).toFixed(1)}s — arraste para mudar a ordem">
      <b>${k + 1}</b><span>${esc(words)}</span></div>`;
  }).join('');
  seqKnown = new Set(cuts.map(key));
  $('#seq-reset').classList.toggle('hidden', !(state.p.order || []).length);
}

function setupSeqbar() {
  const bar = $('#seqbar');
  bar.addEventListener('click', e => {
    const jb = e.target.closest('[data-j]');
    if (jb) { const j = joins().find(x => x.k === +jb.dataset.j); if (j) openTransitionPicker(j); }
  });
  bar.addEventListener('contextmenu', e => {
    const clip = e.target.closest('.sq-clip'); if (!clip) return;
    e.preventDefault();
    const sg = state.c.cuts[+clip.dataset.k];
    tl.seg = [sg.start, sg.end]; drawTimeline();
    clipMenu(e, sg);
  });
  bar.addEventListener('pointerdown', e => {
    const clip = e.target.closest('.sq-clip');
    if (!clip || e.button !== 0) return;
    const k = +clip.dataset.k, x0 = e.clientX;
    const clips = $$('.sq-clip', bar);
    let dragging = false, target = k;
    const mark = document.createElement('div'); mark.className = 'sq-drop';
    const move = ev => {
      const dx = ev.clientX - x0;
      if (!dragging && Math.abs(dx) < 6) return;
      if (!dragging) { dragging = true; clip.classList.add('dragging'); bar.appendChild(mark); }
      clip.style.transform = `translateX(${dx}px)`;
      // posição de soltura = entre quais blocos o ponteiro está
      target = clips.filter(c => c !== clip).reduce((n, c) => { const r = c.getBoundingClientRect(); return ev.clientX > r.left + r.width / 2 ? n + 1 : n; }, 0);
      const others = clips.filter(c => c !== clip), br = bar.getBoundingClientRect();
      const ref = others[target] ? others[target].getBoundingClientRect().left : others.at(-1).getBoundingClientRect().right + 2;
      mark.style.left = (ref - br.left + bar.scrollLeft - 2) + 'px';
    };
    const up = () => {
      removeEventListener('pointermove', move); removeEventListener('pointerup', up);
      mark.remove();
      if (!dragging) {                     // clique: seleciona o trecho na timeline e vai para ele
        const s = state.c.cuts[k];
        tl.seg = [s.start, s.end];
        $('#video').currentTime = s.start; tick(true); drawTimeline();
        return;
      }
      clip.classList.remove('dragging'); clip.style.transform = '';
      if (target === k) return;
      const arr = [...state.c.cuts];
      const [mv] = arr.splice(k, 1);
      arr.splice(target, 0, mv);
      patch({ order: arr.map(s => +((s.start + s.end) / 2).toFixed(3)) });
      toast(`Trecho ${k + 1} movido para a posição ${target + 1}`);
    };
    addEventListener('pointermove', move); addEventListener('pointerup', up);
  });
  $('#seq-reset').onclick = () => { patch({ order: [] }); toast('Ordem original'); };
  // trilha de trechos (texto de cada pedaço): recolhida por padrão, abre no botão
  const setSeq = open => {
    $('.seq-wrap').classList.toggle('collapsed', !open);
    $('#seq-toggle').textContent = open ? '▾ Trechos' : '▸ Trechos';
    try { localStorage.setItem('seqOpen', open ? '1' : '0'); } catch {}
  };
  let seqOpen = false;
  try { seqOpen = localStorage.getItem('seqOpen') === '1'; } catch {}
  setSeq(seqOpen);
  $('#seq-toggle').onclick = () => setSeq($('.seq-wrap').classList.contains('collapsed'));
  $('#tl-add-sfx').onclick = () => openSfxPicker(null, wordAtHead());
  $('#tl-add-tr').onclick = () => {
    const js = joins();
    if (!js.length) return toast('Ainda não há cortes entre trechos', true);
    const t = $('#video').currentTime;
    openTransitionPicker(js.reduce((a, b) => Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a));
  };
}

// ------------------------------------------------------------------ sons na timeline
// faixa de cima da timeline (estilo CapCut, acima do vídeo principal): blocos arrastáveis
const LANE_TYPES = {
  greenscreen: { color: 'rgba(62,207,142,.85)', ink: '#06241a', label: () => '🟩 você no canto' },
  media: { color: 'rgba(240,145,107,.9)', ink: '#2a1208', label: o => '▣ ' + (o.file || o.desc || 'B-roll').replace(/^[a-z0-9]{2,6}_/, '').replace(/\.[^.]+$/, '') },
  motion: { color: 'rgba(176,160,255,.9)', ink: '#1b1438', label: o => '✦ ' + (o.params?.icon || o.template || 'animação') },
};
const sfxT = o => (state.p.words[o.w0]?.start ?? 0) + (+o.offset || 0);       // momento do som (no original)
const sfxLead = name => +(state.status?.sfx?.find(x => x.name === name)?.lead || 0);
function moveSfx(o, t) {
  // ancora na palavra que está tocando naquele instante e guarda o ajuste fino (s) em `offset`
  const W = state.p.words, del = new Set(state.p.deleted);
  let w0 = -1;
  for (let i = 0; i < W.length; i++) if (!del.has(W[i].i) && W[i].w && W[i].start <= t + 0.001) w0 = i;
  if (w0 < 0) w0 = W.findIndex(w => !del.has(w.i) && w.w);
  const offset = +(t - W[w0].start).toFixed(3);
  patch({ overlays: state.p.overlays.map(x => x.id === o.id ? { ...x, w0, w1: w0, offset, auto: false } : x) });
  toast(`Som movido para ${fmt(t)}${sfxLead(o.sfx) > 0.3 ? ' (é onde ele termina de subir)' : ''}`);
}

// ------------------------------------------------------------------ transições entre trechos
const TR_STYLES = [
  { id: '', name: 'Nenhuma', desc: 'corte seco' },
  { id: 'leak', name: 'Luz', desc: 'film burn quente → creme (da referência)' },
  { id: 'branco', name: 'Branco', desc: 'mergulho rápido no creme' },
  { id: 'escuro', name: 'Escuro', desc: 'mergulho rápido no ônix' },
  { id: 'desfoque', name: 'Desfoque', desc: 'desfoca e volta' },
];
const trName = st => TR_STYLES.find(x => x.id === st)?.name || st;

function wordAtTime(t) {
  const W = state.p.words, del = new Set(state.p.deleted);
  const i = W.findIndex(w => w.end > t && !del.has(w.i));
  return i < 0 ? W.length - 1 : i;
}
// junções que aceitam transição: cortes reais e o corte do hook (calculadas no servidor)
function joins() {
  if (!state.c) return [];
  const W = state.p.words, cuts = state.c.cuts;
  return (state.c.joins || []).map(j => {
    const tr = state.p.overlays.find(o => (o.type === 'transition' || o.type === 'flash') && W[o.w0] &&
      Math.abs(W[o.w0].start - j.t) < 0.8 && W[o.w0].start - j.t > -0.8);
    const k = cuts.findIndex(c => Math.abs(c.start - j.t) < 0.01);
    return { k: k > 0 ? k : null, t: j.t, out: j.out, kind: j.kind, w0: j.w, tr };
  });
}

function outToSrc(out) {
  const segs = state.c.segments;
  if (!segs.length) return 0;
  for (const p of segs) if (out >= p.out && out < p.out + (p.end - p.start)) return p.start + (out - p.out);
  if (out <= 0) return segs[0].start;
  const last = segs[segs.length - 1];                     // depois do fim: fim do último pedaço
  return last.end - 0.001;
}

function setJoinTransition(j, style) {
  let ovs = state.p.overlays.filter(o => o !== j.tr && !(j.tr && o.id === j.tr.id));
  if (style) ovs = [...ovs, { id: uid(), type: 'transition', style, w0: j.w0, w1: j.w0 }];
  return ovs;
}

function previewJoin(j) {
  const v = $('#video');
  v.currentTime = outToSrc(Math.max(0, j.out - 0.8));
  v.play().catch(() => {});
}

function openTransitionPicker(j) {
  const cur = j.tr ? (j.tr.type === 'flash' ? 'branco' : j.tr.style) : '';
  const body = dialog(`<h3>Transição neste corte</h3>
    <p class="hint">${j.kind === 'hook' ? 'Corte do fim do hook' : `Entre o trecho ${j.k} e o ${j.k + 1}`} · a prévia toca sozinha ao escolher.</p>
    <div class="tr-grid">${TR_STYLES.map(x => `<button class="tr-opt ${x.id === cur ? 'on' : ''}" data-st="${x.id}">
      <span class="tr-sw tr-${x.id || 'none'}"></span><b>${x.name}</b><small>${x.desc}</small></button>`).join('')}</div>
    <div class="row" style="margin-top:14px"><button class="tool" id="tr-all">Usar a escolhida em TODOS os cortes</button></div>`);
  let chosen = cur;
  body.addEventListener('click', async e => {
    const b = e.target.closest('[data-st]');
    if (!b) return;
    chosen = b.dataset.st;
    $$('.tr-opt', body).forEach(x => x.classList.toggle('on', x === b));
    await patch({ overlays: setJoinTransition(j, chosen) });
    const nj = joins().find(x => Math.abs(x.t - j.t) < 0.01);
    if (nj) { Object.assign(j, nj); previewJoin(nj); }
  });
  $('#tr-all', body).onclick = async () => {
    let ovs = state.p.overlays;
    for (const jj of joins()) {
      ovs = ovs.filter(o => !(jj.tr && o.id === jj.tr.id));
      if (chosen) ovs = [...ovs, { id: uid(), type: 'transition', style: chosen, w0: jj.w0, w1: jj.w0 }];
    }
    await patch({ overlays: ovs });
    $('#dialog').classList.add('hidden');
    toast(chosen ? `${trName(chosen)} em todos os ${joins().length} cortes` : 'Todas as transições removidas');
  };
}

// ------------------------------------------------------------------ fundo (cenário)
let bgList = null;
async function renderScenes() {
  const box = $('#bg-scenes');
  if (!box || !state.p) return;
  if (!bgList) { try { bgList = await api('/api/backgrounds'); } catch { bgList = []; } }
  const cur = state.p.settings.bg_scene || 'none';
  const card = (id, name, desc, img) => `<button class="bg-card${cur === id ? ' on' : ''}" data-scene="${esc(id)}" title="${esc(desc)}">
    ${img ? `<img src="${esc(img)}" loading="lazy" alt="">` : `<span class="bg-ph">${id === 'none' ? '◻' : '＋'}</span>`}<b>${esc(name)}</b></button>`;
  const html = card('none', 'Original', 'O fundo como foi gravado') +
    bgList.map(b => card(b.slug, b.name, b.desc, b.thumb)).join('') +
    (cur.startsWith('file:') ? card(cur, 'Sua imagem', cur.slice(5), assetUrl(cur.slice(5))) : '') +
    card('upload', 'Usar imagem minha', 'Uma foto sua do ambiente (de preferência vertical)', null);
  if (box._h !== html) { box.innerHTML = html; box._h = html; }
}

// carregando EM CIMA do vídeo: bolinha girando + porcentagem + o que está acontecendo
function showBusy(on, title, pct, msg) {
  const el = $('#busy');
  el.classList.toggle('hidden', !on);
  if (!on) return;
  if (title) $('#busy-title').textContent = title;
  const p = Math.max(0, Math.min(1, pct || 0));
  $('#busy-pct').textContent = Math.round(p * 100) + '%';
  $('#busy-arc').style.strokeDashoffset = (119.4 * (1 - p)).toFixed(1);
  $('#busy-msg').textContent = (msg || '').replace(/\s*\d+%$/, '');
}

async function followJob(jobId, title, done) {
  showBusy(true, title, 0, '');
  try {
    await waitJob(jobId, j => showBusy(true, null, j.progress, j.message));
    const p = await api(`/api/projects/${state.p.id}`);
    applyServer(p);
    done && done(p);
  } catch (e) { toast(e.message, true, 9000); }
  finally { showBusy(false); }
}
// recorta você do fundo (uma vez por vídeo) — a tela verde aparece recortada já na prévia
async function ensureCutout() {
  if (state.p.cutout) return;
  try {
    const job = await api(`/api/projects/${state.p.id}/cutout`, { method: 'POST' });
    await followJob(job.id, 'Recortando você do fundo…', () => toast('✓ Recorte pronto: a prévia já mostra você recortado no canto'));
  } catch (e) { toast(e.message, true); }
}

async function followBgJob(jobId, scene) {
  const st = $('#bg-status');
  state.bgBusy = true; $('#bg-scenes').classList.add('locked');
  const first = !state.p.bg_ready;
  showBusy(true, scene === 'none' ? 'Voltando ao fundo original…' : 'Trocando o fundo…', 0, '');
  try {
    await waitJob(jobId, j => {
      showBusy(true, null, j.progress, j.message);
      st.textContent = j.message ? '⏳ ' + j.message : '';
    });
    // terminou: mostra o fundo novo SOZINHO (sem precisar clicar de novo)
    const v = $('#video'), t = v.currentTime;
    const p = await api(`/api/projects/${state.p.id}`);
    applyServer(p);
    v.src = mediaUrl(p.preview || p.source.file) + `?t=${Date.now()}`;
    v.addEventListener('loadedmetadata', () => { v.currentTime = t; tick(true); }, { once: true });
    st.textContent = (p.settings.bg_scene || 'none') === 'none' ? 'Fundo original.' : '✓ Cenário aplicado.';
  } catch (e) { st.textContent = ''; toast(e.message, true, 9000); }
  finally { state.bgBusy = false; $('#bg-scenes').classList.remove('locked'); showBusy(false); }
}

async function setScene(scene) {
  if (state.bgBusy) {                     // já processando: só troca a escolha (o mesmo processamento usa ela)
    await api(`/api/projects/${state.p.id}/background`, { method: 'POST', json: { scene } });
    state.p.settings.bg_scene = scene; renderScenes();
    return;
  }
  if (scene === 'none') {                 // voltar ao original é instantâneo
    await api(`/api/projects/${state.p.id}/background`, { method: 'POST', json: { scene } });
    const p = await api(`/api/projects/${state.p.id}`);
    const v = $('#video'), t = v.currentTime;
    applyServer(p);
    v.src = mediaUrl(p.preview || p.source.file) + `?t=${Date.now()}`;
    v.addEventListener('loadedmetadata', () => { v.currentTime = t; tick(true); }, { once: true });
    $('#bg-status').textContent = 'Fundo original.';
    return;
  }
  try {
    const job = await api(`/api/projects/${state.p.id}/background`, { method: 'POST', json: { scene } });
    state.p.settings.bg_scene = scene; renderScenes();
    await followBgJob(job.id, scene);
  } catch (e) { toast(e.message, true, 9000); }
}

// ------------------------------------------------------------------ biblioteca: sons e transições
const TRANSITIONS = [
  { type: 'transition', style: 'leak', name: 'Luz (film burn)', desc: 'luz quente invade, estoura para creme e a cena volta — da referência' },
  { type: 'flash', name: 'Flash branco', desc: 'piscada branca rápida (a identidade Kronos evita)' },
];

function renderLibrary() {
  const s = state.c.settings, lib = state.status.sfx || [];
  const hs = $('#set-hook-sfx');
  hs.innerHTML = '<option value="none">Nenhum</option>' + lib.map(x =>
    `<option value="${esc(x.name)}">${esc(x.cat)} · ${esc(x.desc.split(' — ')[0])}</option>`).join('');
  hs.value = s.hook_sfx || 'reverse_expectativa';
  $('#set-hook-tr').value = s.hook_transition || 'leak';
  $('#lib-tr').innerHTML = TRANSITIONS.map((t, k) => `<div class="lib-item"><span class="lib-ic">${t.style ? '☀' : '✺'}</span>
    <div class="lib-txt"><b>${esc(t.name)}</b><span class="muted">${esc(t.desc)}</span></div>
    <button class="act" data-tr="${k}" title="Inserir onde a agulha está">＋</button></div>`).join('') +
    `<p class="hint">Entre todos os cortes (corte seco, zoom, fade): aba Estilo.</p>`;
  const cats = [...new Set(lib.map(x => x.cat))];
  $('#lib-sfx').innerHTML = cats.map(c => `<h4>${esc(c)}</h4>` + lib.filter(x => x.cat === c).map(x => {
    const [name, ...rest] = x.desc.split(' — ');
    return `<div class="lib-item"><button class="act pl" data-play="${esc(x.name)}" title="Ouvir">▶</button>
      <div class="lib-txt"><b>${esc(name)}</b>${rest.length ? `<span class="muted">${esc(rest.join(' — '))}</span>` : ''}</div>
      <button class="act" data-add="${esc(x.name)}" title="Inserir onde a agulha está">＋</button></div>`;
  }).join('')).join('');
}

function setupLibrary() {
  $('#tab-sons').addEventListener('click', e => {
    const pl = e.target.closest('[data-play]');
    if (pl) return playSfx(pl.dataset.play);
    const add = e.target.closest('[data-add]');
    if (add) { const w = wordAtHead(); playSfx(add.dataset.add); return addOverlay({ type: 'sfx', sfx: add.dataset.add, w0: w, w1: w }); }
    const tr = e.target.closest('[data-tr]');
    if (tr) {
      const t = TRANSITIONS[+tr.dataset.tr], w = wordAtHead();
      return addOverlay(t.style ? { type: 'transition', style: t.style, w0: w, w1: w } : { type: 'flash', w0: w, w1: w });
    }
  });
  $('#play-hook-sfx').onclick = e => { e.preventDefault(); const v = $('#set-hook-sfx').value; if (v !== 'none') playSfx(v); };
  // muda a escolha e já troca no vídeo aberto (o que o plano automático colocou no pós-hook)
  $('#set-hook-sfx').onchange = e => {
    const v = e.target.value;
    if (v !== 'none') playSfx(v);
    const ovs = state.p.overlays.filter(o => !(o.type === 'sfx' && o.reason === 'expectativa pós-hook' && v === 'none'))
      .map(o => o.type === 'sfx' && o.reason === 'expectativa pós-hook' ? { ...o, sfx: v } : o);
    patch({ settings: { hook_sfx: v }, overlays: ovs });
  };
  $('#set-hook-tr').onchange = e => {
    const v = e.target.value;
    const ovs = state.p.overlays.filter(o => !(o.type === 'transition' && o.reason === 'pós-hook' && v === 'none'));
    patch({ settings: { hook_transition: v }, overlays: ovs });
  };
}

// ------------------------------------------------------------------ cor automática na prévia
async function updateGradePreview() {
  // Prévia de cor só com filtros CSS (acelerados pela placa de vídeo). Filtros SVG sobre o vídeo
  // pesavam tanto (principalmente com zoom) que travavam a reprodução. A cor exata sai na exportação.
  const s = state.c.settings;
  $('#grade-svg')?.remove();
  state.gradeCss = '';
  if (s.grade === 'auto') {
    try {
      const g = await api(`/api/projects/${state.p.id}/grade`);
      if (g.gains) {
        const stretch = 1 / Math.max(0.5, g.white - g.black);
        const bright = 1 + (g.gamma - 1) * 0.45 + g.black * 0.5;
        const contrast = (g.contrast || 1) * (1 + (stretch - 1) * 0.6);
        const warm = Math.max(0, g.gains[0] - g.gains[2]);   // ganho maior no vermelho = aquecer
        state.gradeCss = `brightness(${bright.toFixed(3)}) contrast(${contrast.toFixed(3)}) saturate(${g.saturation})` +
          (warm > 0.01 ? ` sepia(${Math.min(0.2, warm * 1.5).toFixed(3)})` : '');
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
      <div class="exp-actions"><a class="exp-download" href="${j.result.url}" download="${esc(j.result.file)}">⬇ Baixar MP4</a>
      ${j.result.credits ? `<a class="exp-credits" href="${j.result.credits}" target="_blank">ver créditos dos materiais</a>` : ''}</div>`;
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
  const help = () => dialog(`<h3>Como funciona</h3><div class="help-list">
    <h4>Timeline</h4>
    <div><b>Arrastar</b> (ou pegar a alça branca no topo) move a agulha.</div>
    <div><b>Clique num trecho verde</b> seleciona; arraste as <b>alças brancas</b> das bordas para estender/encurtar. <kbd>Delete</kbd> corta o trecho.</div>
    <div><kbd>shift</kbd> + arrastar seleciona um intervalo · <kbd>X</kbd> corta · <kbd>R</kbd> restaura · <kbd>I</kbd>/<kbd>O</kbd> marcam início/fim.</div>
    <div><b>Rolar o mouse</b> = zoom no cursor · <kbd>shift</kbd> + rolar = andar · <kbd>V</kbd> liga/desliga “Ver cortes”.</div>
    <h4>Texto e legenda</h4>
    <div>Na transcrição: clique numa palavra para ir até ela · <b>clique duplo</b> (ou ligue <b>✎ Editar texto</b> e dê um clique) para corrigir.</div>
    <div>No vídeo pausado: <b>clique numa palavra da legenda</b> e corrija ali mesmo. <kbd>Enter</kbd> salva, <kbd>Esc</kbd> cancela.</div>
    <div>Selecione palavras na transcrição para cortar, transformar em <b>★ destaque</b> etc. Palavras com sublinhado ondulado = a transcrição ficou em dúvida.</div>
    <h4>Geral</h4>
    <div><kbd>espaço</kbd> toca/pausa · <kbd>⌘Z</kbd> desfaz · ⛶ amplia o vídeo · » recolhe o painel.</div></div>`);
  $('#help-btn').onclick = help;
  $$('[data-help]').forEach(b => b.onclick = help);
  $('#edit-mode').onclick = () => {
    state.editMode = !state.editMode;
    $('#edit-mode').classList.toggle('on', state.editMode);
    $('#transcript').classList.toggle('editing', state.editMode);
    toast(state.editMode ? 'Modo edição: clique numa palavra para corrigir' : 'Modo edição desligado');
  };
  $('#fullscreen').onclick = () => {
    const st = $('.stage');
    if (document.fullscreenElement) document.exitFullscreen(); else st.requestFullscreen?.();
  };
  document.addEventListener('fullscreenchange', () => {
    for (const ms of [0, 80, 250]) setTimeout(() => { layoutFrame(); drawTimeline(); tick(true); }, ms);
  });
  const setSide = collapsed => {
    document.body.classList.toggle('side-collapsed', collapsed);
    $('#side-open').classList.toggle('hidden', !collapsed);
    try { localStorage.setItem('sideCollapsed', collapsed ? '1' : ''); } catch {}
    setTimeout(() => { layoutFrame(); drawTimeline(); }, 30);
  };
  $('#side-close').onclick = () => setSide(true);
  $('#side-open').onclick = () => setSide(false);
  // atalho: abre o painel na aba Estilo, direto na seção de fundo
  $('#open-bg').onclick = () => {
    setSide(false);
    document.querySelector('.tabs [data-tab="estilo"]').click();
    setTimeout(() => { const el = $('#bg-scenes'); el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('flash-hint'); setTimeout(() => el.classList.remove('flash-hint'), 1400); }, 120);
  };
  try { if (localStorage.getItem('sideCollapsed')) setSide(true); } catch {}
  $('#vocab').onchange = async e => { await api('/api/vocab', { method: 'PUT', json: { text: e.target.value } }); toast('Vocabulário salvo'); };
  $('#go-formatos').onclick = loadFormatos;
  setupRefs();
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
  $('#show-cuts').onclick = toggleShowCuts;
  $('#frame').addEventListener('click', togglePlay);
  $('#undo').onclick = undo;
  $('#redo').onclick = redo;
  $('#export').onclick = exportVideo;
  $('#modal-close').onclick = () => { $('#modal').classList.add('hidden'); $('#exp-result').innerHTML = ''; };
  $('#pname').onchange = e => patch({ name: e.target.value }, false);
  $$('.tabs button[data-tab]').forEach(b => b.onclick = () => {
    $$('.tabs button[data-tab]').forEach(x => x.classList.toggle('on', x === b));
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
  // Enter num campo de texto do painel (cartões, notas) confirma e fecha a edição, como no resto do editor
  document.addEventListener('keydown', e => {
    const el = e.target;
    if (e.key === 'Enter' && el.matches?.('input[type="text"], input:not([type]), select') && !el.classList.contains('w-edit') &&
        el.closest('.side, #refs')) {
      e.preventDefault();
      if (el.closest('.rf-form')) $('#ref-add').click(); else el.blur();
    }
  });
  setupLibrary();
  $('#bg-scenes').addEventListener('click', e => {
    const b = e.target.closest('[data-scene]'); if (!b) return;
    if (b.dataset.scene === 'upload') return pickAsset(file => setScene('file:' + file), 'image/*');
    setScene(b.dataset.scene);
  });
  setupSeqbar();
  $('#my-files').onclick = e => {
    const b = e.target.closest('[data-file]'); if (!b) return;
    const file = b.dataset.file, isImg = !isVideo(file);
    document.querySelector('.ctx-menu')?.remove();
    const m = document.createElement('div');
    m.className = 'ctx-menu';
    m.innerHTML = `<button data-a="card">▣ Mostrar na agulha (card)</button>
      ${isImg ? '<button data-a="gs">🟩 Tela verde — eu no canto lendo isto</button>' : ''}
      <button data-a="cancel">Cancelar</button>`;
    document.body.appendChild(m);
    placeMenu(m, e.clientX, e.clientY);
    const close = () => { m.remove(); removeEventListener('mousedown', outside, true); };
    const outside = e2 => { if (!m.contains(e2.target)) close(); };
    setTimeout(() => addEventListener('mousedown', outside, true), 0);
    m.onclick = e2 => {
      const a = e2.target.closest('[data-a]')?.dataset.a; if (!a) return;
      close();
      if (a === 'card') insertFileAtHead(file);
      if (a === 'gs') addGreenscreen(file);
    };
  };
  $('#btn-add-file').onclick = () => pickAsset(() => { toast('Arquivo adicionado'); loadMyFiles(); });
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
    // atalhos com ⌘/Ctrl primeiro (senão "V" sozinho = ver cortes engoliria o ⌘V)
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'c') { if (!window.getSelection().toString()) { e.preventDefault(); copySelected(); } return; }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'v') { e.preventDefault(); pasteAtHead(); return; }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
    if (e.metaKey || e.ctrlKey) return;
    if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
    else if (state.sel && (e.key === 'x' || e.key === 'X')) { e.preventDefault(); setDeleted(state.sel, true); }
    else if ('sSbBxX'.includes(e.key) && !e.metaKey && !e.ctrlKey) { e.preventDefault(); splitAtHead(); }
    else if (e.key === 'r' || e.key === 'R') { e.preventDefault(); rangeEdit('keep'); }
    else if (e.key === 'v' || e.key === 'V') { e.preventDefault(); toggleShowCuts(); }
    else if (e.key === 'i' || e.key === 'I') { tl.markIn = $('#video').currentTime; tl.sel = null; drawTimeline(); toast('Início marcado — vá até o fim e aperte O'); }
    else if ((e.key === 'o' || e.key === 'O') && tl.markIn != null) { const t = $('#video').currentTime; tl.sel = [Math.min(tl.markIn, t), Math.max(tl.markIn, t)]; tl.markIn = null; drawTimeline(); }
    else if (e.key === '=' || e.key === '+') setZoom(tl.zoom * 1.6);
    else if (e.key === '-') setZoom(tl.zoom / 1.6);
    else if ((e.key === 'Delete' || e.key === 'Backspace') && state.sel) { e.preventDefault(); setDeleted(state.sel, true); }
    else if ((e.key === 'Delete' || e.key === 'Backspace') && (tl.sel || tl.seg || state.musicSel)) { e.preventDefault(); deleteSelected(); }
    else if ((e.key === 'Delete' || e.key === 'Backspace') && state.selItem?.kind === 'overlay') { e.preventDefault(); removeOverlay(state.selItem.id); state.selItem = null; }
    else if (e.key === 'Escape') { tl.seg = null; tl.sel = null; state.musicSel = null; document.querySelector('.ctx-menu')?.remove(); drawTimeline(); }
    else if (e.key === 'ArrowLeft') { $('#video').currentTime -= 2; }
    else if (e.key === 'ArrowRight') { $('#video').currentTime += 2; }
  });
  new ResizeObserver(() => { layoutFrame(); drawTimeline(); }).observe($('.stage-col'));
  loop();
}

function route() {
  const h = location.hash.slice(1);
  if (h === 'formatos') return loadStatus().then(loadFormatos);
  if (h === 'refs') return loadRefs();
  if (h && h !== state.p?.id) return openProject(h).catch(() => loadHome());
  if (!h) return loadHome();
}
setup();
window.addEventListener('hashchange', () => { $('#video').pause(); route(); });
route();
