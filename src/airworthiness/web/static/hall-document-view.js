/* Original layout is the default for PDFs; extracted text is a reading aid. */
import { el, officialLink } from './hall-core.js';

function isOriginalPath(sourceId, path) {
  if (!/^CH\d{2}-S\d{3}$/.test(sourceId || '') || typeof path !== 'string') return false;
  const base = `/api/documents/${sourceId}/original`;
  return path.startsWith(base) && /^(?:\?index=(?:0|[1-9]\d*))?$/.test(path.slice(base.length));
}

function initialDocumentMode(doc, originals, { search = '', hash = '' } = {}) {
  if (search || hash) return 'text';
  return ['extracted', 'metadata'].includes(doc.content_kind) &&
    originals.some(item => isOriginalPath(doc.source_id, item?.url)) ? 'original' : 'text';
}

function createDocumentView({ doc, originals, content, tools, search = '', hash = '', onModeChange = () => {} }) {
  const files = originals.filter(item => isOriginalPath(doc.source_id, item?.url));
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
    textPane.append(el('p', { class: 'original-missing' }, '当前电脑未保存可用 PDF 原件。若文字排版仍不清晰，请打开官方来源查看。'));
  }
  textPane.append(tools, content);
  const originalPane = el('div', { class: 'document-original', id: 'document-original' });
  const actions = el('div', { class: 'document-actions' });
  const source = officialLink(doc.url, '官方来源 ↗');
  if (source) actions.append(source);

  let frame = null;
  let selected = files[0];
  let mode = initialDocumentMode(doc, files, { search, hash });
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
    originalPane.append(el('p', { class: 'pdf-help' },
      '以下展示 PDF 原件版式。若浏览器未显示预览、手机显示不全或加载较慢，请使用“新窗口打开原件”，也可打开官方来源。'), holder);
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
