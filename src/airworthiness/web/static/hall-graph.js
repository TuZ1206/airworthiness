/* Circles are source-backed nodes; colored lines are actual CSV relations. */
import { el, list, link, resourceURL } from './hall-core.js';

const kindName = { law: '法规', norm: '规范', concept: '概念', process: '过程', material: '材料' };
const SVG_NS = 'http://www.w3.org/2000/svg';
// Each color describes a relation, never an inferred property of either endpoint.
const relationColors = {
  依据: '#2859a3', 规定: '#165f88', 细化: '#087e8b', 操作化: '#a5621b',
  验证: '#2f7957', 支撑: '#648227', 传递: '#328a73', 约束: '#b34859',
  衔接: '#6261a7', 触发: '#b85a32', 包含: '#6f7190', 责任锚定: '#825378',
  延伸监管: '#8b6940', 边界: '#8c5155', 补充: '#936ba2', 前置: '#935b2c'
};
const relationColor = type => relationColors[type] || '#607688';
const groupFor = node => {
  if (['law', 'norm', 'article', 'standard', 'guidance'].includes(node.display_type)) return 'source';
  if (['process', 'method', 'control', 'procedure', 'inspection', 'responsibility', 'interface'].includes(node.display_type)) return 'activity';
  if (['evidence', 'record'].includes(node.display_type)) return 'evidence';
  return 'concept';
};
const groupNames = { source: '法规与资料', concept: '概念与要求', activity: '过程与方法', evidence: '证据与记录' };
const groupCenters = (cellWidth, cellHeight, gap, padding) => ({
  source: { x: padding + cellWidth / 2, y: padding + cellHeight / 2 },
  concept: { x: padding + cellWidth * 1.5 + gap, y: padding + cellHeight / 2 },
  activity: { x: padding + cellWidth * 1.5 + gap, y: padding + cellHeight * 1.5 + gap },
  evidence: { x: padding + cellWidth / 2, y: padding + cellHeight * 1.5 + gap }
});

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

function clusterOutline(points) {
  const corners = points.flatMap(point => [
    { x: point.x - 140, y: point.y - 115 }, { x: point.x + 140, y: point.y - 115 },
    { x: point.x + 140, y: point.y + 135 }, { x: point.x - 140, y: point.y + 135 }
  ]).sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (a, b, c) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  const lower = [], upper = [];
  for (const point of corners) {
    while (lower.length > 1 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) lower.pop();
    lower.push(point);
  }
  for (const point of [...corners].reverse()) {
    while (upper.length > 1 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) upper.pop();
    upper.push(point);
  }
  const hull = lower.slice(0, -1).concat(upper.slice(0, -1));
  const middle = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  const start = middle(hull[hull.length - 1], hull[0]);
  const path = `M ${start.x} ${start.y} ${hull.map((point, index) => {
    const next = middle(point, hull[(index + 1) % hull.length]);
    return `Q ${point.x} ${point.y} ${next.x} ${next.y}`;
  }).join(' ')} Z`;
  const bounds = { left: Math.min(...corners.map(point => point.x)), right: Math.max(...corners.map(point => point.x)),
    top: Math.min(...corners.map(point => point.y)), bottom: Math.max(...corners.map(point => point.y)) };
  return { path, bounds, labelX: (bounds.left + bounds.right) / 2, labelY: bounds.top + 31 };
}

// Deterministic, offline node-link layout. No inferred chapter/topic edges.
function layoutGraph(graph) {
  const nodes = list(graph.nodes);
  const ids = new Set(nodes.map(node => node.node_id));
  const edges = list(graph.relations).filter(edge => ids.has(edge.from_node_id) && ids.has(edge.to_node_id));
  const groupCounts = new Map();
  for (const node of nodes) groupCounts.set(groupFor(node), (groupCounts.get(groupFor(node)) || 0) + 1);
  const largestGroup = Math.max(1, ...groupCounts.values());
  const cellWidth = Math.max(760, Math.ceil(Math.sqrt(largestGroup) * 180));
  const cellHeight = Math.max(660, Math.ceil(Math.sqrt(largestGroup) * 155));
  const gap = 120, padding = 70;
  const width = cellWidth * 2 + gap + padding * 2;
  const height = cellHeight * 2 + gap + padding * 2;
  const centers = groupCenters(cellWidth, cellHeight, gap, padding);
  const limitX = cellWidth / 2 - 150, limitY = cellHeight / 2 - 150;
  const degree = new Map(nodes.map(node => [node.node_id, 0]));
  for (const edge of edges) {
    degree.set(edge.from_node_id, degree.get(edge.from_node_id) + 1);
    degree.set(edge.to_node_id, degree.get(edge.to_node_id) + 1);
  }
  const ordered = [...nodes].sort((a, b) =>
    degree.get(b.node_id) - degree.get(a.node_id) || a.node_id.localeCompare(b.node_id));
  const points = new Map();
  const groupIndex = new Map();
  ordered.forEach(node => {
    const group = groupFor(node), index = groupIndex.get(group) || 0, center = centers[group];
    groupIndex.set(group, index + 1);
    const angle = index * 2.399963229728653;
    const radius = index ? Math.sqrt(index) * 74 : 0;
    points.set(node.node_id, { x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius, degree: degree.get(node.node_id) });
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
      const center = centers[groupFor(node)];
      point.x = Math.max(center.x - limitX, Math.min(center.x + limitX,
        point.x + delta.x + (center.x - point.x) * .018));
      point.y = Math.max(center.y - limitY, Math.min(center.y + limitY,
        point.y + delta.y + (center.y - point.y) * .018));
    }
  }
  return { width, height, points, degree, centers, hubId: ordered[0]?.node_id || null, edges };
}

function renderChapterGraph(chapter, inDocument = false) {
  const graph = chapter.graph;
  if (!graph?.nodes?.length) return null;
  const nodes = new Map(list(graph.nodes).map(node => [node.node_id, node]));
  const layout = layoutGraph(graph);
  const relations = layout.edges;
  const root = el('section', { id: 'chapter-graph', class: 'chapter-graph', 'aria-labelledby': 'chapter-graph-title' });
  const details = el('details', { class: 'graph-disclosure', open: !inDocument });
  const stage = el('div', { class: 'graph-stage', role: 'group', 'aria-label': '资料关系索引图' });
  stage.style.width = `${layout.width}px`;
  stage.style.height = `${layout.height}px`;
  const grouped = new Map();
  for (const node of nodes.values()) {
    const group = groupFor(node);
    if (!grouped.has(group)) grouped.set(group, []);
    grouped.get(group).push(layout.points.get(node.node_id));
  }
  const clusterLayer = svgEl('svg', { class: 'graph-cluster-layer', width: layout.width, height: layout.height,
    viewBox: `0 0 ${layout.width} ${layout.height}`, 'aria-hidden': 'true' });
  for (const [group, points] of grouped) {
    const outline = clusterOutline(points);
    clusterLayer.append(svgEl('path', { d: outline.path, class: `graph-cluster-shape graph-cluster-${group}` }));
    const label = svgEl('text', { x: outline.labelX, y: outline.labelY,
      class: 'graph-cluster-label', 'text-anchor': 'middle' });
    label.textContent = `${groupNames[group]} · ${points.length}`;
    clusterLayer.append(label);
  }
  stage.append(clusterLayer);
  const svg = svgEl('svg', { class: 'graph-lines', width: layout.width, height: layout.height,
    viewBox: `0 0 ${layout.width} ${layout.height}`, 'aria-hidden': 'true' });
  const edgeEls = [];
  for (const edge of relations) {
    const a = layout.points.get(edge.from_node_id), b = layout.points.get(edge.to_node_id);
    const line = svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      class: 'graph-relation-line', 'data-from': edge.from_node_id, 'data-to': edge.to_node_id,
      'data-relation-type': edge.type });
    line.style.setProperty('--relation-color', relationColor(edge.type));
    edgeEls.push({ edge, line });
    svg.append(line);
  }
  stage.append(svg);
  const nodeButtons = new Map();
  const panel = el('aside', { class: 'graph-inspector', 'aria-live': 'polite' });
  for (const node of nodes.values()) {
    const point = layout.points.get(node.node_id);
    const button = el('button', { type: 'button',
      class: `graph-node graph-node-${node.display_type || 'concept'} graph-node-group-${groupFor(node)}`,
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
    panel.replaceChildren(
      el('p', { class: 'graph-inspector-kicker' }, node.node_id, ' · ', kindName[node.display_type] || '节点'),
      el('h3', {}, node.name), node.code ? el('p', { class: 'graph-node-code' }, node.code) : null,
      node.summary ? el('p', { class: 'graph-node-summary' }, node.summary) : null,
      el('p', { class: 'graph-locator' }, `来源定位：${node.source_id} · ${node.source_locator || '条款待定位'}`),
      link('查看来源资料 ↗', resourceURL({ source_id: node.source_id, chapter_id: chapter.id }, ''), { class: 'graph-source-link' }),
      el('h4', {}, `关联关系 · ${connected.length}`),
      connected.length ? el('ul', { class: 'graph-edge-list' }, connected.map(edge => {
        const outgoing = edge.from_node_id === id;
        const peerId = outgoing ? edge.to_node_id : edge.from_node_id;
        const peer = nodes.get(peerId);
        const item = el('li', {},
          el('button', { type: 'button', class: 'graph-edge-button', onclick: () => {
            selectNode(peerId);
            nodeButtons.get(peerId)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
          } }, el('span', { class: 'graph-edge-swatch', 'aria-hidden': 'true' }),
          `${outgoing ? '→' : '←'} ${edge.type} · ${peer?.name || peerId}`),
          el('p', { class: 'graph-edge-evidence' }, `${edge.source_id} · ${edge.evidence}`));
        item.style.setProperty('--relation-color', relationColor(edge.type));
        return item;
      })) : el('p', { class: 'graph-empty' }, '此节点在现有关系表中没有关联项。'));
  }

  const relationLegend = [...new Set(relations.map(edge => edge.type))].map(type => {
    const item = el('span', { class: 'graph-key-item' },
      el('span', { class: 'graph-key-swatch', 'aria-hidden': 'true' }), type);
    item.style.setProperty('--relation-color', relationColor(type));
    return item;
  });

  const wrap = el('div', { class: 'graph-tree-wrap' }, stage);
  const zoomLabel = el('span', { class: 'graph-zoom-label' }, '100%');
  let zoom = 1, manualZoom = false;
  const setZoom = value => {
    zoom = Math.max(.35, Math.min(1.6, Math.round(value * 100) / 100));
    stage.style.zoom = String(zoom);
    zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
  };
  const fit = () => {
    if (!wrap.clientWidth || !wrap.clientHeight) return;
    setZoom(Math.min(1, (wrap.clientWidth - 18) / layout.width, (wrap.clientHeight - 18) / layout.height));
    wrap.scrollTo(0, 0);
  };
  const controls = el('div', { class: 'graph-controls' },
    el('span', { class: 'graph-controls-title' }, `全章网络 · ${nodes.size} 个节点`),
    el('button', { type: 'button', 'aria-label': '缩小图谱', onclick: () => { manualZoom = true; setZoom(zoom - .15); } }, '−'),
    zoomLabel,
    el('button', { type: 'button', 'aria-label': '放大图谱', onclick: () => { manualZoom = true; setZoom(zoom + .15); } }, '+'),
    el('button', { type: 'button', class: 'graph-fit-button', onclick: () => { manualZoom = false; fit(); } }, '适应视图'));

  details.append(
    el('summary', { class: 'graph-summary' },
    el('span', { class: 'graph-summary-title', id: 'chapter-graph-title' }, '本章概念关联图'),
      el('span', { class: 'graph-summary-count' }, `${nodes.size} 个节点 · ${relations.length} 条关联`),
      el('span', { class: 'graph-summary-action' }, '展开／收起')),
    el('p', { class: 'graph-intro' }, '本章全部可展示节点按概念、过程和法规资料分组；彩色连线表示已记录的关系。点击节点查看关系证据和来源定位。'),
    controls,
    el('div', { class: 'graph-key', 'aria-label': '关联类型颜色图例' },
      el('span', { class: 'graph-key-label' }, '关联类型'), relationLegend,
      el('span', { class: 'graph-key-pan' }, '先看全图，再放大查看节点；点击节点可突出关联')),
    el('div', { class: 'graph-layout' }, wrap, panel));
  root.append(details);
  panel.replaceChildren(el('p', { class: 'graph-inspector-kicker' }, '全章概览'),
    el('h3', {}, `${nodes.size} 个节点 · ${relations.length} 条关系`),
    el('p', { class: 'graph-node-summary' }, '点击图中的任一节点，可查看与它直接相连的关系、证据和来源定位。'));
  details.addEventListener('toggle', () => { if (details.open && !manualZoom) requestAnimationFrame(fit); });
  requestAnimationFrame(() => { if (details.open && !manualZoom) fit(); });
  return root;
}

export { renderChapterGraph, layoutGraph };
