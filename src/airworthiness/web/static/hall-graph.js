/* Chapter graph preview: guide branches are navigation; CSV edges carry evidence. */
import { el, list, link, resourceURL } from './hall-core.js';

const kindName = { law: '法规', norm: '规范', concept: '概念', process: '过程', material: '材料' };
const evidenceName = { fulltext: '网页正文', extracted: '提取正文待校对', excerpt: '摘录待核', metadata: '仅状态信息' };

function renderChapterGraph(chapter, inDocument = false) {
  const graph = chapter.graph;
  if (!graph?.nodes?.length) return null;
  const nodes = new Map(list(graph.nodes).map(node => [node.node_id, node]));
  const relations = list(graph.relations);
  const root = el('section', { id: 'chapter-graph', class: 'chapter-graph', 'aria-labelledby': 'chapter-graph-title' });
  const details = el('details', { class: 'graph-disclosure', open: !inDocument });
  const tree = el('div', { class: 'graph-tree', role: 'group', 'aria-label': '按专题浏览节点' });
  const panel = el('aside', { class: 'graph-inspector', 'aria-live': 'polite' });
  let activeId = '';
  const nodeButtons = new Map();

  function selectNode(id) {
    const node = nodes.get(id);
    if (!node) return;
    activeId = id;
    const connected = relations.filter(edge => edge.from_node_id === id || edge.to_node_id === id);
    const relatedIds = new Set(connected.map(edge => edge.from_node_id === id ? edge.to_node_id : edge.from_node_id));
    for (const [nodeId, button] of nodeButtons) {
      button.classList.toggle('is-active', nodeId === id);
      button.classList.toggle('is-related', relatedIds.has(nodeId));
      button.setAttribute('aria-pressed', nodeId === id ? 'true' : 'false');
    }
    const source = { source_id: node.source_id, chapter_id: chapter.id };
    const flags = [evidenceName[node.source_kind] || '来源状态待核', node.source_status === 'effective' ? '登记有效' : '效力待核', '待专业审核'];
    panel.replaceChildren(
      el('p', { class: 'graph-inspector-kicker' }, node.node_id, ' · ', kindName[node.display_type] || '节点'),
      el('h3', {}, node.name), node.code ? el('p', { class: 'graph-node-code' }, node.code) : null,
      el('p', { class: 'graph-node-summary' }, node.summary || '节点说明待核对。'),
      el('p', { class: 'graph-node-flags' }, flags.map(flag => el('span', {}, flag))),
      el('p', { class: 'graph-locator' }, `来源定位：${node.source_id} · ${node.source_locator || '条款待定位'}`),
      link('查看来源资料 ↗', resourceURL(source, ''), { class: 'graph-source-link' }),
      el('h4', {}, `关联关系 · ${connected.length}`),
      connected.length ? el('ul', { class: 'graph-edge-list' }, connected.map(edge => {
        const outgoing = edge.from_node_id === id;
        const peerId = outgoing ? edge.to_node_id : edge.from_node_id;
        const peer = nodes.get(peerId);
        return el('li', {},
          el('button', { type: 'button', class: 'graph-edge-button', onclick: () => {
            selectNode(peerId);
            nodeButtons.get(peerId)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
          } }, `${outgoing ? '→' : '←'} ${edge.type} · ${peer?.name || peerId}`),
          el('p', { class: 'graph-edge-evidence' }, `${edge.source_id} · ${edge.evidence || '证据待核'} · ${evidenceName[edge.source_kind] || '来源待核'}`));
      })) : el('p', { class: 'graph-empty' }, '此节点在现有关系表中没有关联项。'));
  }

  for (const section of list(graph.sections)) {
    const branchNodes = list(section.node_ids).map(id => nodes.get(id)).filter(Boolean);
    if (!branchNodes.length) continue;
    const branch = el('section', { class: 'graph-branch' },
      el('h3', { class: 'graph-branch-title' }, section.title),
      el('ul', { class: 'graph-node-list' }, branchNodes.map(node => {
        const button = el('button', { type: 'button', class: `graph-node graph-node-${node.display_type || 'concept'}`,
          'aria-pressed': 'false', onclick: () => selectNode(node.node_id) },
          el('span', { class: 'graph-node-name' }, node.name),
          el('small', {}, node.node_id, ' · ', evidenceName[node.source_kind] || '待核'));
        nodeButtons.set(node.node_id, button);
        return el('li', {}, button);
      })));
    tree.append(branch);
  }
  const summary = el('summary', { class: 'graph-summary' },
    el('span', { class: 'graph-summary-title', id: 'chapter-graph-title' }, '本章知识图谱'),
    el('span', { class: 'graph-summary-count' }, `${nodes.size} 个节点 · ${relations.length} 条关联`),
    el('span', { class: 'graph-summary-action' }, '展开／收起'));
  details.append(summary,
    el('p', { class: 'graph-intro' }, `专题树用于查找重要节点；选择节点可查看关系表中的关联及来源定位。专题分组不表示法规的上下位关系。仅有状态页、摘录或效力不明的来源不进入此图谱（本章排除 ${graph.omitted_nodes || 0} 个节点）；提取正文仍待校对，全部关系待专业审核。`),
    el('div', { class: 'graph-layout' },
      el('div', { class: 'graph-tree-wrap' }, el('div', { class: 'graph-root' }, `第 ${String(chapter.id).slice(2)} 章 · ${chapter.title}`), tree), panel));
  root.append(details);
  selectNode(graph.nodes[0].node_id);
  return root;
}

export { renderChapterGraph };
