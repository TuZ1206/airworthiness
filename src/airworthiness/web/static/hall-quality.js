import { main, announcer, kinds, state, el, list, number, count, chapterNumber, chapterURL, resourceURL, link, badge, sectionHeading, loading, empty, errorBox, api, overview, renderRail, route } from './hall-core.js';


function reportTable(chapters) {
  const columns = [['章节', null], ['资料', 'count'], ['网页正文', 'fulltext_count'], ['文档正文', 'extracted_count'], ['整理摘录', 'excerpt_count'], ['官方来源', 'metadata_count']];
  return el('div', { class: 'table-scroll', tabindex: '0', role: 'region', 'aria-label': '各章收录统计，可横向滚动' },
    el('table', { class: 'report-table' },
      el('caption', { class: 'sr-only' }, '按章节与收录类型统计资料数量'),
      el('thead', {}, el('tr', {}, columns.map(([title, key]) => el('th', { scope: 'col', class: key ? 'numeric' : '' }, title)))),
      el('tbody', {}, chapters.map(chapter => el('tr', {},
        el('td', {}, link(`${chapterNumber(chapter.id)} · ${chapter.title}`, chapterURL(chapter.id, '', ''))),
        columns.slice(1).map(([, key]) => el('td', { class: 'numeric' }, count(chapter[key]))))))));
}

function reportList(items, type) {
  const isGap = type === 'gap';
  const rows = el('ul', { class: isGap ? 'gap-list' : 'issue-list' });
  const input = el('input', { id: `${type}-search`, class: 'file-filter', type: 'search', placeholder: '按标识、标题或说明筛选', autocomplete: 'off' });
  const status = el('span', { class: 'review-label', 'aria-live': 'polite' });
  function render() {
    const term = input.value.trim().toLocaleLowerCase();
    const filtered = items.filter(item => `${item.source_id || ''} ${item.title || ''} ${item.reason || item.message || ''}`.toLocaleLowerCase().includes(term));
    status.textContent = `${filtered.length} / ${items.length} 项`;
    rows.replaceChildren(...filtered.map(item => el('li', { class: isGap ? 'gap-item' : 'issue-item' },
      el('div', {}, item.source_id ? link(item.title || item.source_id, resourceURL(item, '')) : el('span', {}, item.title || '收录记录'),
        item.title && item.source_id ? el('small', {}, item.source_id) : null,
        item.content_kind ? el('div', { class: 'tag-group' }, badge(item.content_kind)) : null),
      el('p', {}, isGap ? item.reason || '待补充完整正文。' : item.message || '待补充检查说明。'))));
    if (!filtered.length) rows.append(el('li', {}, empty(term ? '没有匹配的记录' : isGap ? '当前报告未列出缺失条目' : '当前报告未列出检查问题',
      term ? '试试其他关键词。' : '请按资料名称或编号查找。')));
  }
  input.addEventListener('input', render);
  render();
  return el('div', {}, el('div', { class: 'quality-filter' }, el('label', { for: input.id }, '筛选记录'), input, status), rows);
}

function reportDate(value) {
  if (!value) return '未注明';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false });
}

async function renderQuality(signal, generation) {
  const content = el('div', {}, loading('正在读取收录质量报告…'));
  const page = el('div', { class: 'page-width quality-page' },
    el('header', { class: 'quality-header' },
      el('div', {}, el('p', { class: 'eyebrow' }, 'COLLECTION / QUALITY REPORT'), el('h1', {}, '收录质量与缺失清单'),
        el('p', {}, '查看各章资料范围与正文可用情况。来源登记包含跨章重复引用。')),
      el('button', { type: 'button', class: 'button', onclick: () => { state.overview = null; route(); } }, '刷新报告 ↻')), content);
  main.replaceChildren(page);
  const railTask = overview(signal).then(data => { if (generation === state.generation) renderRail(data); }).catch(() => {});
  try {
    const data = await api('/api/quality', signal);
    if (generation !== state.generation) return;
    const totals = data.totals || {};
    const chapters = list(data.chapters);
    const gaps = list(data.gaps);
    const issues = list(data.issues);
    const excerpt = number(totals.excerpt);
    const metadata = number(totals.metadata);
    const incomplete = excerpt === null || metadata === null ? null : excerpt + metadata;
    const metrics = [['来源登记（含跨章引用）', totals.sources], ...Object.entries(kinds).map(([kind, label]) => [label, totals[kind]])];
    content.replaceChildren(
      el('p', { class: 'report-time' }, `报告生成时间：${reportDate(data.generated_at)}`),
      el('dl', { class: 'quality-metrics' }, metrics.map(([label, value]) => el('div', { class: 'quality-metric' }, el('dt', {}, label), el('dd', {}, count(value))))),
      el('aside', { class: 'content-notice' },
        el('strong', {}, `${count(incomplete)} 份资料未收录完整正文 · ${count(totals.extracted)} 份文档正文`),
        el('p', {}, `未收录完整正文数量为整理摘录与官方来源入口之和。本次报告列出 ${gaps.length} 项缺失记录、${issues.length} 项检查问题。`)),
      el('section', { class: 'quality-section', 'aria-label': '各章收录情况' }, sectionHeading('各章收录情况', `${chapters.length} 个章节`),
        chapters.length ? reportTable(chapters) : empty('暂无章节统计', '当前质量报告未返回各章统计。')),
      el('section', { class: 'quality-section', 'aria-label': '正文缺失清单' }, sectionHeading('正文缺失清单', `${gaps.length} 项`),
        el('p', { class: 'quality-explainer' }, '按报告列出缺失范围与原因。点击资料名称可查看已收录信息及官方来源。'), reportList(gaps, 'gap')),
      el('section', { class: 'quality-section', 'aria-label': '收录检查问题' }, sectionHeading('收录检查问题', `${issues.length} 项`), reportList(issues, 'issue')));
    announcer.textContent = `收录质量报告：${gaps.length} 项缺失记录，${issues.length} 项检查问题`;
  } catch (error) {
    if (generation === state.generation && !signal.aborted) content.replaceChildren(errorBox(error, () => route()));
  }
  await railTask;
}


export { renderQuality };
