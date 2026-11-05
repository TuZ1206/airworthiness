"""Verified official HTTP retrieval and cache primitives for acquire.py."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import uuid4

import requests


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_url(url: str) -> str:
    """Normalize only insignificant URL parts; preserve case and query semantics."""
    if not isinstance(url, str) or re.search(r"[\\\x00-\x20\x7f]", url):
        raise ValueError("Unsafe URL characters")
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (parsed.scheme.lower() not in {"http", "https"} or not host
            or not (host == "gov.cn" or host.endswith(".gov.cn"))
            or not re.fullmatch(r"[a-z0-9.-]+", host)
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("Only public http(s) gov.cn URLs without credentials are allowed")
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    if parsed.port not in {None, default_port}:
        raise ValueError("Nonstandard port rejected")
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", parsed.query, ""))


class AcquisitionError(RuntimeError):
    pass


@dataclass
class Download:
    data: bytes
    url: str
    crawled_at: str
    content_type: str = ""
    redirects: list[str] = field(default_factory=list)

    @property
    def original_sha256(self):
        return digest(self.data)


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def write_json(path: Path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


class Fetcher:
    """Manual redirect checking, bounded streaming, per-host limits, verified cache.

    ``transport`` injects only the HTTP boundary for deterministic offline tests.
    Production uses requests with TLS verification and no .netrc/environment auth.
    No fallback network or fabricated responses are provided.
    """

    def __init__(self, cache_dir: Path, *, transport=None, retries=1,
                 timeout=(3.5, 9), max_bytes=32 * 1024 * 1024, deadline=40,
                 max_redirects=5, per_host=2, interval=0.4, refresh=False,
                 proxy=None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / ".gitignore").write_text("*\n", encoding="ascii")
        self.transport = transport
        self.retries = retries
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.deadline = deadline
        self.max_redirects = max_redirects
        self.per_host = per_host
        self.interval = interval
        self.refresh = refresh
        self.proxy = proxy
        self._lock = threading.Lock()
        self._host_slots = defaultdict(lambda: threading.BoundedSemaphore(per_host))
        self._host_pace = defaultdict(threading.Lock)
        self._host_last = defaultdict(float)
        self._url_locks = defaultdict(threading.Lock)
        self._memory: dict[str, Download | AcquisitionError] = {}
        self.events = []
        self.journal = None
        self.run_id = uuid4().hex

    def begin_run(self, journal: Path, legacy_events=()):
        """Append-only request evidence; never erase earlier failed runs."""
        self.journal = Path(journal)
        self.run_id = uuid4().hex
        self.events = []
        self._memory = {}
        if not self.journal.exists() and legacy_events:
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            with self.journal.open("a", encoding="utf-8") as handle:
                for event in legacy_events:
                    handle.write(json.dumps(dict(event, run_id="initial-report"), ensure_ascii=False) + "\n")

    def _record(self, event):
        event = dict(event, run_id=self.run_id)
        with self._lock:
            self.events.append(event)
            if self.journal:
                self.journal.parent.mkdir(parents=True, exist_ok=True)
                with self.journal.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _cached(self, url, key):
        meta_path = self.cache_dir / (key + ".json")
        raw_path = self.cache_dir / (key + ".bin")
        if self.refresh or not meta_path.exists() or not raw_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if raw_path.stat().st_size > self.max_bytes or meta["request_url"] != url:
                return None
            final = canonical_url(meta["url"])
            redirects = [canonical_url(u) for u in meta["redirects"]]
            data = raw_path.read_bytes()
            if digest(data) != meta["original_sha256"]:
                return None
            return Download(data, final, meta["crawled_at"], meta["content_type"], redirects)
        except (KeyError, ValueError, OSError):
            return None

    def fetch(self, url: str) -> Download:
        try:
            url = canonical_url(url)
        except ValueError as exc:
            raise AcquisitionError(str(exc)) from exc
        with self._lock:
            mutex = self._url_locks[url]
        with mutex:
            if url in self._memory:
                cached = self._memory[url]
                if isinstance(cached, AcquisitionError):
                    raise cached
                return cached
            key = digest(url.encode())
            cached = self._cached(url, key)
            if cached:
                self._memory[url] = cached
                self._record(dict(url=url, actual_url=cached.url, status="cache", crawled_at=cached.crawled_at))
                return cached
            try:
                result = self._retrieve(url)
                atomic_write(self.cache_dir / (key + ".bin"), result.data)
                write_json(self.cache_dir / (key + ".json"), dict(
                    request_url=url, url=result.url, content_type=result.content_type,
                    crawled_at=result.crawled_at, redirects=result.redirects,
                    original_sha256=result.original_sha256, size=len(result.data)))
                self._memory[url] = result
                return result
            except AcquisitionError as exc:
                self._memory[url] = exc
                raise

    def _retrieve(self, url):
        transport = self.transport
        if transport is None:
            transport = requests.Session()
            transport.trust_env = False  # No credential files, ambient auth, or secrets.
            if self.proxy:
                transport.proxies.update({"http": self.proxy, "https": self.proxy})
        try:
            for attempt in range(self.retries + 1):
                started = time.monotonic()
                current, redirects = url, []
                try:
                    for hop in range(self.max_redirects + 1):
                        current = canonical_url(current)
                        host = urlsplit(current).hostname
                        with self._lock:
                            slots, pace = self._host_slots[host], self._host_pace[host]
                        with slots:
                            with pace:
                                delay = self.interval - (time.monotonic() - self._host_last[host])
                                if delay > 0:
                                    time.sleep(delay)
                                self._host_last[host] = time.monotonic()
                            if time.monotonic() - started > self.deadline:
                                raise AcquisitionError("Download deadline exceeded")
                            response = transport.get(current, timeout=self.timeout, stream=True,
                                                     allow_redirects=False, verify=True,
                                                     headers={"User-Agent": "AirworthinessOfflineLibrary/1.0",
                                                              "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.1"})
                            try:
                                status = response.status_code
                                self._record(dict(url=current, status=status, stage="response", attempt=attempt + 1, crawled_at=now()))
                                if status in {301, 302, 303, 307, 308}:
                                    location = response.headers.get("Location")
                                    if not location:
                                        raise AcquisitionError("Redirect without Location")
                                    target = canonical_url(urljoin(current, location))
                                    if target in redirects or target == current or hop == self.max_redirects:
                                        raise AcquisitionError("Redirect loop or limit exceeded")
                                    redirects.append(current)
                                    current = target
                                    continue
                                if status in {408, 429, 500, 502, 503, 504} and attempt < self.retries:
                                    raise requests.exceptions.RetryError(f"HTTP {status}")
                                if status != 200:
                                    raise AcquisitionError(f"HTTP {status}: {current}")
                                length = response.headers.get("Content-Length", "")
                                if length.isdigit() and int(length) > self.max_bytes:
                                    raise AcquisitionError("Content-Length exceeds size limit")
                                chunks, size = [], 0
                                for chunk in response.iter_content(chunk_size=64 * 1024):
                                    size += len(chunk)
                                    if size > self.max_bytes:
                                        raise AcquisitionError("Response exceeds size limit")
                                    if time.monotonic() - started > self.deadline:
                                        raise AcquisitionError("Download deadline exceeded")
                                    chunks.append(chunk)
                                data = b"".join(chunks)
                                if not data:
                                    raise AcquisitionError("Empty HTTP response")
                                self._record(dict(url=current, status="retrieved", size=size, stage="complete",
                                                  original_sha256=digest(data), attempt=attempt + 1, crawled_at=now()))
                                return Download(data, current, now(), response.headers.get("Content-Type", ""), redirects)
                            finally:
                                response.close()
                    raise AcquisitionError("Redirect limit exceeded")
                except (requests.RequestException, ValueError, AcquisitionError) as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    self._record(dict(url=current, status="failed", attempt=attempt + 1, error=error, crawled_at=now()))
                    # Certificate/handshake failures never disable verification or downgrade TLS.
                    if isinstance(exc, (requests.exceptions.SSLError, ValueError, AcquisitionError)) or attempt == self.retries:
                        raise AcquisitionError(error) from exc
                    time.sleep(min(0.5 * (attempt + 1), 2))
        finally:
            if self.transport is None:
                transport.close()
