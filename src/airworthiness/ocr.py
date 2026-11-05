"""Local, uncorrected scan OCR. No network, ingestion or approval side effects.

Only the calling thread touches PyMuPDF. Worker threads wait for independent
Tesseract processes, with at most three PNGs/processes in flight. Successful
pages are atomically cached; failed/empty pages are retried on the next call.
"""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

import pymupdf


TESSERACT_EXE = shutil.which('tesseract') or 'C:/msys64/ucrt64/bin/tesseract.exe'
# Version 2 binds rendering to the hashed snapshot; never reuse v1 race-prone keys.
PIPELINE_VERSION = 2
MAX_PIXELS = 25_000_000
MAX_PDF_BYTES = 256 * 1024 * 1024
NOTE = ('本地机械 OCR（chi_sim+eng），保留引擎原始文字，未经人工校核；'
        '可能存在错字、漏字、乱码及表格顺序错误，不代表核准全文。'
        'ocr_complete 仅表示每页引擎执行成功且输出非空，不代表文字完整或准确；'
        'error 非空的页面（包括超时的部分文字及空页）不可视为完整提取。')


def _sha_file(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _json_sha(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _atomic_json(path, value):
    """A crash leaves either the previous complete file or the new complete file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_page(path, key, number):
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        page = record['page']
        if (record['cache_key'] == key and page['number'] == number
                and isinstance(page['text'], str) and page['text'].strip()
                and page['error'] is None and page['empty'] is False
                and isinstance(page['stderr'], str) and page['returncode'] == 0
                and record['page_sha256'] == _json_sha(page)):
            return page
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _decode(raw):
    # subprocess output is captured as bytes, so line endings are not normalized.
    return raw.decode('utf-8') if isinstance(raw, bytes) else (raw or '')


def _page_result(number, text='', error=None, stderr='', returncode=None):
    empty = not bool(text.strip())
    if error is None and empty:
        error = 'empty: no text recognized; blank or unreadable page'
    return dict(number=number, text=text, error=error, empty=empty,
                stderr=stderr, returncode=returncode)


def _recognize(image_path, number, models, dpi, timeout):
    command = [TESSERACT_EXE, str(image_path), 'stdout', '--tessdata-dir', str(models),
               '-l', 'chi_sim+eng', '--oem', '1', '--psm', '3', '--dpi', str(dpi)]
    # Limit only the child environment, without changing global/system settings.
    env = dict(os.environ, OMP_THREAD_LIMIT='1', OMP_NUM_THREADS='1')
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, env=env, check=False)
        text = _decode(result.stdout)
        stderr = result.stderr.decode('utf-8', errors='replace')
        error = None if result.returncode == 0 else f'tesseract exit {result.returncode}: {stderr}'
        return _page_result(number, text, error, stderr, result.returncode)
    except subprocess.TimeoutExpired as exc:
        # subprocess.run kills and waits for its child on timeout. Partial output
        # remains inspectable but is explicitly erroneous and will not be reused.
        text = (exc.output or b'').decode('utf-8', errors='replace')
        stderr = (exc.stderr or b'').decode('utf-8', errors='replace')
        return _page_result(number, text, f'timeout after {timeout:g}s', stderr)
    except (OSError, UnicodeError) as exc:
        return _page_result(number, error=f'tesseract {type(exc).__name__}: {exc}')
    finally:
        image_path.unlink(missing_ok=True)


def ocr_pdf(path, cache_dir, tessdata_dir, *, workers=3, dpi=180, timeout=45):
    """Return pages(text,error,number,empty,stderr,returncode) plus provenance.

    The PDF may have any filename extension. ``cache_dir/<cache_key>/`` holds
    per-page JSON and ``result.json``. Cache identity includes PDF/model hashes,
    the pipeline/Tesseract/PyMuPDF versions, DPI and all recognition settings.
    ``workers`` is capped at three; ``timeout`` is per Tesseract page invocation
    and must not exceed 45 seconds. Source PDFs are limited to 256 MiB and read
    once into immutable bytes used for both hashing and rendering.
    A page above 25 million rendered pixels becomes an explicit render error.
    Fatal setup/invalid-PDF errors raise; individual page failures are returned.
    Run this function on the main thread; do not use PyMuPDF concurrently outside
    it. No spelling correction, whitespace cleanup or inferred text is applied.
    """
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('ocr_pdf must run on the main thread; PyMuPDF is not thread-safe')
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError('workers must be a positive integer')
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi < 1:
        raise ValueError('dpi must be a positive integer')
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or not 0 < timeout <= 45):
        raise ValueError('timeout must be finite, positive and at most 45 seconds')
    workers = min(workers, 3)
    path = Path(path).resolve()
    models = Path(tessdata_dir).resolve()
    model_hashes = {lang: _sha_file(models / (lang + '.traineddata'))
                    for lang in ('chi_sim', 'eng')}
    # Bind provenance to exactly the bytes rendered, even if the path is later
    # replaced. The extra byte detects oversize input without an unbounded read.
    with path.open('rb') as handle:
        pdf_bytes = handle.read(MAX_PDF_BYTES + 1)
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError(f'PDF size limit exceeded: maximum {MAX_PDF_BYTES} bytes')
    original_sha = hashlib.sha256(pdf_bytes).hexdigest()
    try:
        engine = subprocess.run([TESSERACT_EXE, '--version'], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=15, check=False)
        if engine.returncode != 0 or not engine.stdout:
            raise RuntimeError(f'Tesseract version failed: {_decode(engine.stderr)}')
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'Tesseract unavailable: {exc}') from exc
    provenance = dict(original_sha256=original_sha, models=model_hashes,
                      tesseract_version=_decode(engine.stdout).strip(),
                      pymupdf_version=pymupdf.VersionBind,
                      pipeline_version=PIPELINE_VERSION, dpi=dpi,
                      languages='chi_sim+eng', oem=1, psm=3,
                      colorspace='gray', alpha=False, annotations=True,
                      omp_thread_limit=1)
    key = _json_sha(provenance)
    folder = Path(cache_dir).resolve() / key
    with pymupdf.open(stream=pdf_bytes, filetype='pdf') as document:
        if not document.is_pdf or document.needs_pass or document.page_count < 1:
            raise ValueError('A readable, nonempty, unencrypted PDF is required')
        page_count = document.page_count
        folder.mkdir(parents=True, exist_ok=True)
        pages = [None] * page_count

        def save_page(page):
            number = page['number']
            _atomic_json(folder / 'pages' / f'{number:06d}.json',
                         dict(cache_key=key, page_sha256=_json_sha(page), page=page))
            pages[number - 1] = page

        # A bounded producer: no PDF objects ever enter the executor, and no
        # document-wide image list is created. One raster is held while saving.
        with tempfile.TemporaryDirectory(prefix='work-', dir=folder) as work_dir:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                pending = set()

                def collect_one_or_more():
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        pending.remove(future)
                        save_page(future.result())

                for number in range(1, page_count + 1):
                    cached = _read_page(folder / 'pages' / f'{number:06d}.json', key, number)
                    if cached is not None:
                        pages[number - 1] = cached
                        continue
                    if len(pending) >= workers:
                        collect_one_or_more()
                    image_path = Path(work_dir) / f'{number:06d}.png'
                    try:
                        page = document.load_page(number - 1)
                        width = math.ceil(page.rect.width * dpi / 72)
                        height = math.ceil(page.rect.height * dpi / 72)
                        if width * height > MAX_PIXELS:
                            raise ValueError(f'render limit: {width}x{height} exceeds {MAX_PIXELS} pixels')
                        pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
                        try:
                            pixmap.save(image_path)
                        finally:
                            del pixmap
                    except Exception as exc:
                        image_path.unlink(missing_ok=True)
                        save_page(_page_result(number, error=f'render {type(exc).__name__}: {exc}'))
                        continue
                    pending.add(pool.submit(_recognize, image_path, number, models, dpi, timeout))
                while pending:
                    collect_one_or_more()
    error_count = sum(page['error'] is not None for page in pages)
    result = dict(pages=pages, page_count=page_count, original_sha256=original_sha,
                  method='local_ocr_tesseract', note=NOTE, cache_key=key,
                  provenance=provenance, error_count=error_count,
                  empty_page_count=sum(page['empty'] for page in pages),
                  ocr_complete=error_count == 0)
    _atomic_json(folder / 'result.json', result)
    return result
