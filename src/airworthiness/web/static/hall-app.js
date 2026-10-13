/* Same-origin ES modules; no build step or inline scripts required. */
import { main, state, mobile, reducedMotion, safeURL, renderRail, empty, link, errorBox } from './hall-core.js';
import { renderHome } from './hall-home.js';
import { renderReader, saveReadingPosition, scheduleSave, hashTarget } from './hall-reader.js';
import { renderQuality } from './hall-quality.js';

function clearReader() {
  saveReadingPosition();
  state.scrollReady = false;
  state.scrollKey = null;
  state.pane = null;
  state.observer?.disconnect();
  state.observer = null;
  for (const dispose of state.disposers) dispose();
  state.disposers = [];
}

async function route({ focus = false } = {}) {
  clearReader();
  state.controller?.abort();
  state.controller = new AbortController();
  const signal = state.controller.signal;
  const generation = ++state.generation;
  const chapterMatch = /^\/chapters\/(ch\d{2})\/?$/i.exec(location.pathname);
  const isHome = location.pathname === '/';
  const isQuality = /^\/quality\/?$/.test(location.pathname);
  const view = chapterMatch ? 'reader' : isQuality ? 'quality' : 'home';
  document.body.dataset.view = view;
  document.title = isQuality ? '收录质量 · 适航离线资源馆' : '适航离线资源馆';
  main.setAttribute('aria-busy', 'true');
  for (const anchor of document.querySelectorAll('[data-nav]')) {
    const active = isQuality ? 'quality' : chapterMatch || location.hash === '#chapters' ? 'chapters' : 'resources';
    if (anchor.dataset.nav === active) anchor.setAttribute('aria-current', 'page');
    else anchor.removeAttribute('aria-current');
  }
  if (state.overview) renderRail(state.overview);
  try {
    if (chapterMatch) await renderReader(chapterMatch[1].toLowerCase(), signal, generation);
    else if (isQuality) await renderQuality(signal, generation);
    else if (isHome) await renderHome(signal, generation);
    else main.replaceChildren(empty('页面不存在', '请从资源总览选择章节或资料。', link('返回资源总览', '/', { class: 'button' })));
    if (generation !== state.generation) return;
    if (!chapterMatch) {
      if (location.hash) hashTarget()?.scrollIntoView({ block: 'start' });
      else window.scrollTo(0, 0);
    }
    if (focus) (document.getElementById('reader-title') || hashTarget() || main).focus({ preventScroll: true });
  } catch (error) {
    if (generation === state.generation && !signal.aborted) main.replaceChildren(errorBox(error, () => route()));
  } finally {
    if (generation === state.generation) main.setAttribute('aria-busy', 'false');
  }
}

function navigate(path, { replace = false } = {}) {
  const url = safeURL(path);
  if (!url || url.origin !== location.origin) return;
  saveReadingPosition();
  if (replace) history.replaceState(null, '', url.href);
  else if (url.href !== location.href) history.pushState(null, '', url.href);
  route({ focus: true });
}

document.addEventListener('click', event => {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const anchor = event.target.closest('a');
  if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) return;
  if (anchor.dataset.tocTarget) {
    const target = document.getElementById(anchor.dataset.tocTarget);
    if (!target) return;
    event.preventDefault();
    main.querySelector('.document-view')?.showText?.();
    if (mobile.matches) main.querySelectorAll('.reader-sidebar, .glossary-sidebar').forEach(panel => { panel.open = false; });
    history.replaceState(null, '', `${location.pathname}${location.search}#${encodeURIComponent(target.id)}`);
    target.scrollIntoView({ block: 'start', behavior: reducedMotion.matches ? 'auto' : 'smooth' });
    target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
    return;
  }
  if (!anchor.hasAttribute('data-route')) return;
  const url = safeURL(anchor.href);
  if (!url || url.origin !== location.origin) return;
  event.preventDefault();
  navigate(url.pathname + url.search + url.hash);
});

if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
window.addEventListener('popstate', () => route({ focus: true }));
window.addEventListener('scroll', scheduleSave, { passive: true });
window.addEventListener('pagehide', saveReadingPosition);
document.addEventListener('visibilitychange', () => { if (document.hidden) saveReadingPosition(); });
state.route = route;
state.navigate = navigate;
route();
