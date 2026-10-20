import { main, announcer, kinds, statuses, state, el, number, count, chapterNumber, query, chapterURL, resourceURL, link, officialLink, sectionHeading, loading, empty, errorBox, api, overview, renderRail, selectField, updateChapterSelect, route, navigate } from './hall-core.js';
import { highlight } from './hall-content.js';
import { staticMode } from './hall-core.js';

function homeSearch(params) {
  const chapter = selectField('filter-chapter', '章节', 'chapter', [['', '全部章节']], params.get('chapter'));
  const status = selectField('filter-status', '效力', 'status', [['', '全部效力'], ...Object.entries(statuses)], params.get('status'));
  const kind = selectField('filter-kind', '收录', 'content_kind', [['', '全部收录类型'], ...Object.entries(kinds)], params.get('content_kind'));
  const input = el('input', { id: 'resource-search', type: 'search', name: 'q', value: query(), maxlength: '200', placeholder: '搜索标题、文号或正文关键词', autocomplete: 'off' });
  const form = el('form', { class: 'search-form', role: 'search', 'aria-label': '检索馆藏资源' },
    el('label', { for: 'resource-search', class: 'sr-only' }, '检索资源'),
    el('div', { class: 'search-line' }, el('span', { class: 'search-symbol', 'aria-hidden': 'true' }), input,
      el('button', { type: 'submit', class: 'button button-primary' }, '检索', el('span', { 'aria-hidden': 'true' }, '→'))),
    el('div', { class: 'filter-line' }, chapter.field, status.field, kind.field,
      el('button', { type: 'button', class: 'text-button', onclick: () => navigate('/#resources') }, '清除筛选')));
  form.addEventListener('submit', event => {
    event.preventDefault();
    const next = new URLSearchParams();
    for (const [key, value] of new FormData(form)) if (String(value).trim()) next.set(key, String(value).trim());
    navigate(`/${next.size ? `?${next}` : ''}#resources`);
  });
  for (const select of [chapter.select, status.select, kind.select]) select.addEventListener('change', () => form.requestSubmit());
  if (state.overview) updateChapterSelect(chapter.select, state.overview.chapters, params.get('chapter'));
  return { form, chapterSelect: chapter.select };
}

function chapterIndex(chapters) {
  if (!chapters.length) return empty('章节尚未入库', '章节资料准备完成后会显示在这里。');
  return el('ol', { class: 'chapter-list' }, chapters.map(chapter => el('li', {},
    link([
      el('span', { class: 'chapter-number', 'aria-hidden': 'true' }, chapterNumber(chapter.id)),
      el('div', {}, el('h3', {}, chapter.title), el('p', {}, `${count(chapter.count)} 条来源 · ${count((number(chapter.fulltext_count) || 0) + (number(chapter.extracted_count) || 0))} 份可读正文`)),
      el('span', { class: 'entry-arrow', 'aria-hidden': 'true' }, '↗')
    ], chapterURL(chapter.id, '', ''), { class: 'chapter-entry', title: chapter.description || chapter.title }))));
}

function resourceRow(resource, searchTerm) {
  const title = link(resource.title || resource.source_id, resourceURL(resource, searchTerm));
  const snippet = resource.snippet ? el('p', { class: 'resource-snippet' }, resource.snippet) : null;
  highlight(title, searchTerm);
  if (snippet) highlight(snippet, searchTerm);
  return el('li', { class: 'resource-row' },
    el('div', { class: 'resource-overline' }, el('span', { class: 'source-id' }, resource.source_id),
      el('span', { class: 'overline-divider', 'aria-hidden': 'true' }, '/'),
      el('span', {}, resource.chapter_title || resource.chapter_id),
      resource.document_code ? el('span', {}, `· ${resource.document_code}`) : null,
      resource.publish_date ? el('time', {}, resource.publish_date) : null),
    el('h3', {}, title), snippet,
    el('div', { class: 'resource-bottom' }, officialLink(resource.url)));
}

function pagination(data, params) {
  const page = Math.max(1, number(data.page) || 1);
  const pages = number(data.pages) || 0;
  const total = number(data.total) || 0;
  const size = number(data.page_size) || 20;
  const go = target => {
    const next = new URLSearchParams(params);
    next.set('page', String(target));
    navigate(`/?${next}#resources`);
  };
  const controls = el('div', { class: 'page-buttons' },
    el('button', { type: 'button', class: 'page-button', disabled: page <= 1, onclick: () => go(page - 1), 'aria-label': '上一页' }, '←'));
  const visible = new Set([1, pages, page - 1, page, page + 1].filter(value => value > 0 && value <= pages));
  let previous = 0;
  for (const value of [...visible].sort((a, b) => a - b)) {
    if (previous && value - previous > 1) controls.append(el('span', { class: 'page-ellipsis', 'aria-hidden': 'true' }, '…'));
    controls.append(el('button', { type: 'button', class: 'page-button', 'aria-label': `第 ${value} 页`,
      'aria-current': value === page ? 'page' : null, onclick: () => go(value) }, value));
    previous = value;
  }
  controls.append(el('button', { type: 'button', class: 'page-button', disabled: page >= pages, onclick: () => go(page + 1), 'aria-label': '下一页' }, '→'));
  return el('nav', { class: 'pagination', 'aria-label': '资源分页' },
    el('span', {}, total ? `显示 ${(page - 1) * size + 1}–${Math.min(page * size, total)} / 共 ${count(total)} 条来源` : '暂无资源'), controls);
}

async function renderHome(signal, generation) {
  const params = new URLSearchParams(location.search);
  const search = homeSearch(params);
  const chapters = el('div', {}, loading('正在读取章节…'));
  const results = el('div', { 'aria-live': 'polite', 'aria-busy': 'true' }, loading('正在检索资料…'));
  const resultCount = el('small', {}, '读取中');
  const resultHeading = sectionHeading('馆藏资源');
  resultHeading.append(resultCount);
  main.replaceChildren(
    el('section', { class: 'page-width home-hero', 'aria-labelledby': 'home-title' },
      el('div', {}, el('p', { class: 'eyebrow' }, 'AIRWORTHINESS / RESOURCE HALL'),
        el('h1', { id: 'home-title' }, staticMode ? '适航法规资源馆' : '适航离线资源馆'),
        el('p', { class: 'hero-footnote' }, el('span', {}, '复合材料适航'), staticMode ? '在线验收 · 按章索引 · 来源可溯' : '本地收录 · 按章索引 · 来源可溯'),
        staticMode ? el('p', { class: 'hero-footnote' }, '点击章节可查看适航资料；PDF 原件请从官方来源打开。') : null)),
    el('section', { class: 'search-section', 'aria-label': '资源检索与筛选' }, el('div', { class: 'page-width' }, search.form)),
    el('div', { class: 'page-width home-body' },
      el('section', { id: 'chapters', class: 'chapter-index', tabindex: '-1', 'aria-label': '九章索引' },
        sectionHeading('九章索引', 'CHAPTERS'), chapters,
        el('p', { class: 'chapter-index-note' }, '选择章节进入导读；正文、目录与术语在同一阅读界面中查看。')),
      el('section', { id: 'resources', class: 'resource-area', tabindex: '-1', 'aria-label': '检索结果' }, resultHeading, results)));

  const current = () => generation === state.generation;
  const requestParams = new URLSearchParams();
  for (const key of ['q', 'chapter', 'status', 'content_kind']) if (params.get(key)) requestParams.set(key, params.get(key));
  requestParams.set('page', String(Math.max(1, number(params.get('page')) || 1)));
  requestParams.set('page_size', '20');

  await Promise.all([
    overview(signal).then(data => {
      if (!current()) return;
      chapters.replaceChildren(chapterIndex(data.chapters));
      updateChapterSelect(search.chapterSelect, data.chapters, params.get('chapter'));
      renderRail(data);
    }).catch(error => {
      if (!current() || signal.aborted) return;
      chapters.replaceChildren(errorBox(error, () => route(), true));
    }),
    api(`/api/resources?${requestParams}`, signal).then(data => {
      if (!current()) return;
      if (!Array.isArray(data.items)) throw new Error('Invalid resources');
      resultCount.textContent = `${count(data.total)} 条来源`;
      const filtersActive = ['q', 'chapter', 'status', 'content_kind'].some(key => params.get(key));
      const description = query() ? `“${query()}” 的检索结果` : filtersActive ? '按当前条件筛选' : '全部收录资料';
      results.replaceChildren(el('p', { class: 'result-description' }, `${description} · 每页 20 条来源${staticMode ? ' · 按来源编号排序' : ''}`));
      if (!data.items.length) {
        const beyond = (number(data.page) || 1) > 1;
        results.append(empty(beyond ? '这一页没有资料' : filtersActive ? '没有匹配的资源' : '资源尚未入库',
          beyond ? '当前页码超出了结果范围，请返回第一页。' : filtersActive ? '试试更短的关键词，或调整章节、效力和收录类型。' : '本地资源入库后，会显示在这里。',
          beyond ? el('button', { type: 'button', class: 'button', onclick: () => { params.delete('page'); navigate(`/?${params}#resources`); } }, '返回第一页') :
            filtersActive ? el('button', { type: 'button', class: 'button', onclick: () => navigate('/#resources') }, '清除筛选') : null));
      } else {
        results.append(el('ol', { class: 'resource-list' }, data.items.map(item => resourceRow(item, query()))), pagination(data, params));
      }
      announcer.textContent = `找到 ${count(data.total)} 条来源`;
    }).catch(error => {
      if (!current() || signal.aborted) return;
      resultCount.textContent = '读取失败';
      results.replaceChildren(errorBox(error, () => route()));
    }).finally(() => { if (current()) results.setAttribute('aria-busy', 'false'); })
  ]);
}


export { renderHome };
