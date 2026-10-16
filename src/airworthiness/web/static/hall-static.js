/* GitHub Pages transport. All paths are local snapshots, never a remote API. */
const staticCache = new Map();

function prefixPath(value, base = '', directoryRoutes = false) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return value;
  const boundary = value.search(/[?#]/);
  let path = boundary < 0 ? value : value.slice(0, boundary);
  const tail = boundary < 0 ? '' : value.slice(boundary);
  if (base && (path === base || path.startsWith(base + '/'))) path = path.slice(base.length) || '/';
  if (directoryRoutes && /^(?:\/chapters\/ch\d{2}|\/quality)$/.test(path)) path += '/';
  return base + path + tail;
}

function unprefixPath(path, base = '') {
  if (base && path !== base && !path.startsWith(base + '/')) return null;
  const result = base ? path.slice(base.length) : path;
  return !result || result === '/index.html' ? '/' : result;
}

function requestError(status, message) {
  const error = new Error(message);
  error.status = status;
  error.userMessage = message;
  return error;
}

function searchOptions(params) {
  const options = Object.fromEntries(['q', 'chapter', 'status', 'content_kind'].map(key => [key, (params.get(key) || '').trim()]));
  if (options.q.length > 200 || /[\x00-\x1f]/.test(options.q)) throw requestError(400, '关键词限 200 字，不能包含控制字符。');
  const choices = { chapter: /^(?:ch0[1-9])?$/, status: /^(?:effective|abolished|unknown)?$/,
    content_kind: /^(?:fulltext|extracted|excerpt|metadata)?$/ };
  for (const [key, pattern] of Object.entries(choices)) {
    if (!pattern.test(options[key])) throw requestError(400, `无效的筛选条件：${key}`);
  }
  for (const [key, fallback] of [['page', 1], ['page_size', 20]]) {
    const value = params.get(key);
    if (value !== null && !/^[+-]?\d+$/.test(value.trim())) throw requestError(400, '页码和每页条数必须为整数。');
    options[key] = Math.max(1, Math.min(Number.MAX_SAFE_INTEGER, value === null ? fallback : Number(value)));
  }
  options.page_size = Math.min(100, options.page_size);
  options.needle = options.q.replace(/\s/g, '').toLowerCase();
  return options;
}

function filterResources(rows, options) {
  return rows.filter(row => (!options.chapter || row.chapter_id === options.chapter) &&
    (!options.status || row.document_status === options.status) &&
    (!options.content_kind || row.content_kind === options.content_kind));
}

function searchResources(rows, entries, params) {
  const options = searchOptions(params);
  const index = new Map(entries.map(entry => [entry.source_id, entry]));
  let items = filterResources(rows, options);
  if (options.needle) {
    for (const item of items) {
      const entry = index.get(item.source_id);
      if (!entry || typeof entry.search_text !== 'string' || typeof entry.plain !== 'string') throw new Error('Incomplete search index');
    }
    items = items.filter(item => index.get(item.source_id).search_text.includes(options.needle));
  }
  items.sort((a, b) => (a.source_id < b.source_id ? -1 : a.source_id > b.source_id ? 1 : 0));
  const total = items.length;
  const pages = Math.max(1, Math.ceil(total / options.page_size));
  const page = Math.min(options.page, pages);
  items = items.slice((page - 1) * options.page_size, page * options.page_size).map(item => {
    if (!options.needle) return { ...item };
    const plain = index.get(item.source_id).plain;
    const position = plain.toLowerCase().indexOf(options.needle);
    const start = Math.max(0, position - 45);
    return { ...item, snippet: (start ? '…' : '') + plain.slice(start, start + 180) + (plain.length > start + 180 ? '…' : '') };
  });
  return { items, total, pages, page, page_size: options.page_size };
}

function checkAbort(signal) {
  if (signal?.aborted) throw new DOMException('Request aborted', 'AbortError');
}

async function snapshotJSON(path, signal) {
  checkAbort(signal);
  if (staticCache.has(path)) return staticCache.get(path);
  let data;
  // Pages serves .gz as a file. Some hosts transparently decode; check the bytes.
  if (typeof DecompressionStream === 'function') {
    try {
      const response = await fetch(path + '.gz', { signal });
      if (!response.ok) throw requestError(response.status, 'Compressed snapshot unavailable');
      const bytes = new Uint8Array(await response.arrayBuffer());
      data = bytes[0] === 0x1f && bytes[1] === 0x8b
        ? await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).json()
        : JSON.parse(new TextDecoder().decode(bytes));
    } catch (error) {
      checkAbort(signal);
      // Older browsers and missing compressed companions use the ordinary JSON.
    }
  }
  if (data === undefined) {
    const response = await fetch(path, { signal, headers: { Accept: 'application/json' } });
    if (!response.ok) throw requestError(response.status, '在线资料暂时无法下载，请重试。');
    data = await response.json();
  }
  checkAbort(signal);
  if (!data || typeof data !== 'object') throw new Error('Invalid snapshot');
  staticCache.set(path, data);
  return data;
}

async function staticRequest(path, base, signal) {
  checkAbort(signal);
  if (!/^(?:\/[A-Za-z0-9_-]+)*$/.test(base) || !path.startsWith('/api/')) throw requestError(404, '未找到资料。');
  const url = new URL(path, 'https://snapshot.invalid');
  const pathname = url.pathname;
  let file;
  if (pathname === '/api/overview') file = 'overview';
  else if (pathname === '/api/quality') file = 'quality';
  else if (/^\/api\/chapters\/ch0[1-9]$/.test(pathname)) file = pathname.slice(5);
  else if (/^\/api\/documents\/CH0[1-9]-S\d{3}$/.test(pathname)) file = pathname.slice(5);
  else if (pathname !== '/api/resources') throw requestError(404, '未找到资料。');
  if (file) return snapshotJSON(`${base}/data/${file}.json`, signal);

  const options = searchOptions(url.searchParams);
  const catalog = await snapshotJSON(`${base}/data/resources.json`, signal);
  if (!Array.isArray(catalog.items)) throw new Error('Invalid resource snapshot');
  const entries = [];
  if (options.needle) {
    const chapters = [...new Set(filterResources(catalog.items, options).map(row => row.chapter_id))];
    for (let i = 0; i < chapters.length; i += 3) {
      const shards = await Promise.all(chapters.slice(i, i + 3).map(chapter => {
        if (!/^ch0[1-9]$/.test(chapter)) throw new Error('Invalid search shard');
        return snapshotJSON(`${base}/data/search/${chapter}.json`, signal);
      }));
      for (const shard of shards) {
        if (!Array.isArray(shard)) throw new Error('Invalid search index');
        entries.push(...shard);
      }
      checkAbort(signal);
    }
  }
  return searchResources(catalog.items, entries, url.searchParams);
}

export { prefixPath, unprefixPath, searchResources, staticRequest };
