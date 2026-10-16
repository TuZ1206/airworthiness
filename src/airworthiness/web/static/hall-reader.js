import { main, announcer, mobile, reducedMotion, kinds, statuses, state, el, list, count, chapterNumber, query, reviewLabel, sourceChapter, chapterURL, resourceURL, link, officialLink, badge, loading, errorBox, overview, record, renderRail, updateChapterSelect, route, navigate } from './hall-core.js';
import { readingHTML, highlight, reflowExtractedBlocks, structureExtractedTables, guardExtractedGlyphs } from './hall-content.js';
import { createDocumentView } from './hall-document-view.js';
import { renderChapterGraph } from './hall-graph.js';
import { staticMode } from './hall-core.js';

function readerPanel(className, title, content) {
  return el('details', { class: className, open: !mobile.matches }, el('summary', { class: 'panel-summary' }, title), content);
}

function renderChapterGuide(chapter) {
  const guide = chapter.guide;
  if (!guide?.sections?.length) return readingHTML(chapter.guide_html, [], null);
  const root = el('div', { class: 'chapter-guide' });
  const toc = [];
  const sectionHeading = (id, title, level = 2, includeInToc = false) => {
    if (includeInToc) toc.push({ id, text: title, level, kind: 'guide' });
    return el(`h${level}`, { id }, title);
  };
  const docs = new Map(list(chapter.documents).map(doc => [doc.source_id, doc]));
  root.append(el('section', { class: 'guide-positioning' },
    sectionHeading('guide-positioning', '本章定位'), el('p', {}, guide.positioning)));
  const path = el('nav', { class: 'guide-path', 'aria-label': '本章专题路径' },
    list(guide.sections).map((section, index) => el('a', { href: `#guide-${section.id}`, 'data-toc-target': `guide-${section.id}` },
      el('span', { class: 'guide-path-number' }, String(index + 1).padStart(2, '0')),
      el('span', {}, section.title), el('span', { 'aria-hidden': 'true' }, '↗'))));
  root.append(el('section', { class: 'guide-path-section' }, sectionHeading('guide-path', '专题路径'), path));
  const cards = el('div', { class: 'guide-card-list' });
  for (const [index, section] of guide.sections.entries()) {
    const sources = el('ul', { class: 'guide-source-list' });
    for (const ref of section.sources) {
      const sourceId = typeof ref === 'string' ? ref : ref.source_id;
      const doc = docs.get(sourceId);
      if (!doc) continue;
      sources.append(el('li', { class: 'guide-source' },
        link([el('span', { class: 'guide-source-id' }, sourceId), el('span', { class: 'guide-source-title' }, doc.title),
          el('span', { 'aria-hidden': 'true' }, '↗')], resourceURL(doc), { class: 'guide-source-link' }),
        el('div', { class: 'guide-source-flags' }, badge(doc.content_kind),
          el('span', { class: 'guide-status' }, statuses[doc.document_status] || '效力待核'),
          el('span', { class: 'review-label' }, reviewLabel(doc.review_status))),
        typeof ref === 'object' && ref.locator ?
          el('p', { class: 'guide-locator' }, `正文定位线索：${ref.locator}（待专业审核）`) : null,
        doc.content_kind === 'metadata' ?
          el('p', { class: 'guide-limitation' }, '仅有状态信息，不能据此确认具体条款。') : null));
    }
    cards.append(el('section', { class: 'guide-card' },
      el('div', { class: 'guide-card-heading' }, el('span', { class: 'guide-card-number' }, String(index + 1).padStart(2, '0')),
        sectionHeading(`guide-${section.id}`, section.title, 3, true)),
      el('p', { class: 'guide-card-summary' }, section.summary),
      el('p', { class: 'guide-sources-label' }, '对应资料 · 来源编号'), sources));
  }
  root.append(el('section', { class: 'guide-topics' }, sectionHeading('guide-topics', '专题与对应资料'), cards));
  const related = list(guide.related);
  if (related.length) root.append(el('section', { class: 'guide-related' }, sectionHeading('guide-related', '跨章衔接'),
    el('div', { class: 'guide-related-list' }, related.map(item =>
      link([el('span', { class: 'guide-related-id' }, item.chapter_id.toUpperCase()),
        el('span', {}, item.reason), el('span', { 'aria-hidden': 'true' }, '↗')], chapterURL(item.chapter_id, '', ''),
      { class: 'guide-related-link' })))));
  root.append(el('p', { class: 'guide-footnote' }, '以上仅为资料导航，不代表文件现行有效、条款适用或专业审核通过。请逐份查看效力、收录类型及官方原件。'));
  return { root, toc };
}

function renderReaderSidebar(container, chapter, selectedSource, chapters, toc) {
  const switcher = el('select', { id: 'reader-chapter', class: 'chapter-switch', 'aria-label': '切换章节' });
  updateChapterSelect(switcher, chapters.length ? chapters : [chapter], chapter.id, false);
  switcher.addEventListener('change', () => navigate(chapterURL(switcher.value, '', query())));
  const documents = list(chapter.documents);
  const files = el('ul', { class: 'file-list' });
  const fileCount = el('span', {}, count(documents.length));
  const filter = el('input', { id: 'file-search', type: 'search', class: 'file-filter', placeholder: '筛选本章文件', 'aria-label': '筛选本章文件', autocomplete: 'off' });
  const renderFiles = () => {
    const term = filter.value.trim().toLocaleLowerCase();
    const shown = documents.filter(doc => `${doc.source_id} ${doc.title} ${doc.document_code || ''}`.toLocaleLowerCase().includes(term));
    fileCount.textContent = term ? `${shown.length} / ${documents.length}` : count(documents.length);
    files.replaceChildren(...shown.map(doc => el('li', {}, link([
      el('span', { class: 'file-id' }, doc.source_id), el('span', {}, doc.title), el('br'), badge(doc.content_kind)
    ], resourceURL({ ...doc, chapter_id: doc.chapter_id || chapter.id }), {
      class: 'file-link', 'aria-current': doc.source_id === selectedSource ? 'page' : null
    }))));
    if (!shown.length) files.append(el('li', { class: 'sidebar-empty' }, term ? '没有匹配的文件。' : '本章尚未收录文件。'));
  };
  filter.addEventListener('input', renderFiles);
  renderFiles();
  const tocList = el('ol', { class: 'toc-list' });
  const minimum = Math.min(...toc.map(item => Number(item.level) || 2));
  for (const item of toc) tocList.append(el('li', {}, el('a', {
    href: `#${encodeURIComponent(item.id)}`, 'data-toc-target': item.id,
    'data-depth': Math.min(3, Math.max(1, (Number(item.level) || 2) - minimum + 1))
  }, item.text)));
  container.replaceChildren(
    el('p', { class: 'sidebar-label' }, '九章索引'), switcher,
    link('本章导读', chapterURL(chapter.id), { class: 'guide-link', 'aria-current': selectedSource ? null : 'page' }),
    chapter.graph?.nodes?.length ? el('a', { href: '#chapter-graph', class: 'guide-link', 'data-toc-target': 'chapter-graph' },
      `本章知识图谱 · ${chapter.graph.nodes.length} 个节点`) : null,
    el('details', { class: 'toc-disclosure', open: !selectedSource && Boolean(chapter.guide?.sections?.length) },
      el('summary', {}, selectedSource ? `文字目录 · ${toc.length} 处定位` : '专题导航'),
      el('nav', { 'aria-label': '当前内容目录' },
        toc.length ? tocList : el('p', { class: 'sidebar-empty' }, '当前内容没有可用的分节目录。'))),
    el('p', { class: 'sidebar-label' }, '本章文件 · ', fileCount), filter,
    el('nav', { 'aria-label': '本章文件' }, files));
}

function glossaryTarget(item, chapter) {
  const base = chapterURL(sourceChapter(item.source_id, chapter.id), item.source_id);
  if (!['text_match', 'verified_clause'].includes(item.locator_status)) return base;
  let anchor = String(item.locator_anchor || '');
  if (!anchor && item.anchor_or_url) {
    try { anchor = decodeURIComponent(new URL(item.anchor_or_url, location.href).hash.slice(1)); }
    catch { return base; }
  }
  if (!/^(?:reading-)?(?:clause|chapter|page|paragraph|section)-[0-9a-z-]+$/.test(anchor)) return base;
  return `${base}#${anchor.startsWith('reading-') ? anchor : `reading-${anchor}`}`;
}

function locatorDescription(item) {
  return {
    verified_clause: '精确引文位置已核对；未核验术语释义，也不代表专业审核通过。',
    text_match: '仅关键词匹配；未核验术语释义，不表示此处支持该定义。',
    source_only: '仅定位来源；尚未找到可靠的正文匹配。'
  }[item.locator_status] || '仅定位来源；尚未找到可靠的正文匹配。';
}

function renderGlossary(container, entries, chapter) {
  const terms = list(entries);
  const rows = el('div');
  const shownCount = el('span', { class: 'glossary-count', 'aria-live': 'polite' }, `${terms.length} 个术语`);
  const input = el('input', { type: 'search', class: 'file-filter', placeholder: '查找术语', 'aria-label': '查找术语', autocomplete: 'off' });
  const render = () => {
    const term = input.value.trim().toLocaleLowerCase();
    const filtered = terms.filter(item => `${item.term} ${item.definition} ${item.group || ''}`.toLocaleLowerCase().includes(term));
    shownCount.textContent = `${filtered.length} 个术语`;
    rows.replaceChildren(...filtered.map(item => el('section', { class: 'glossary-entry' },
      item.group ? el('div', { class: 'term-group' }, item.group) : null,
      el('h3', {}, item.term), el('p', {}, item.definition || '释义尚待补充。'),
      item.source_id ? link(`来源 ${item.source_id} ↗`, glossaryTarget(item, chapter), { class: 'term-source' }) :
        el('span', { class: 'review-label' }, '来源尚待补充'),
      el('p', { class: 'sidebar-empty' }, locatorDescription(item)),
      ['text_match', 'verified_clause'].includes(item.locator_status) && item.locator_evidence ?
        el('p', { class: 'locator-evidence' }, `原文片段：${item.locator_evidence}`) : null,
      el('span', { class: 'review-label' }, reviewLabel(item.review_status)))));
    if (!filtered.length) rows.append(el('p', { class: 'sidebar-empty' }, term ? '没有匹配的术语。' : '当前内容暂无关联术语。'));
  };
  input.addEventListener('input', render);
  render();
  container.replaceChildren(el('h2', { class: 'glossary-title' }, '术语释义', shownCount),
    el('p', { class: 'glossary-intro' }, '随文参照 · 原文定位不等于释义核验'), input, rows);
}

function readerTools(content, q) {
  const input = el('input', { type: 'search', value: q, maxlength: '200', 'aria-label': '在当前内容中查找', placeholder: '在当前内容中查找', autocomplete: 'off' });
  const form = el('form', { class: 'reader-find-form', role: 'search', 'aria-label': '页内查找' }, input,
    el('button', { type: 'submit', class: 'button' }, '查找'));
  form.addEventListener('submit', event => {
    event.preventDefault();
    const url = new URL(location.href);
    const term = input.value.trim();
    if (term) url.searchParams.set('q', term);
    else url.searchParams.delete('q');
    url.hash = '';
    navigate(url.pathname + url.search);
  });
  const toolbar = el('div', { class: 'reader-tools' }, form);
  const matches = highlight(content, q);
  if (q) {
    let index = -1;
    const status = el('span', { role: 'status' }, `找到 ${matches.length} 处匹配`);
    const step = delta => {
      if (!matches.length) return;
      matches[index]?.classList.remove('current-match');
      index = (index + delta + matches.length) % matches.length;
      matches[index].classList.add('current-match');
      matches[index].scrollIntoView({ block: 'center', behavior: reducedMotion.matches ? 'auto' : 'smooth' });
      status.textContent = `${index + 1} / ${matches.length} 处匹配`;
    };
    toolbar.append(el('div', { class: 'match-navigation' }, status,
      el('button', { type: 'button', class: 'text-button', disabled: !matches.length, onclick: () => step(index < 0 ? 0 : -1) }, '上一处'),
      el('button', { type: 'button', class: 'text-button', disabled: !matches.length, onclick: () => step(1) }, '下一处'),
      el('button', { type: 'button', class: 'text-button', onclick: () => { input.value = ''; form.requestSubmit(); } }, '清除高亮')));
  }
  return toolbar;
}

function originalPDFs(doc) {
  if (doc.original_available !== true || !/^CH\d{2}-S\d{3}$/.test(doc.source_id || '')) return [];
  const expected = `/api/documents/${doc.source_id}/original`;
  const items = list(doc.originals);
  const candidates = items.length ? items : [{ label: '', url: doc.original_url }];
  return candidates.filter(item => item && typeof item.url === 'string' && item.url.startsWith(expected) &&
    /^(?:\?index=(?:0|[1-9]\d*))?$/.test(item.url.slice(expected.length)))
    .map(item => ({ url: item.url, label: typeof item.label === 'string' ? item.label : '' }));
}

function documentNotice(doc) {
  const messages = {
    fulltext: '本页收录网页正文。法规效力与版本请核对官方来源。',
    extracted: '本页为文件提取正文，尚待校对；表格、公式与分页可能存在提取误差。',
    excerpt: '本页为整理摘录，可能包含归纳或转述，不代表完整原文，不宜作为逐字引用。请核对官方来源。',
    metadata: '本条目仅收录来源登记及获取状态信息，尚无可用正文。下方信息不代表原文。'
  };
  if (doc.content_kind === 'metadata' && originalPDFs(doc).length) {
    messages.metadata = '本条目暂缺可检索文字，可查看本地 PDF 原件并对照图表、公式。下方登记信息不代表原文。';
  }
  if (doc.content_kind === 'extracted' && originalPDFs(doc).length) {
    messages.extracted = '已保存 PDF 原件，可按原件版式阅读。提取文字仅用于辅助检索，表格、公式及 OCR 文字仍需对照原件。';
  }
  return el('aside', { class: 'content-notice', 'aria-label': '收录与审核说明' },
    el('strong', {}, `${kinds[doc.content_kind] || '收录类型未注明'} · ${reviewLabel(doc.review_status)}`),
    el('p', {}, messages[doc.content_kind] || '收录范围尚未确认，请核对官方来源。'),
    doc.navigation_note || doc.extraction_note ? el('details', { class: 'notice-details' },
      el('summary', {}, '提取限制与定位说明'),
      doc.navigation_note ? el('p', {}, doc.navigation_note) : null,
      doc.extraction_note ? el('p', { class: 'extraction-note' }, doc.extraction_note) : null) : null);
}

function metadataEvidenceLink(value, index) {
  try {
    const host = new URL(value).hostname.toLowerCase().replace(/\.$/, '');
    if (host !== 'gov.cn' && !host.endsWith('.gov.cn')) return null;
    return officialLink(value, `官方证据 ${index + 1} ↗`);
  } catch { return null; }
}

function metadataDetails(doc) {
  const entries = list(doc.metadata_verification).filter(item => item && typeof item === 'object' && !Array.isArray(item));
  if (!entries.length) return null;
  const fields = { title: '题名', document_code: '文件文号', publish_date: '发布日期' };
  const actions = { corrected: '已纠正', already_matches: '原值已一致', confirmed: '已确认',
    explained: '差异已解释', recorded: '仅记录', blocked: '未应用', unresolved: '未解决' };
  const value = text => typeof text === 'string' && text.trim() ? text : '未记录';
  return el('section', { 'aria-label': '元数据核对记录' }, el('h3', {}, '元数据核对记录'),
    el('ul', {}, entries.map(entry => {
      const old = value(entry.original_value ?? doc.original_metadata?.[entry.field]);
      const verified = value(entry.verified_value);
      const applied = ['corrected', 'already_matches', 'confirmed'].includes(entry.application);
      const change = applied ? `${old} → ${verified}` : `${old}（原值保留；核对值：${verified}）`;
      const isField = Object.hasOwn(fields, entry.field);
      const label = isField ? fields[entry.field] : entry.field === 'url_alias' ? '同源地址核对' : '来源核对';
      const notes = [...new Set([entry.evidence?.text, entry.note].filter(text => typeof text === 'string' && text.trim()))];
      const detail = isField ? change : notes.join('；') || '未提供核对说明。';
      const evidence = list(entry.evidence_url).map(metadataEvidenceLink).filter(Boolean);
      return el('li', {}, el('p', {}, `${label}：${detail} · ${actions[entry.application] || '未应用'}`),
        evidence.length ? evidence : el('span', { class: 'sidebar-empty' }, '未提供可用的官方证据链接。'));
    })),
    el('p', { class: 'sidebar-empty' }, `仅核对登记字段，不改变专业审核状态（${reviewLabel(doc.review_status)}）。`));
}

function provenanceDetails(doc) {
  const source = doc.body_provenance || doc.uploaded_provenance || {};
  const uploaded = doc.uploaded_provenance || {};
  const fields = [
    ['正文来源编号', source.source_id || doc.source_id],
    ['采集时间', source.crawled_at || doc.crawled_at || '未记录'],
    ['当前正文 Markdown SHA-256', source.markdown_sha256 || doc.sha256 || '未记录'],
    ['原始附件／页面 SHA-256', source.pdf_sha256 || source.original_sha256 || '未取得原始字节哈希']
  ];
  const attachment = source.pdf_url || (source.source_id === doc.source_id ? uploaded.pdf_url : '');
  const originals = originalPDFs(doc);
  return el('details', { class: 'provenance-details' },
    el('summary', {}, '查看采集与校验记录'),
    el('dl', { class: 'document-facts' }, fields.map(([name, value]) => [el('dt', {}, name), el('dd', {}, value)])),
    originals.map(item => el('a', { href: item.url, target: '_blank', rel: 'noopener noreferrer', class: 'button' },
      `查看本地 PDF 原件${item.label ? ` · ${item.label}` : ''} ↗`)),
    originals.length ? el('p', {}, '请对照 PDF 原件中的图表、公式；提取正文可能存在缺失。') : null,
    attachment ? officialLink(attachment, '查看官方附件 ↗') : null,
    metadataDetails(doc),
    el('p', { class: 'sidebar-empty' }, '哈希用于核对保存文件的一致性，不代表专业审核通过。'));
}

function documentFacts(doc) {
  const facts = [
    ['资料标识', doc.source_id],
    ['文件文号', doc.document_code || '未注明'],
    ['发布日期', doc.publish_date || '未注明'],
    ['文件效力', el('span', {}, statuses[doc.document_status] || statuses.unknown, ' · ', el('span', { class: 'review-label' }, reviewLabel(doc.review_status)))],
    ['官方来源', officialLink(doc.url, '打开官方原始页面 ↗') || '未提供可用的官方链接']
  ];
  // These optional acquisition fields are user-facing provenance, not local paths.
  const acquisition = doc.acquisition || {};
  const acquiredAt = acquisition.acquired_at || acquisition.retrieved_at || acquisition.fetched_at;
  if (acquiredAt) facts.push(['收录时间', acquiredAt]);
  return el('dl', { class: 'document-facts' }, facts.map(([title, value]) => [el('dt', {}, title), el('dd', {}, value)]));
}

async function renderReader(chapterId, signal, generation) {
  const sourceId = new URLSearchParams(location.search).get('source') || '';
  const sidebar = el('div', { class: 'sidebar-content' }, loading('正在读取目录…', true));
  const glossary = el('div', { class: 'sidebar-content' }, loading('正在读取术语…', true));
  const pane = el('section', { class: 'reading-pane', tabindex: '0', 'aria-label': '正文阅读区', 'aria-busy': 'true' }, loading('正在打开阅读内容…'));
  const leftPanel = readerPanel('reader-sidebar', '章节、文件与当前目录', sidebar);
  const rightPanel = readerPanel('glossary-sidebar', '随文术语释义', glossary);
  rightPanel.open = false;
  leftPanel.append(rightPanel);
  main.replaceChildren(el('div', { class: 'reader-shell' }, leftPanel, pane));
  const resize = () => { leftPanel.open = !mobile.matches; rightPanel.open = false; };
  mobile.addEventListener('change', resize);
  state.disposers.push(() => mobile.removeEventListener('change', resize));
  const values = await Promise.allSettled([
    record(state.chapters, chapterId, '/api/chapters', signal),
    sourceId ? record(state.documents, sourceId, '/api/documents', signal) : Promise.resolve(null),
    overview(signal)
  ]);
  if (generation !== state.generation || signal.aborted) return;
  const [chapterResult, docResult, overviewResult] = values;
  if (overviewResult.status === 'fulfilled') renderRail(overviewResult.value);
  if (chapterResult.status === 'rejected') {
    pane.replaceChildren(errorBox(chapterResult.reason, () => route()), link('返回资源总览', '/', { class: 'button' }));
    sidebar.replaceChildren(el('p', { class: 'sidebar-empty' }, '章节目录暂不可用。'));
    glossary.replaceChildren(el('p', { class: 'sidebar-empty' }, '术语释义暂不可用。'));
    pane.setAttribute('aria-busy', 'false');
    return;
  }
  const chapter = chapterResult.value;
  const chapters = overviewResult.status === 'fulfilled' ? list(overviewResult.value.chapters) : [chapter];
  const doc = docResult.status === 'fulfilled' ? docResult.value : null;
  if (docResult.status === 'rejected') {
    pane.replaceChildren(errorBox(docResult.reason, () => route()), link('阅读本章导读', chapterURL(chapter.id), { class: 'button' }));
    renderReaderSidebar(sidebar, chapter, sourceId, chapters, []);
    renderGlossary(glossary, chapter.glossary, chapter);
    pane.setAttribute('aria-busy', 'false');
    return;
  }
  // A copied source URL can refer to another chapter; use the canonical route.
  if (doc?.chapter_id && doc.chapter_id !== chapterId) {
    navigate(chapterURL(doc.chapter_id, doc.source_id) + location.hash, { replace: true });
    return;
  }
  const isDoc = Boolean(doc);
  const content = isDoc ? readingHTML(doc.html, doc.toc, doc.url) : renderChapterGuide(chapter);
  if (doc?.content_kind === 'extracted') {
    const quality = guardExtractedGlyphs(content.root);
    if (quality.severe) content.toc = [];
    else {
      structureExtractedTables(content.root);
      reflowExtractedBlocks(content.root);
    }
  }
  if (!content.root.textContent.trim()) content.root.append(el('p', {}, isDoc
    ? doc.content_kind === 'metadata' ? '尚未收录可阅读正文。请通过上方官方来源查阅。' : '当前条目尚无可展示的内容。请核对官方来源或查看收录质量报告。'
    : '本章导读尚待补充。可从左侧文件列表选择已收录资料。'));
  const title = isDoc ? doc.title || doc.source_id : chapter.title;
  const heading = el('h1', { class: 'reader-heading', id: 'reader-title', tabindex: '-1' }, title);
  const inner = el('div', { class: 'reading-inner' },
    el('nav', { class: 'reading-breadcrumb', 'aria-label': '当前位置' }, link('资源总览', '/'),
      el('span', { class: 'breadcrumb-divider', 'aria-hidden': 'true' }, '/'),
      isDoc ? link(`第 ${chapterNumber(chapter.id)} 章`, chapterURL(chapter.id)) : el('span', {}, `第 ${chapterNumber(chapter.id)} 章`),
      el('span', { class: 'breadcrumb-divider', 'aria-hidden': 'true' }, '/'), el('span', {}, isDoc ? doc.source_id : '本章导读')),
    el('p', { class: 'eyebrow' }, isDoc ? `${doc.source_id} / ${kinds[doc.content_kind] || '收录资料'}` : `CHAPTER ${chapterNumber(chapter.id)} / READING GUIDE`), heading,
    isDoc ? el('p', { class: 'document-meta' }, doc.document_code || doc.source_id, ' · ', doc.publish_date || '发布日期待核对') :
      el('p', { class: 'reader-description' }, chapter.description),
    isDoc ? el('details', { class: 'document-details' }, el('summary', {}, '文件信息、来源与校验记录'),
      documentFacts(doc), provenanceDetails(doc)) : null,
    isDoc ? documentNotice(doc) : el('aside', { class: 'content-notice' }, el('strong', {}, '章节导读 · 待专业审核'), '导读用于组织阅读线索。查阅具体条文时，请选择已收录的来源文件。'),
    isDoc ? createDocumentView({ doc, originals: originalPDFs(doc), content: content.root,
      tools: readerTools(content.root, query()), search: query(), hash: location.hash }) :
      el('div', {}, readerTools(content.root, query()), content.root));
  const related = isDoc ? list(doc.related_sources) : [];
  if (related.length) inner.append(el('section', { class: 'related-sources', 'aria-label': '相关资料' }, el('h2', {}, '继续阅读 · 相关资料'),
    related.map(item => link([item.title || item.source_id, el('small', {}, `${item.source_id} · ${item.chapter_title || item.chapter_id || ''}`)], resourceURL(item)))));
  const graph = renderChapterGraph(chapter, isDoc);
  if (graph) inner.append(graph);
  inner.append(el('div', { class: 'reading-end' }, el('span', {}, '阅读位置自动保存在当前浏览器会话中'),
    el('button', { type: 'button', class: 'text-button', onclick: () => scrollToReadingStart(pane) }, '回到顶部 ↑'),
    link('收录质量 ↗', '/quality')));
  pane.replaceChildren(inner);
  pane.setAttribute('aria-busy', 'false');
  renderReaderSidebar(sidebar, chapter, sourceId, chapters, content.toc);
  renderGlossary(glossary, isDoc ? doc.glossary : chapter.glossary, chapter);
  document.title = `${title} · ${staticMode ? '适航法规资源馆' : '适航离线资源馆'}`;
  announcer.textContent = `已打开${isDoc ? '资料' : '章节导读'}：${title}`;
  state.pane = pane;
  state.scrollKey = `airworthiness:reading:${chapter.id}:${sourceId || 'guide'}`;
  pane.addEventListener('scroll', scheduleSave, { passive: true });
  restoreReadingPosition(pane, generation);
  observeTOC(content.toc, pane);
}

function scrollToReadingStart(pane) {
  if (mobile.matches) pane.scrollIntoView({ block: 'start', behavior: reducedMotion.matches ? 'auto' : 'smooth' });
  else pane.scrollTo({ top: 0, behavior: reducedMotion.matches ? 'auto' : 'smooth' });
}

function saveReadingPosition() {
  if (!state.scrollKey || !state.pane || !state.scrollReady) return;
  const top = mobile.matches ? Math.max(0, -state.pane.getBoundingClientRect().top + document.querySelector('.site-header').offsetHeight) : state.pane.scrollTop;
  try {
    sessionStorage.setItem(state.scrollKey, JSON.stringify({ top, windowY: window.scrollY, mobile: mobile.matches, hash: location.hash }));
  } catch { /* Reading still works if the browser disables session storage. */ }
}

let saveFrame = 0;
function scheduleSave() {
  if (saveFrame) return;
  saveFrame = requestAnimationFrame(() => { saveFrame = 0; saveReadingPosition(); });
}

function hashTarget() {
  if (!location.hash) return null;
  try {
    const id = decodeURIComponent(location.hash.slice(1));
    return document.getElementById(id) || document.getElementById(`reading-${id}`);
  }
  catch { return null; }
}

function restoreReadingPosition(pane, generation) {
  let saved = null;
  try { saved = JSON.parse(sessionStorage.getItem(state.scrollKey)); } catch { /* No saved position. */ }
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (generation !== state.generation) return;
    const top = Math.max(0, Number(saved?.top) || 0);
    if (mobile.matches) {
      const y = saved ? saved.mobile ? Math.max(0, Number(saved.windowY) || 0) :
        window.scrollY + pane.getBoundingClientRect().top + top - document.querySelector('.site-header').offsetHeight : 0;
      window.scrollTo(0, y);
    } else {
      window.scrollTo(0, 0);
      pane.scrollTop = top;
    }
    const target = hashTarget();
    if (target && pane.contains(target) && (!saved || saved.hash !== location.hash)) target.scrollIntoView({ block: 'start' });
    state.scrollReady = true;
  }));
}

function observeTOC(toc, pane) {
  if (!window.IntersectionObserver || !toc.length) return;
  const visible = new Map();
  const links = [...main.querySelectorAll('.toc-list a')];
  state.observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting) visible.set(entry.target.id, entry.boundingClientRect.top);
      else visible.delete(entry.target.id);
    }
    const active = [...visible.entries()].sort((a, b) => a[1] - b[1])[0]?.[0];
    if (!active) return;
    for (const anchor of links) {
      if (anchor.dataset.tocTarget === active) anchor.setAttribute('aria-current', 'location');
      else anchor.removeAttribute('aria-current');
    }
  }, { root: mobile.matches ? null : pane, rootMargin: '0px 0px -60% 0px' });
  for (const item of toc) {
    const heading = document.getElementById(item.id);
    if (heading) state.observer.observe(heading);
  }
}


export { renderReader, saveReadingPosition, scheduleSave, hashTarget };
