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

// PDF extraction sometimes inserts an empty line in the middle of one legal
// sentence. Reflow only adjacent extracted blocks with an unfinished left
// side and an unnumbered right side. The source text and paragraph IDs stay
// intact; the original line layout remains available through the reader toggle.
function extractedContinuation(left, right) {
  const end = String(left || '').trimEnd();
  const start = String(right || '').trimStart();
  if (end.length < 14 || !/\p{Script=Han}/u.test(end) || !/^\p{Script=Han}/u.test(start) ||
      /[。！？!?；;：:]$/u.test(end)) return false;
  if (/^(?:[（(][0-9a-zA-Z一二三四五六七八九十]+[）)]|第\s*[0-9０-９一二三四五六七八九十百千万]+\s*[条章节]|[0-9０-９]+[、.．]|〔|\[)/u.test(start)) return false;
  return true;
}

function reflowExtractedBlocks(root) {
  let previous = null;
  let group = null;
  for (const block of [...root.children]) {
    if (block.tagName !== 'P' || !block.classList.contains('extracted-block')) {
      previous = group = null;
      continue;
    }
    if (previous && extractedContinuation(previous.textContent, block.textContent)) {
      if (!group) {
        group = el('div', { class: 'extracted-reflow' });
        previous.before(group);
        group.append(previous);
      }
      group.append(block);
    } else {
      group = null;
    }
    previous = block;
  }
}

// A few embedded Symbol/Wingdings glyphs have an unambiguous role in the
// captured forms and lists. Other private-use glyphs, especially equations,
// cannot be decoded safely from plain text and must not be shown as law.
function readablePdfMarkers(value) {
  return String(value || '').replace(/[\uf09f\uf06c]/gu, '•')
    .replace(/\uf0a8/gu, '□').replace(/\uf06f/gu, '○').replace(/\uf0fc/gu, '✓');
}

function unreliablePdfSymbols(value) {
  return (String(value || '').match(/[\uFFFD\uE000-\uF8FF]/gu) || []).length;
}

function unreliablePdfMathLayout(value) {
  const lines = String(value || '').split('\n');
  if (lines.length < 2) return false;
  const visualFormula = lines.filter(line => /^\s{6,}[A-Za-z0-9(][^\p{Script=Han}]*$/u.test(line) &&
    (/[=＝≥≤+−÷×]/u.test(line) || /^[A-Za-z][A-Za-z0-9 ]{0,12}$/u.test(line.trim())));
  return visualFormula.length >= 2 ||
    lines.some(line => /^\s{12,}[A-Z][A-Z ]{3,}处.+[A-Za-z].*[＝=]/u.test(line)) ||
    lines.some(line => /^\s{6,}[A-Z][A-Z ]{3,}由如下方法确定.+\([a-z]\)\s*V/u.test(line));
}

function guardExtractedGlyphs(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);
  for (const node of textNodes) node.nodeValue = readablePdfMarkers(node.nodeValue);

  const initial = [...root.children].filter(block =>
    unreliablePdfSymbols(block.textContent) || unreliablePdfMathLayout(block.textContent));
  const damagedSet = new Set(initial);
  for (const block of initial) {
    const next = block.nextElementSibling;
    if (/\p{Script=Han}$/u.test(block.textContent.trim()) &&
        next?.tagName === 'P' && next.classList.contains('extracted-block') &&
        /^\p{Script=Han}/u.test(next.textContent.trim())) damagedSet.add(next);
  }
  const damaged = [...root.children].filter(block => damagedSet.has(block));
  if (!damaged.length) return { severe: false, blocks: 0 };
  const count = damaged.reduce((sum, block) => sum + unreliablePdfSymbols(block.textContent), 0);
  const notice = el('div', { class: 'extraction-quality-note', role: 'note' },
    el('strong', {}, '提取文字存在符号缺损'),
    el('p', {}, '相关片段已暂停展示，不能据此解读条款或公式；请使用上方原件链接核对。原始采集文件及哈希未改动。'));
  if (count >= 100 || damaged.length >= 25) {
    root.replaceChildren(notice, el('p', { class: 'extraction-quality-summary' },
      '该文件的提取文本缺损较多，文字版暂不提供阅读。'));
    return { severe: true, blocks: damaged.length };
  }
  root.prepend(notice);
  for (const block of damaged) {
    const previous = block.previousElementSibling;
    if (previous?.classList.contains('extraction-corrupt-block')) {
      if (block.id) previous.append(el('span', { id: block.id }));
      block.remove();
      continue;
    }
    const placeholder = el('aside', { class: 'extraction-corrupt-block', role: 'note' },
      '此段公式或特殊符号无法从 PDF 可靠还原，请核对原件。');
    if (block.id) placeholder.id = block.id;
    block.replaceWith(placeholder);
  }
  return { severe: false, blocks: damaged.length };
}

// PDF text extraction retains spaces between columns even when the browser
// collapses them. Only runs with a stable, unambiguous numeric column count
// become tables. Other dense numeric runs are folded for source-PDF review.
function splitColumns(line) {
  return String(line).trim().split(/\s{2,}|\t+/u).filter(Boolean);
}

function numericColumns(line) {
  const cells = splitColumns(line);
  return cells.length >= 2 && cells.length <= 12 &&
    cells.every(cell => /^[+−-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?$/u.test(cell)) ? cells : null;
}

function extractedTableSegments(raw) {
  const lines = String(raw || '').split('\n');
  const segments = [];
  let cursor = 0;
  for (let start = 0; start < lines.length;) {
    const first = numericColumns(lines[start]);
    if (!first) { start += 1; continue; }
    let end = start + 1;
    while (end < lines.length && numericColumns(lines[end])?.length === first.length) end += 1;
    if (end - start < 3) { start = end; continue; }
    let headerStart = start;
    while (headerStart > cursor && start - headerStart < 3) {
      const cells = splitColumns(lines[headerStart - 1]);
      if (cells.length !== first.length || numericColumns(lines[headerStart - 1]) ||
          !cells.some(cell => /[^\d\s.,+−-]/u.test(cell))) break;
      headerStart -= 1;
    }
    if (headerStart > cursor) segments.push({ type: 'text', raw: lines.slice(cursor, headerStart).join('\n') });
    const headerRows = lines.slice(headerStart, start).map(splitColumns);
    segments.push({ type: 'table', raw: lines.slice(headerStart, end).join('\n'),
      headers: first.map((_, index) => headerRows.map(row => row[index]).join(' · ')),
      rows: lines.slice(start, end).map(numericColumns), columns: first.length });
    cursor = end;
    start = end;
  }
  if (cursor < lines.length) segments.push({ type: 'text', raw: lines.slice(cursor).join('\n') });
  return segments;
}

function denseUnstructuredNumbers(raw) {
  const lines = String(raw || '').split('\n').map(line => line.trim()).filter(Boolean);
  const numericLines = lines.filter(line => {
    const values = line.match(/[+−-]?(?:\d[\d,.]*)(?:%|％)?/gu) || [];
    return values.length >= 2 &&
      line.replace(/[+−-]?(?:\d[\d,.]*)(?:%|％)?/gu, '').trim().length <= 4;
  });
  return numericLines.length >= 4 ||
    (numericLines.length >= 3 && numericLines.every(line => (line.match(/\d/gu) || []).length >= 8)) ||
    (lines.length === 1 && (numericLines[0]?.match(/\d[\d,.]*/gu) || []).length >= 12) ||
    (lines.length >= 8 && lines.filter(line => /^[+−-]?\d[\d,.]*$/u.test(line)).length >= 8);
}

function appendExtractedTable(container, segment, previousHeaders, rowIds = []) {
  const headers = segment.headers.some(Boolean) ? segment.headers :
    previousHeaders?.length === segment.columns ? previousHeaders : null;
  if (!headers) {
    container.append(el('details', { class: 'extracted-table-unverified' },
      el('summary', {}, '疑似表格：缺少可核对的列名，请对照上方官方 PDF 原件'),
      el('pre', {}, segment.raw)));
    for (const id of rowIds.filter(Boolean)) container.append(el('span', { id }));
    return null;
  }
  const table = el('table', { class: 'extracted-data-table' });
  const thead = el('thead', {}, el('tr', {}, ...headers.map(label => el('th', { scope: 'col' }, label))));
  const tbody = el('tbody', {}, ...segment.rows.map((row, rowIndex) =>
    el('tr', {}, ...row.map((cell, cellIndex) => el('td', {},
      ...(cellIndex === 0 && rowIds[rowIndex] ? [el('span', { id: rowIds[rowIndex] })] : []), cell)))));
  table.append(thead, tbody);
  const shell = el('div', { class: 'table-scroll', tabindex: '0', role: 'region', 'aria-label': '提取文本重建的表格，可横向滚动' }, table);
  container.append(el('div', { class: 'extracted-table-wrap' },
    el('p', { class: 'extracted-table-note' }, '根据提取文本的列间距整理；表格数值与列名请以官方 PDF 原件为准。'), shell,
    el('pre', { class: 'extracted-table-raw' }, segment.raw)));
  return headers;
}

function structureExtractedTables(root) {
  let previousHeaders = null;
  for (const block of [...root.children]) {
    if (block.parentElement !== root) continue;
    if (block.tagName !== 'P' || !block.classList.contains('extracted-block')) {
      if (!block.classList?.contains('source-page-label')) previousHeaders = null;
      continue;
    }
    const firstRow = !block.textContent.includes('\n') && numericColumns(block.textContent);
    if (firstRow) {
      const rowBlocks = [block];
      let next = block.nextElementSibling;
      while (next?.tagName === 'P' && next.classList.contains('extracted-block') &&
          !next.textContent.includes('\n') && numericColumns(next.textContent)?.length === firstRow.length) {
        rowBlocks.push(next);
        next = next.nextElementSibling;
      }
      if (rowBlocks.length >= 3) {
        const container = el('div', { class: 'extracted-layout', id: block.id });
        const segment = { type: 'table', raw: rowBlocks.map(item => item.textContent).join('\n'),
          headers: [], rows: rowBlocks.map(item => numericColumns(item.textContent)), columns: firstRow.length };
        previousHeaders = appendExtractedTable(container, segment, previousHeaders,
          rowBlocks.map((item, index) => index ? item.id : ''));
        block.replaceWith(container);
        for (const item of rowBlocks.slice(1)) item.remove();
        continue;
      }
    }
    const segments = extractedTableSegments(block.textContent);
    if (!segments.some(segment => segment.type === 'table') && !denseUnstructuredNumbers(block.textContent)) {
      if (!/^(?:交通运输部规章|交通运输部发布|-\s*\d+\s*-)$/u.test(block.textContent.trim())) previousHeaders = null;
      continue;
    }
    const container = el('div', { class: 'extracted-layout' });
    if (block.id) container.id = block.id;
    for (const segment of segments) {
      if (segment.type === 'table') {
        previousHeaders = appendExtractedTable(container, segment, previousHeaders);
      } else if (segment.raw.trim()) {
        if (denseUnstructuredNumbers(segment.raw)) {
          container.append(el('details', { class: 'extracted-table-unverified' },
            el('summary', {}, '疑似表格：列关系无法可靠还原，请对照上方官方 PDF 原件'),
            el('pre', {}, segment.raw)));
        } else {
          container.append(el('p', { class: 'extracted-block' }, segment.raw));
          if (!/^(?:交通运输部规章|交通运输部发布|-\s*\d+\s*-)$/u.test(segment.raw.trim())) previousHeaders = null;
        }
      }
    }
    block.replaceWith(container);
  }
}

// Search terms become text nodes inside mark elements, never HTML strings.
function highlight(root, text) {
  const terms = [...new Set(String(text || '').trim().split(/\s+/u).filter(Boolean))].slice(0, 12).sort((a, b) => b.length - a.length);
  if (!terms.length) return [];
  const pattern = new RegExp(terms.map(term => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'giu');
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: node => node.parentElement?.closest('mark, script, style, button, input, textarea, select, .extracted-table-raw, .extracted-table-unverified pre')
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


export { highlight, readingHTML, readingPresentation, extractedContinuation, reflowExtractedBlocks, splitColumns, numericColumns, extractedTableSegments, denseUnstructuredNumbers, structureExtractedTables, readablePdfMarkers, unreliablePdfSymbols, guardExtractedGlyphs };
