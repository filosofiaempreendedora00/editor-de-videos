// Base comum dos templates de motion. Parâmetros chegam no #hash (JSON).
// O renderizador controla o tempo com window.__seek(t) — todas as animações são CSS.
(function () {
  let P = {};
  try { P = JSON.parse(decodeURIComponent(location.hash.slice(1)) || '{}'); } catch (e) {}
  window.P = P;
  const dur = Math.max(1, +P.dur || 3);
  document.documentElement.style.setProperty('--dur', dur + 's');
  document.documentElement.style.setProperty('--accent', P.color || '#ffd60a');
  document.documentElement.dataset.format = P.vertical ? 'vertical' : 'horizontal';
  window.__seek = (t) => {
    document.getAnimations().forEach(a => { a.pause(); a.currentTime = t * 1000; });
  };
  window.__ready = async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map(i => i.decode().catch(() => 0)));
    return true;
  };
  window.esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
})();
