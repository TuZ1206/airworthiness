/* Human-authored chapter knowledge map. This is intentionally separate from CSV relation indexing. */
import { el, list, link, resourceURL } from './hall-core.js';

const categoryLabels = {
  concept: '核心概念', regulation: '法规基础', procedure: '程序活动',
  evidence: '证据', standard: '标准', interface: '跨章接口'
};

function refLinks(refs, chapter) {
  return el('ul', { class: 'knowledge-source-list' }, list(refs).map(ref =>
    el('li', {}, link(`${ref.source_id} · ${ref.source_locator} ↗`,
      resourceURL({ source_id: ref.source_id, chapter_id: chapter.id }), { class: 'knowledge-source-link' }))));
}

function renderKnowledgeMap(map, chapter, inDocument = false) {
  const root = el('section', { id: 'knowledge-map', class: 'knowledge-map', 'aria-labelledby': 'knowledge-map-title' });
  const details = el('details', { class: 'knowledge-map-disclosure', open: !inDocument });
  const title = map?.title || '章节知识导图';
  details.append(el('summary', { class: 'knowledge-map-summary' },
    el('span', { id: 'knowledge-map-title' }, title),
    el('span', { class: 'knowledge-map-action' }, '展开／收起')));
  if (!map?.available) {
    details.append(el('p', { class: 'knowledge-map-empty' }, map?.message || '暂无已审核的章节知识导图。'));
    root.append(details);
    return root;
  }
  const nodes = new Map(list(map.nodes).map(node => [node.knowledge_node_id, node]));
  const relations = list(map.relations).filter(item => nodes.has(item.from_node_id) && nodes.has(item.to_node_id));
  const cards = el('div', { class: 'knowledge-node-list' });
  const inspector = el('aside', { class: 'knowledge-inspector', 'aria-live': 'polite' });
  const buttons = new Map();
  const select = id => {
    const node = nodes.get(id);
    if (!node) return;
    const connected = relations.filter(item => id === item.from_node_id || id === item.to_node_id);
    for (const [nodeId, button] of buttons) {
      button.classList.toggle('is-active', nodeId === id);
      button.setAttribute('aria-pressed', nodeId === id ? 'true' : 'false');
    }
    inspector.replaceChildren(
      el('p', { class: 'knowledge-inspector-kicker' }, `${node.knowledge_node_id} · ${categoryLabels[node.category] || node.category}`),
      el('h3', {}, node.name), el('p', {}, node.summary),
      el('h4', {}, '依据来源'), refLinks(node.source_refs, chapter),
      el('h4', {}, `已审核关系 · ${connected.length}`),
      connected.length ? el('ul', { class: 'knowledge-relation-list' }, connected.map(item => {
        const isFrom = item.from_node_id === id;
        const peer = nodes.get(isFrom ? item.to_node_id : item.from_node_id);
        return el('li', {}, el('button', { type: 'button', class: 'knowledge-peer', onclick: () => select(peer.knowledge_node_id) },
          `${isFrom ? '→' : '←'} ${item.type} · ${peer.name}`),
        refLinks(item.source_refs, chapter));
      })) : el('p', { class: 'knowledge-map-empty' }, '此节点暂无已审核关系。'));
  };
  for (const node of nodes.values()) {
    const button = el('button', { type: 'button', class: `knowledge-node knowledge-node-${node.category || 'concept'}`,
      'aria-pressed': 'false', onclick: () => select(node.knowledge_node_id) },
    el('span', { class: 'knowledge-node-category' }, categoryLabels[node.category] || node.category),
    el('strong', {}, node.name), el('span', {}, node.summary));
    buttons.set(node.knowledge_node_id, button);
    cards.append(button);
  }
  details.append(
    el('p', { class: 'knowledge-map-intro' }, '按章节知识结构组织核心概念、法规基础、程序活动与证据。仅显示已完成专业审核且能回链到有效正文的内容。'),
    el('div', { class: 'knowledge-map-layout' }, cards, inspector));
  root.append(details);
  select(nodes.keys().next().value);
  return root;
}

export { renderKnowledgeMap };
