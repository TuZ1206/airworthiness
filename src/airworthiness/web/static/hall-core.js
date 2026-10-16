/* Shared API client, safe DOM primitives and navigation callbacks. */
import { prefixPath, unprefixPath, staticRequest } from './hall-static.js';
const staticMode = document.querySelector('meta[name="airworthiness-mode"]')?.content === 'static';
const basePath = staticMode ? document.querySelector('meta[name="airworthiness-base"]')?.content || '' : '';
const sitePath = path => prefixPath(path, basePath, staticMode);
const routePath = path => unprefixPath(path, basePath);
const main = document.getElementById('main');
const rail = document.getElementById('chapter-rail');
const announcer = document.getElementById('announcer');
const mobile = window.matchMedia('(max-width: 1023px)');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const kinds = {
  fulltext: '网页正文',
  extracted: '提取正文（待校对）',
  excerpt: '整理摘录',
  metadata: '状态信息'
};
const statuses = { effective: '登记有效', abolished: '已废止', unknown: '效力未确认' };
const state = {
  generation: 0,
  controller: null,
  overview: null,
  chapters: new Map(),
  documents: new Map(),
  pane: null,
  scrollKey: null,
  scrollReady: false,
  observer: null,
  disposers: []
};

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (name === 'class') node.className = value;
    else if (name.startsWith('on') && typeof value === 'function') node.addEventListener(name.slice(2), value);
    else if (name === 'value') node.value = value;
    else if (name === 'checked' || name === 'disabled' || name === 'hidden' || name === 'open') node[name] = Boolean(value);
    else node.setAttribute(name, String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child !== undefined && child !== null && child !== false) {
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
  }
  return node;
}

const list = value => Array.isArray(value) ? value : [];
const number = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value))
  ? Math.max(0, Math.trunc(Number(value))) : null;
const count = value => number(value) === null ? '—' : number(value).toLocaleString('zh-CN');
const chapterNumber = id => String(id || '').replace(/^ch/i, '').padStart(2, '0');
const query = () => new URLSearchParams(location.search).get('q')?.trim().slice(0, 200) || '';
const reviewLabel = value => value === 'approved' || value === 'reviewed' ? '已专业审核' : '待专业审核';

function sourceChapter(sourceId, fallback = '') {
  const match = /^CH(\d{2})-/i.exec(String(sourceId || ''));
  return match ? `ch${match[1]}` : fallback;
}

function chapterURL(id, sourceId = '', q = query()) {
  const url = new URL(sitePath(`/chapters/${encodeURIComponent(id)}`), location.origin);
  if (sourceId) url.searchParams.set('source', sourceId);
  if (q) url.searchParams.set('q', q);
  return url.pathname + url.search;
}

function resourceURL(resource, q = query()) {
  return chapterURL(resource.chapter_id || sourceChapter(resource.source_id), resource.source_id, q);
}

function link(text, href, attrs = {}) {
  return el('a', { href: sitePath(href), 'data-route': '', ...attrs }, text);
}

function safeURL(value, base = location.href) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const url = new URL(value, base);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url : null;
  } catch { return null; }
}

function officialLink(value, text = '官方来源 ↗') {
  // A source link must be an explicit web URL, not an interpreted local path.
  if (typeof value !== 'string' || !/^https?:\/\//i.test(value.trim())) return null;
  const url = safeURL(value);
  return url ? el('a', { href: url.href, target: '_blank', rel: 'noopener noreferrer', class: 'official-link' }, text) : null;
}

function badge(kind) {
  const recognized = Object.hasOwn(kinds, kind);
  return el('span', { class: `badge badge-${recognized ? kind : 'metadata'}` }, kinds[kind] || '收录类型未注明');
}

function sectionHeading(title, detail) {
  return el('div', { class: 'section-heading' }, el('h2', {}, title), detail ? el('small', {}, detail) : null);
}

function loading(text = '正在读取资料…', inline = false) {
  return el('div', { class: `state-box${inline ? ' inline-state' : ''}`, role: 'status' },
    el('span', { class: 'loading-indicator', 'aria-hidden': 'true' }), el('p', {}, text));
}

function empty(title, description, action) {
  return el('div', { class: 'state-box' }, el('h3', {}, title), el('p', {}, description), action);
}

function errorBox(error, retry, inline = false) {
  return el('div', { class: `state-box${inline ? ' inline-state' : ''}`, role: 'alert' },
    el('h3', {}, error.status === 400 ? '检索条件有误' : error.status === 404 ? '未找到这份资料' : '暂时无法读取资料'),
    el('p', {}, error.status === 404 ? '此地址对应的资料尚未收录，或标识已变更。可以返回资源总览继续查找。' :
      error.status === 400 ? error.userMessage || '请清除筛选条件后重新检索。' :
      staticMode ? '在线资料下载失败或超时，请检查网络后重试。首次全文搜索需要下载检索索引。' :
      error.name === 'TimeoutError' ? '本地服务响应超时，请稍后重试。' : '请确认本地服务正在运行，然后重试。'),
    error.status === 400 ? link('清除筛选', '/#resources', { class: 'button' }) : el('button', { class: 'button', type: 'button', onclick: retry }, '重新加载'));
}

async function api(path, signal) {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  if (signal.aborted) controller.abort();
  else signal.addEventListener('abort', abort, { once: true });
  const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, staticMode ? 90000 : 20000);
  try {
    if (staticMode) return await staticRequest(path, basePath, controller.signal);
    const response = await fetch(path, { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}`);
      error.status = response.status;
      if (response.status === 400) {
        const detail = await response.json().catch(() => ({}));
        if (typeof detail.error === 'string') error.userMessage = detail.error.slice(0, 300);
      }
      throw error;
    }
    const data = await response.json();
    if (!data || typeof data !== 'object') throw new Error('Invalid API response');
    return data;
  } catch (error) {
    if (timedOut) {
      const timeoutError = new Error('Local API timed out');
      timeoutError.name = 'TimeoutError';
      throw timeoutError;
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    signal.removeEventListener('abort', abort);
  }
}

async function overview(signal) {
  if (state.overview) return state.overview;
  const data = await api('/api/overview', signal);
  if (!Array.isArray(data.chapters) || !data.totals) throw new Error('Invalid overview');
  state.overview = data;
  return data;
}

async function record(cache, id, endpoint, signal) {
  if (cache.has(id)) return cache.get(id);
  const data = await api(`${endpoint}/${encodeURIComponent(id)}`, signal);
  cache.set(id, data);
  return data;
}

function renderRail(data) {
  const chapters = list(data.chapters);
  rail.replaceChildren(el('span', { class: 'rail-label' }, '章节导航'), ...chapters.map(chapter =>
    link(`第${Number(chapterNumber(chapter.id))}章`, chapterURL(chapter.id, '', ''), {
      title: chapter.title, 'aria-label': `第${Number(chapterNumber(chapter.id))}章 ${chapter.title}`
    })));
  rail.hidden = !chapters.length;
}

function selectField(id, label, name, options, selected) {
  const select = el('select', { id, name }, options.map(([value, text]) => el('option', { value }, text)));
  if (selected && !options.some(([value]) => value === selected)) select.append(el('option', { value: selected }, selected));
  select.value = selected || '';
  return { field: el('div', { class: 'filter-field' }, el('label', { for: id }, label), select), select };
}

function updateChapterSelect(select, chapters, selected, all = true) {
  select.replaceChildren();
  if (all) select.append(el('option', { value: '' }, '全部章节'));
  for (const chapter of chapters) select.append(el('option', { value: chapter.id }, `${chapterNumber(chapter.id)} · ${chapter.title}`));
  if (selected && !chapters.some(chapter => chapter.id === selected)) select.append(el('option', { value: selected }, selected));
  select.value = selected || '';
}


export const route = (...args) => state.route(...args);
export const navigate = (...args) => state.navigate(...args);
export { main, rail, announcer, mobile, reducedMotion, kinds, statuses, state, el, list, number, count, chapterNumber, query, reviewLabel, sourceChapter, chapterURL, resourceURL, link, safeURL, officialLink, badge, sectionHeading, loading, empty, errorBox, api, overview, record, renderRail, selectField, updateChapterSelect };
export { staticMode, basePath, sitePath, routePath };
