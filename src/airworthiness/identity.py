"""Strict, rebuildable identity records for chapter source registrations."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from .acquire_http import canonical_url


def normalize_code(value: str) -> str:
    """Keep every meaningful character; only normalize casing and spacing."""
    return re.sub(r"\s+", "", str(value or "")).upper()


def canonical_identity(document: dict) -> tuple[str, str, str]:
    """The three fields required for an automatic, safe source merge."""
    return (canonical_url(document["url"]), normalize_code(document["document_code"]),
            str(document["sha256"] or "").lower())


def _canonical_id(identity: tuple[str, str, str]) -> str:
    digest = hashlib.sha256("\x1f".join(identity).encode("utf-8")).hexdigest()[:16].upper()
    return "DOC-" + digest


def build_document_identity(documents: list[dict]) -> dict:
    """Create internal canonical records without changing chapter source IDs.

    Only exact normalized official URL + document code/version + Markdown hash
    matches are merged. Similar names are deliberately not considered evidence.
    """
    groups = defaultdict(list)
    invalid = []
    for document in documents:
        try:
            groups[canonical_identity(document)].append(document)
        except (KeyError, TypeError, ValueError):
            invalid.append(document["source_id"])

    canonical, aliases, source_links = [], [], []
    for identity, members in sorted(groups.items()):
        canonical_id = _canonical_id(identity)
        exemplar = sorted(members, key=lambda item: item["source_id"])[0]
        canonical.append(dict(canonical_id=canonical_id, canonical_url=identity[0],
                              normalized_code=identity[1], markdown_sha256=identity[2],
                              title=exemplar["title"], document_status=exemplar["document_status"],
                              review_status=exemplar["review_status"]))
        for member in members:
            member["canonical_id"] = canonical_id
            source_links.append(dict(source_id=member["source_id"], chapter_id=member["chapter_id"],
                                     canonical_id=canonical_id))
            aliases.extend((
                dict(canonical_id=canonical_id, alias_type="title", alias=member["title"],
                     source_id=member["source_id"]),
                dict(canonical_id=canonical_id, alias_type="document_code", alias=member["document_code"],
                     source_id=member["source_id"]),
            ))

    conflicts = []
    by_url = defaultdict(set)
    by_code = defaultdict(set)
    for identity in groups:
        by_url[identity[0]].add(identity)
        if identity[1]:
            by_code[identity[1]].add(identity)
    for url, identities in sorted(by_url.items()):
        if len(identities) > 1:
            conflicts.append(dict(conflict_type="same_url_different_identity", conflict_key=url,
                                  source_ids=sorted(item["source_id"] for identity in identities for item in groups[identity]),
                                  detail="同一官方链接的文号、版本或正文哈希不一致；未自动归并。"))
    for code, identities in sorted(by_code.items()):
        if len(identities) > 1:
            conflicts.append(dict(conflict_type="same_code_different_identity", conflict_key=code,
                                  source_ids=sorted(item["source_id"] for identity in identities for item in groups[identity]),
                                  detail="同一文号的官方链接或正文哈希不一致；未自动归并。"))
    for source_id in sorted(invalid):
        conflicts.append(dict(conflict_type="invalid_identity", conflict_key=source_id, source_ids=[source_id],
                              detail="无法建立严格身份键；未自动归并。"))
    return dict(canonical_documents=canonical, chapter_sources=source_links, aliases=aliases,
                conflicts=conflicts)
