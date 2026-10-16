"""Prefetch hash-verified official regulatory PDFs for a Pages build.

Only currently effective CCAR, AP and AC records from CAAC landing pages are
eligible. Standards, status-only records and material without a known PDF
digest remain link-only. Downloads stay in ignored .cache; no PDF enters Git.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .acquire_http import AcquisitionError, Fetcher, canonical_url


MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_FETCH_BYTES = 240 * 1024 * 1024
PUBLISHABLE_CODES = re.compile(r"^(?:CCAR|AP|AC)-[A-Za-z0-9]", re.I)
SHA256 = re.compile(r"[0-9a-f]{64}")


def _official_pdf(url):
    try:
        clean = canonical_url(url)
        parsed = urlsplit(clean)
        return clean if parsed.scheme == "https" and parsed.path.lower().endswith(".pdf") else None
    except (TypeError, ValueError):
        return None


def publication_candidates(root):
    """Return unique (request URL, final URL, digest, source IDs) candidates."""
    root = Path(root)
    manifest = json.loads((root / "data/acquired/manifest.json").read_text(encoding="utf-8"))
    grouped = {}
    conflicts = set()
    for path in sorted((root / "data/chapters").glob("ch[0-9][0-9]/sources.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                source_id = row.get("source_id", "")
                code = row.get("document_code", "")
                if (not re.fullmatch(r"CH[0-9]{2}-S[0-9]{3}", source_id)
                        or not PUBLISHABLE_CODES.match(code)
                        or row.get("document_status") != "effective"
                        or row.get("review_status") not in {"pending", "approved"}):
                    continue
                landing = row.get("url", "")
                try:
                    landing = canonical_url(landing)
                except (TypeError, ValueError):
                    continue
                if urlsplit(landing).hostname not in {"www.caac.gov.cn", "caac.gov.cn"}:
                    continue
                acquisition = manifest.get(source_id) or {}
                if acquisition.get("content_kind") != "extracted":
                    continue
                for item in (acquisition.get("originals") or [acquisition])[:16]:
                    if not isinstance(item, dict) or item.get("archive_member_sha256"):
                        continue
                    final = _official_pdf(item.get("url"))
                    request = _official_pdf(item.get("request_url") or item.get("url"))
                    expected = item.get("original_sha256") or item.get("pdf_sha256")
                    if not final or not request or not isinstance(expected, str) or not SHA256.fullmatch(expected):
                        continue
                    existing = grouped.get(request)
                    if existing and tuple(existing[1:3]) != (final, expected):
                        conflicts.add(request)
                        continue
                    if existing:
                        existing[3].add(source_id)
                    else:
                        grouped[request] = [request, final, expected, {source_id}]
    # Shared sources first: one verified download can fill several chapters.
    candidates = [(request, final, expected, tuple(sorted(ids)))
                  for request, final, expected, ids in grouped.values()
                  if request not in conflicts]
    return sorted(candidates, key=lambda item: (-len(item[3]), item[0])), sorted(conflicts)


def prefetch(root, *, fetcher=None, max_bytes=MAX_FETCH_BYTES):
    root = Path(root).resolve()
    candidates, conflicts = publication_candidates(root)
    fetcher = fetcher or Fetcher(root / ".cache/acquisition", retries=0,
                                max_bytes=MAX_PDF_BYTES, deadline=35)
    report = {"candidates": len(candidates), "conflicts": conflicts,
              "verified": [], "skipped": [], "verified_bytes": 0}
    for request, final, expected, sources in candidates:
        if report["verified_bytes"] >= max_bytes:
            report["skipped"].append({"sources": sources, "reason": "build byte budget"})
            continue
        try:
            download = fetcher.fetch(request)
            data = download.data
            if (canonical_url(download.url) != final or not data.startswith(b"%PDF-")
                    or not 0 < len(data) <= MAX_PDF_BYTES
                    or hashlib.sha256(data).hexdigest() != expected):
                raise ValueError("PDF URL, signature, size or SHA-256 mismatch")
            if report["verified_bytes"] + len(data) > max_bytes:
                raise ValueError("build byte budget")
            report["verified"].append({"sources": sources, "sha256": expected, "bytes": len(data)})
            report["verified_bytes"] += len(data)
        except (AcquisitionError, ValueError, OSError) as exc:
            report["skipped"].append({"sources": sources, "reason": str(exc)[:180]})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prefetch eligible official PDFs for a Pages build")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    report = prefetch(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
