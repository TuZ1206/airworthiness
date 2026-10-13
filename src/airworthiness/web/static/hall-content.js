import { el, list, safeURL } from './hall-core.js';

// Presentation only: keep legal text and backend IDs; never infer new clauses.
function readingPresentation(tag, id, text, extracted) {
  if (/^h[1-6]$/.test(tag) && /^reading-page-\d/.test(id)) return { className: 'source-page-label' };
  if (/^h[1-6]$/.test(tag) && /^reading-toc-/.test(id)) return { className: 'source-directory-heading' };
  if (extracted) return { className: 'extracted-block' };
  if (tag === 'p' && text.includes('\n')) {
    return { className: 'source-lines', lines: text.split('\n').map(line => line.trim()) };
  }
  return { className: '' };
}

// Search terms become text nodes inside mark elements, never HTML strings.
function highlight(root, text) {
  const terms = [...new Set(String(text || '').trim().split(/\s+/u).filter(Boolean))].slice(0, 12).sort((a, b) => b.length - a.length);
  if (!terms.length) return [];
  const pattern = new RegExp(terms.map(term => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'giu');
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: node => node.parentElement?.closest('mark, script, style, button, input, textarea, select')
      ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  const matches = [];
  for (const node of nodes) {
    pattern.lastIndex = 0;
    const value = node.nodeValue;
    let match;
    let cursor = 0;
    const fragment = document.createDocumentFragment();
    while ((match = pattern.exec(value)) !== null) {
      fragment.append(document.createTextNode(value.slice(cursor, match.index)));
      const mark = el('mark', {}, match[0]);
      fragment.append(mark);
      matches.push(mark);
      cursor = match.index + match[0].length;
    }
    if (cursor) {
      fragment.append(document.createTextNode(value.slice(cursor)));
      node.replaceWith(fragment);
    }
  }
  return matches;
}

/* Rebuild a deliberately small HTML vocabulary. Remote scripts, styles, event
   handlers, embedded pages and form controls cannot enter the reading pane. */
function readingHTML(html, suppliedToc, baseURL) {
  const allowed = new Set('article section div header footer main nav p h1 h2 h3 h4 h5 h6 ul ol li dl dt dd blockquote pre code table caption thead tbody tfoot tr th td hr br strong b em i u s del ins sub sup small span mark a abbr figure figcaption address time'.split(' '));
  const discard = new Set('script style link meta base iframe object embed svg math template form input button select textarea noscript canvas audio video source img'.split(' '));
  const parsed = new DOMParser().parseFromString(String(html || ''), 'text/html');
  const root = el('div', { class: 'prose', id: 'reading-content' });
  const ids = new Map();
  const usedIds = new Set();
  let headingIndex = 0;
  const headingItems = [];
  const fragmentLinks = [];
  const base = safeURL(baseURL)?.href || location.href;

  function uniqueID(raw) {
    const seed = `reading-${raw || `section-${++headingIndex}`}`;
    let id = seed;
    let suffix = 1;
    while (usedIds.has(id)) id = `${seed}-${++suffix}`;
    usedIds.add(id);
    if (raw && !ids.has(raw)) ids.set(raw, id);
    return id;
  }

  function copy(source, parent) {
    if (source.nodeType === Node.TEXT_NODE) { parent.append(document.createTextNode(source.nodeValue)); return; }
    if (source.nodeType !== Node.ELEMENT_NODE) return;
    const tag = source.tagName.toLowerCase();
    if (discard.has(tag)) return;
    if (!allowed.has(tag)) { for (const child of source.childNodes) copy(child, parent); return; }
    const target = el(tag);
    const rawId = source.getAttribute('id');
    if (rawId || /^h[1-6]$/.test(tag)) target.id = uniqueID(rawId);
    const presentation = readingPresentation(tag, target.id || '', source.textContent,
      ['p', 'pre', 'div'].includes(tag) && source.classList.contains('extracted-block'));
    if (presentation.className) target.className = presentation.className;
    for (const attr of ['title', 'lang', 'dir']) if (source.hasAttribute(attr)) target.setAttribute(attr, source.getAttribute(attr));
    if (tag === 'td' || tag === 'th') {
      for (const attr of ['colspan', 'rowspan']) {
        const value = Number(source.getAttribute(attr));
        if (value >= 1 && value <= 100) target.setAttribute(attr, String(value));
      }
      if (['row', 'col', 'rowgroup', 'colgroup'].includes(source.getAttribute('scope'))) target.setAttribute('scope', source.getAttribute('scope'));
    }
    if (tag === 'ol' && /^-?\d+$/.test(source.getAttribute('start') || '')) target.setAttribute('start', source.getAttribute('start'));
    if (tag === 'a') {
      const href = source.getAttribute('href') || '';
      if (href.startsWith('#')) fragmentLinks.push([target, href.slice(1)]);
      else {
        const url = safeURL(href, base);
        if (url) {
          target.href = url.href;
          target.target = '_blank';
          target.rel = 'noopener noreferrer';
        }
      }
    }
    for (const child of source.childNodes) copy(child, target);
    // Plain web-source lines (directory entries / enumerated items) need block
    // layout. Never flatten inline markup, code, formulas or extracted tables.
    if (presentation.lines && !source.children.length) {
      target.replaceChildren(...presentation.lines.map(line => el('span', { class: 'source-line' }, line)));
    }
    if (/^h[1-6]$/.test(tag)) headingItems.push({ id: target.id, text: target.textContent.trim(), level: Number(tag.slice(1)) });
    if (tag === 'table') parent.append(el('div', { class: 'table-scroll', tabindex: '0', role: 'region', 'aria-label': '文档表格，可横向滚动' }, target));
    else parent.append(target);
  }

  for (const child of parsed.body.childNodes) copy(child, root);
  for (const [anchor, raw] of fragmentLinks) {
    let decoded = raw;
    try { decoded = decodeURIComponent(raw); } catch { /* Keep literal malformed fragments as text. */ }
    const target = ids.get(decoded) || ids.get(raw);
    if (target) { anchor.href = `#${encodeURIComponent(target)}`; anchor.dataset.tocTarget = target; }
  }
  const apiToc = list(suppliedToc).map(item => ({ id: ids.get(String(item.id)), text: String(item.text || ''), level: Number(item.level) || 2 })).filter(item => item.id && item.text);
  return { root, toc: apiToc.length ? apiToc : headingItems };
}


export { highlight, readingHTML, readingPresentation };
