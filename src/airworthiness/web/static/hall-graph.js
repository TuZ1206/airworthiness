/* Circles are source-backed nodes; lines are actual CSV relations. */
import { el, list, link, resourceURL } from './hall-core.js';

const kindName = { law: '法规', norm: '规范', concept: '概念', process: '过程', material: '材料' };
const evidenceName = { fulltext: '网页正文', extracted: '提取正文待校对' };
const SVG_NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

// Deterministic, offline node-link layout. No inferred chapter/topic edges.
function layoutGraph(graph) {
  const nodes = list(graph.nodes);
  const ids = new Set(nodes.map(node => node.node_id));
  const edges = list(graph.relations).filter(edge => ids.has(edge.from_node_id) && ids.has(edge.to_node_id));
  const count = nodes.length;
  const width = count > 36 ? 1360 : count > 24 ? 1200 : 1040;
  const height = count > 36 ? 1100 : count > 24 ? 940 : 800;
  const cx = width / 2, cy = height / 2;
  const degree = new Map(nodes.map(node => [node.node_id, 0]));
  for (const edge of edges) {
    degree.set(edge.from_node_id, degree.get(edge.from_node_id) + 1);
    degree.set(edge.to_node_id, degree.get(edge.to_node_id) + 1);
  }
  const ordered = [...nodes].sort((a, b) =>
    degree.get(b.node_id) - degree.get(a.node_id) || a.node_id.localeCompare(b.node_id));
  const points = new Map();
  ordered.forEach((node, index) => {
    const angle = index * 2.399963229728653;
    const radius = index ? Math.sqrt(index) * (count > 36 ? 92 : 82) : 0;
    points.set(node.node_id, { x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius, degree: degree.get(node.node_id) });
  });
  for (let iteration = 0; iteration < 420; iteration++) {
    const movement = new Map(nodes.map(node => [node.node_id, { x: 0, y: 0 }]));
    for (let i = 0; i < ordered.length; i++) {
      const a = points.get(ordered[i].node_id);
      for (let j = i + 1; j < ordered.length; j++) {
        const b = points.get(ordered[j].node_id);
        let dx = b.x - a.x, dy = b.y - a.y;
        if (!dx && !dy) { dx = 1; dy = 1; }
        const distance = Math.hypot(dx, dy);
        const near = Math.hypot(dx / 164, dy / 106);
        const strength = near < 1 ? (1 - near) * 9 : 1650 / (distance * distance + 3200);
        const ux = dx / distance * strength, uy = dy / distance * strength;
        movement.get(ordered[i].node_id).x -= ux;
        movement.get(ordered[i].node_id).y -= uy;
        movement.get(ordered[j].node_id).x += ux;
        movement.get(ordered[j].node_id).y += uy;
      }
    }
    for (const edge of edges) {
      const a = points.get(edge.from_node_id), b = points.get(edge.to_node_id);
      const dx = b.x - a.x, dy = b.y - a.y, distance = Math.max(1, Math.hypot(dx, dy));
      const spring = Math.max(-1.5, Math.min(1.5, (distance - 205) * 0.004));
      movement.get(edge.from_node_id).x += dx / distance * spring;
      movement.get(edge.from_node_id).y += dy / distance * spring;
      movement.get(edge.to_node_id).x -= dx / distance * spring;
      movement.get(edge.to_node_id).y -= dy / distance * spring;
    }
    for (const node of ordered) {
      const point = points.get(node.node_id), delta = movement.get(node.node_id);
      const anchor = node === ordered[0] ? 0.035 : 0.0015;
      point.x = Math.max(96, Math.min(width - 96, point.x + delta.x + (cx - point.x) * anchor));
      point.y = Math.max(72, Math.min(height - 72, point.y + delta.y + (cy - point.y) * anchor));
    }
  }
  return { width, height, points, degree, hubId: ordered[0]?.node_id || null, edges };
}

function renderChapterGraph(chapter, inDocument = false) {
  const graph = chapter.graph;
  if (!graph?.nodes?.length) return null;
  const nodes = new Map(list(graph.nodes).map(node => [node.node_id, node]));
  const layout = layoutGraph(graph);
  const relations = layout.edges;
  const root = el('section', { id: 'chapter-graph', class: 'chapter-graph', 'aria-labelledby': 'chapter-graph-title' });
  const details = el('details', { class: 'graph-disclosure', open: !inDocument });
  const stage = el('div', { class: 'graph-stage', role: 'group', 'aria-label': '章节节点关系图' });
  stage.style.width = `${layout.width}px`;
  stage.style.height = `${layout.height}px`;
  const svg = svgEl('svg', { class: 'graph-lines', width: layout.width, height: layout.height,
    viewBox: `0 0 ${layout.width} ${layout.height}`, 'aria-hidden': 'true' });
  const edgeEls = [];
  for (const edge of relations) {
    const a = layout.points.get(edge.from_node_id), b = layout.points.get(edge.to_node_id);
    const line = svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      class: 'graph-relation-line', 'data-from': edge.from_node_id, 'data-to': edge.to_node_id });
    edgeEls.push({ edge, line });
    svg.append(line);
  }
  stage.append(svg);
  const nodeButtons = new Map();
  const panel = el('aside', { class: 'graph-inspector', 'aria-live': 'polite' });
  for (const node of nodes.values()) {
    const point = layout.points.get(node.node_id);
    const button = el('button', { type: 'button',
      class: `graph-node graph-node-${node.display_type || 'concept'}${node.node_id === layout.hubId ? ' graph-node-hub' : ''}`,
      title: `${node.name} · ${node.node_id}`,
      'aria-label': `${node.name}，${kindName[node.display_type] || '节点'}，查看关联`,
      'aria-pressed': 'false', onclick: () => selectNode(node.node_id) },
      el('span', { class: 'graph-node-dot', 'aria-hidden': 'true' }),
      el('span', { class: 'graph-node-text' }, node.name));
    button.style.left = `${point.x}px`;
    button.style.top = `${point.y}px`;
    nodeButtons.set(node.node_id, button);
    stage.append(button);
  }

  function selectNode(id) {
    const node = nodes.get(id);
    if (!node) return;
    const connected = relations.filter(edge => edge.from_node_id === id || edge.to_node_id === id);
    const relatedIds = new Set(connected.map(edge => edge.from_node_id === id ? edge.to_node_id : edge.from_node_id));
    for (const [nodeId, button] of nodeButtons) {
      button.classList.toggle('is-active', nodeId === id);
      button.classList.toggle('is-related', relatedIds.has(nodeId));
      button.classList.toggle('is-dim', nodeId !== id && !relatedIds.has(nodeId));
      button.setAttribute('aria-pressed', nodeId === id ? 'true' : 'false');
    }
    for (const { edge, line } of edgeEls) {
      line.classList.toggle('is-active', edge.from_node_id === id || edge.to_node_id === id);
      line.classList.toggle('is-dim', edge.from_node_id !== id && edge.to_node_id !== id);
    }
    const flags = [evidenceName[node.source_kind] || '来源状态待核', '登记有效', '待专业审核'];
    panel.replaceChildren(
      el('p', { class: 'graph-inspector-kicker' }, node.node_id, ' · ', kindName[node.display_type] || '节点'),
      el('h3', {}, node.name), node.code ? el('p', { class: 'graph-node-code' }, node.code) : null,
      el('p', { class: 'graph-node-summary' }, node.summary || '节点说明待核对。'),
      el('p', { class: 'graph-node-flags' }, flags.map(flag => el('span', {}, flag))),
      el('p', { class: 'graph-locator' }, `来源定位：${node.source_id} · ${node.source_locator || '条款待定位'}`),
      link('查看来源资料 ↗', resourceURL({ source_id: node.source_id, chapter_id: chapter.id }, ''), { class: 'graph-source-link' }),
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

  details.append(
    el('summary', { class: 'graph-summary' },
      el('span', { class: 'graph-summary-title', id: 'chapter-graph-title' }, '本章知识图谱'),
      el('span', { class: 'graph-summary-count' }, `${nodes.size} 个节点 · ${relations.length} 条关联`),
      el('span', { class: 'graph-summary-action' }, '展开／收起')),
    el('p', { class: 'graph-intro' }, `圆点是本章的真实节点，连线仅表示关系表中的实际关联；蓝色深浅区分节点类型。点击圆点可突出关联并查看证据。仅有状态页、摘录或效力不明的来源不进入图谱（本章排除 ${graph.omitted_nodes || 0} 个节点）。全部关系仍待专业审核。`),
    el('p', { class: 'graph-key' }, el('span', { class: 'graph-key-relation' }, '连线：已有关系'),
      el('span', { class: 'graph-key-focus' }, '深蓝：当前节点及关联'),
      el('span', { class: 'graph-key-pan' }, '图幅较宽时可横向滚动')),
    el('div', { class: 'graph-layout' }, el('div', { class: 'graph-tree-wrap' }, stage), panel));
  root.append(details);
  selectNode(layout.hubId);
  return root;
}

export { renderChapterGraph, layoutGraph };
