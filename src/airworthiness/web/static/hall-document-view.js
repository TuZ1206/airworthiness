/* Original layout is the default for PDFs; extracted text is a reading aid. */
import { el, officialLink, basePath } from './hall-core.js';

function isOriginalPath(sourceId, path) {
  if (!/^CH\d{2}-S\d{3}$/.test(sourceId || '') || typeof path !== 'string') return false;
  const base = `/api/documents/${sourceId}/original`;
  return path.startsWith(base) && /^(?:\?index=(?:0|[1-9]\d*))?$/.test(path.slice(base.length));
}

function isStaticOriginalPath(sourceId, path, base = '') {
  if (!/^CH\d{2}-S\d{3}$/.test(sourceId || '') || typeof path !== 'string' ||
      !/^(?:\/[A-Za-z0-9_-]+)*$/.test(base)) return false;
  const prefix = `${base}/originals/${sourceId}/`;
  return path.startsWith(prefix) && /^(?:0|[1-9]\d*)\.pdf$/.test(path.slice(prefix.length));
}

function isOfficialPDFPath(path) {
  try {
    const url = new URL(path);
    return url.protocol === 'https:' && !url.username && !url.password && !url.port &&
      !url.search && !url.hash && /(?:^|\.)gov\.cn$/i.test(url.hostname) &&
      /\.pdf$/i.test(url.pathname);
  } catch { return false; }
}

function readableLabel(value) {
  return typeof value === 'string' && !/[\uFFFD\uE000-\uF8FF]/u.test(value) ? value : '';
}

function officialPDFs(doc) {
  const source = doc.body_provenance || {};
  const candidates = [...(Array.isArray(source.originals) ? source.originals : []), source];
  if (!source.source_id || source.source_id === doc.source_id) candidates.push(doc.uploaded_provenance || {});
  const seen = new Set();
  return candidates.flatMap(item => {
    const value = item.pdf_url || item.url;
    try {
      const url = new URL(value);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
          !/(?:^|\.)gov\.cn$/.test(url.hostname) || !/\.pdf$/i.test(url.pathname) || seen.has(url.href)) return [];
      seen.add(url.href);
      return [{ url: url.href, label: readableLabel(item.label) }];
    } catch { return []; }
  }).slice(0, 16);
}

function allowedOriginal(doc, path, base) {
  return doc.deployment_mode === 'static'
    ? isStaticOriginalPath(doc.source_id, path, base) : isOriginalPath(doc.source_id, path);
}

function initialDocumentMode(doc, originals, { search = '', hash = '', base = '' } = {}) {
  if (search || hash) return 'text';
  return doc.content_kind === 'extracted' &&
    originals.some(item => allowedOriginal(doc, item?.url, base) || isOfficialPDFPath(item?.url)) ? 'original' : 'text';
}

function pdfCandidates(doc, originals, base = '') {
  const candidates = doc.deployment_mode === 'static'
    ? Array.isArray(doc.static_originals) ? doc.static_originals : [] : originals;
  const verifiedFiles = (Array.isArray(candidates) ? candidates : [])
    .filter(item => allowedOriginal(doc, item?.url, base));
  return { verifiedFiles, files: verifiedFiles.length ? verifiedFiles : officialPDFs(doc)
    .filter(item => isOfficialPDFPath(item.url)) };
}

function createDocumentView({ doc, originals, content, tools, search = '', hash = '', onModeChange = () => {} }) {
  const online = doc.deployment_mode === 'static';
  // Only hash-verified, eligible local/site copies enter the frame. Government
  // sites can forbid framing, so an uncached remote file is link-only.
  const { files, verifiedFiles } = pdfCandidates(doc, originals, basePath);
  const shell = el('section', { class: 'document-view', 'aria-label': '文档内容' });
  const textPane = el('div', { class: 'document-text', id: 'document-text' });
  const extracted = doc.content_kind === 'extracted';
  if (extracted) {
    const lines = el('button', { type: 'button', class: 'text-button', 'aria-pressed': 'false' }, '保留提取换行');
    lines.addEventListener('click', () => {
      const preserve = content.classList.toggle('preserve-lines');
      lines.setAttribute('aria-pressed', String(preserve));
      lines.textContent = preserve ? '恢复自动换行' : '保留提取换行';
    });
    textPane.append(el('div', { class: 'text-reading-note' },
      el('p', {}, '提取文字仅辅助检索，不还原表格、公式或扫描版式；引用时请对照原件。'), lines));
  }
  if (!files.length && ['extracted', 'metadata'].includes(doc.content_kind)) {
    textPane.append(el('p', { class: 'original-missing' }, online
      ? '此在线快照未托管本文件的 PDF。文字仅辅助检索；表格、公式及完整版式请打开官方原件查看。'
      : '当前电脑未保存可用 PDF 原件。若文字排版仍不清晰，请打开官方来源查看。'));
  }
  textPane.append(tools, content);
  const originalPane = el('div', { class: 'document-original', id: 'document-original' });
  const actions = el('div', { class: 'document-actions' });
  const source = officialLink(doc.url, '官方来源 ↗');
  if (source) actions.append(source);
  if (!files.length) {
    for (const file of officialPDFs(doc)) {
      const anchor = officialLink(file.url, file.label ? `官方 PDF · ${file.label} ↗` : '官方 PDF 原件 ↗');
      if (anchor) actions.prepend(anchor);
    }
  }

  let frame = null;
  let selected = files[0];
  let mode = initialDocumentMode(doc, files, { search, hash, base: basePath });
  const originalButton = el('button', { type: 'button', class: 'view-button', 'aria-controls': 'document-original' }, 'PDF 原件');
  const textButton = el('button', { type: 'button', class: 'view-button', 'aria-controls': 'document-text' }, extracted ? '文字检索' : '正文阅读');
  const modes = el('div', { class: 'document-modes', role: 'group', 'aria-label': '阅读方式' });

  if (files.length) {
    const open = el('a', { href: selected.url, target: '_blank', rel: 'noopener noreferrer', class: 'button open-original' }, '新窗口打开原件 ↗');
    actions.prepend(open);
    const picker = el('select', { class: 'original-select', 'aria-label': '选择 PDF 附件' },
      files.map((item, i) => el('option', { value: String(i) }, item.label || `PDF 附件 ${i + 1}`)));
    if (files.length > 1) actions.prepend(picker);
    const holder = el('div', { class: 'pdf-holder' });
    const showPDF = () => {
      if (!verifiedFiles.length) return;
      if (!frame) {
        frame = el('iframe', { class: 'original-frame', title: `${doc.title || doc.source_id} · PDF 原件`,
          src: `${selected.url}#view=FitH`, referrerpolicy: 'no-referrer' });
        holder.replaceChildren(frame);
      }
    };
    picker.addEventListener('change', () => {
      selected = files[Number(picker.value)] || files[0];
      open.href = selected.url;
      if (frame) frame.src = `${selected.url}#view=FitH`;
    });
    if (!verifiedFiles.length) holder.append(el('div', { class: 'pdf-external-placeholder' },
      el('strong', {}, '该 PDF 需在政府官网阅读'),
      el('p', {}, '官网不一定允许第三方页面嵌入原件；本站没有托管该文件，也不会用错乱的提取文字代替原版式。'),
      el('p', {}, '请选择上方附件后，使用“新窗口打开原件”。')));
    originalPane.append(el('p', { class: 'pdf-help' }, verifiedFiles.length
      ? '以下展示已校验的 PDF 原件。若浏览器未显示预览、手机显示不全或加载较慢，请使用“新窗口打开原件”。'
      : '此文件有政府官网 PDF，但本站没有可嵌入的已校验副本。请使用“新窗口打开原件”；提取文字仅辅助检索。'), holder);
    originalButton.addEventListener('click', () => selectMode('original'));
    modes.append(originalButton);
    function selectMode(next) {
      mode = next;
      shell.dataset.mode = mode;
      textPane.hidden = mode !== 'text';
      originalPane.hidden = mode !== 'original';
      originalButton.setAttribute('aria-pressed', String(mode === 'original'));
      textButton.setAttribute('aria-pressed', String(mode === 'text'));
      if (mode === 'original') showPDF();
      onModeChange(mode);
    }
    textButton.addEventListener('click', () => selectMode('text'));
    // Expose only the mode transition, not arbitrary frame URLs.
    shell.showText = () => selectMode('text');
    selectMode(mode);
  } else {
    textButton.setAttribute('aria-pressed', 'true');
    shell.dataset.mode = 'text';
    originalPane.hidden = true;
    shell.showText = () => {};
  }
  modes.append(textButton);
  shell.append(el('div', { class: 'document-toolbar' }, modes, actions), originalPane, textPane);
  return shell;
}

export { createDocumentView, initialDocumentMode, isOriginalPath };
export { isStaticOriginalPath, isOfficialPDFPath, officialPDFs, pdfCandidates };
