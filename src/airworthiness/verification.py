"""Offline, evidence-bound metadata overlay; never approves or rewrites content.

Call after loading raw documents and their issues, before catalog/API output.
Only schema 1.2 findings with result=verified AND resolution=corrected may
write title, publish_date or document_code. All source files remain read-only.
"""
import json
import warnings
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

from .acquire_http import canonical_url


FIELD_MAP = {"title": "title", "date": "publish_date", "publish_date": "publish_date",
             "code": "document_code", "document_code": "document_code"}
ISSUE_FIELDS = {"title_variation": "title", "date_variation": "publish_date",
                "missing_date": "publish_date", "code_conflict": "document_code"}
SNAPSHOT_FIELDS = ("title", "document_code", "publish_date", "document_status", "url", "review_status")
RESOLVING_APPLICATIONS = {"corrected", "already_matches", "explained", "confirmed"}


def _load_findings(root):
    path = Path(root) / "data/verification/metadata-findings.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.2":
            raise ValueError("unsupported findings schema (expected 1.2)")
        findings = payload.get("findings")
        if not isinstance(findings, list):
            raise ValueError("findings must be an array")
        return [f for f in findings if isinstance(f, dict)
                and isinstance(f.get("finding_id"), str) and f["finding_id"]
                and isinstance(f.get("field"), str) and isinstance(f.get("result"), str)
                and isinstance(f.get("source_ids"), list)
                and all(isinstance(sid, str) for sid in f["source_ids"])]
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        warnings.warn(f"Metadata verification not applied: {exc}", RuntimeWarning, stacklevel=2)
        return []


def _official_url(value):
    # Reject ambiguous raw input before a parser can strip controls or disagree
    # with browser backslash handling. Include C1 controls as well as C0/DEL.
    if not isinstance(value, str) or any(
            char == "\\" or ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        return False
    try:
        # Reuse the retrieval layer's authority, credentials and port policy.
        # Validate only: do not normalize stored evidence or source bindings.
        canonical_url(value)
    except ValueError:
        return False
    return True


def _evidence_valid(finding):
    urls, evidence = finding.get("evidence_url"), finding.get("evidence")
    if not isinstance(urls, list) or not urls or not all(_official_url(x) for x in urls):
        return False
    if not isinstance(evidence, dict) or evidence.get("type") not in ("quote", "paraphrase"):
        return False
    text = evidence.get("text")
    if not isinstance(text, str) or not text.strip():
        return False
    if evidence["type"] == "quote" and len(text) > 25:
        return False
    try:
        stamp = datetime.fromisoformat(finding["checked_at"])
        return stamp.tzinfo is not None
    except (KeyError, TypeError, ValueError):
        return False


def _decision(finding, doc):
    """Return (action, block_reason), without mutating a document."""
    field = FIELD_MAP.get(finding.get("field"))
    result, resolution = finding.get("result"), finding.get("resolution")
    if result in {"unresolved", "unresolved_source_identity"}:
        return "unresolved", ""
    if not _evidence_valid(finding):
        return "blocked", "insufficient_evidence"
    sid = doc.get("source_id")
    urls = finding.get("source_urls")
    if not isinstance(urls, dict) or sid not in urls or urls[sid] != doc.get("url"):
        return "blocked", "source_url_changed_or_unbound"
    if resolution == "recorded":
        return "recorded", ""
    allowed = ((resolution == "corrected" and result == "verified")
               or (resolution == "confirmed" and result == "verified")
               or (resolution == "explained" and result in {"equivalent_title", "scope_distinction"}))
    if not field or not allowed:
        return "blocked", "not_an_authorized_field_decision"
    old_values, value = finding.get("old_values"), finding.get("verified_value")
    if (not isinstance(old_values, dict) or sid not in old_values
            or not isinstance(old_values[sid], str) or field not in doc):
        return "blocked", "missing_original_value"
    if not isinstance(value, str) or not value.strip():
        return "blocked", "invalid_verified_value"
    if field == "publish_date":
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError("date must be YYYY-MM-DD")
        except ValueError:
            return "blocked", "invalid_verified_value"
    if doc[field] not in (old_values[sid], value):
        return "blocked", "current_value_changed"
    if resolution == "confirmed" and doc[field] != value:
        return "blocked", "confirmation_does_not_match"
    return resolution, ""


def _record(finding, doc, action, reason):
    # Retain the complete reasoning (date roles, attachment hashes, limitations),
    # but use the same singular source_id as documents and issues at the API edge.
    record = deepcopy(finding)
    record.pop("source_ids", None)
    record.pop("old_values", None)
    record.pop("source_urls", None)
    field = FIELD_MAP.get(finding.get("field"), finding.get("field"))
    record.update(source_id=doc.get("source_id"), field=field, application=action, applied=False)
    if field in doc.get("original_metadata", {}):
        record["original_value"] = deepcopy(doc["original_metadata"][field])
    if action == "corrected":
        record["applied"] = record.get("original_value") != finding["verified_value"]
        if not record["applied"]:
            record["application"] = "already_matches"
    if reason:
        record["block_reason"] = reason
    return record


def apply_metadata(documents, issues, root):
    """Mutate docs in place; return (resolved_issues, unresolved_issues).

    Each doc gets metadata_verification (including blocked/unresolved evidence)
    and original_metadata, whose first-observed values are never overwritten.
    Inputs issues are not mutated. Resolved copies add resolution, finding_ids,
    and evidence. Unresolved entries retain their original objects/order.
    Alias and supplementary metadata findings are recorded only; body, URL,
    acquisition data, status and review_status are never assigned here.
    """
    by_source = defaultdict(list)
    for finding in _load_findings(root):
        for sid in dict.fromkeys(finding["source_ids"]):
            by_source[sid].append(finding)
    decisions = defaultdict(list)
    for doc in documents:
        original = doc.setdefault("original_metadata", {})
        for field in SNAPSHOT_FIELDS:
            if field in doc:
                original.setdefault(field, deepcopy(doc[field]))
        doc["metadata_verification"] = []
        findings = by_source.get(doc.get("source_id"), [])
        evaluated = [(f, *_decision(f, doc)) for f in findings]
        targets = defaultdict(set)
        for finding, action, _ in evaluated:
            if action in {"corrected", "confirmed"}:
                targets[FIELD_MAP[finding["field"]]].add(finding["verified_value"])
        conflicts = {field for field, values in targets.items() if len(values) > 1}
        identity_unresolved = any(f.get("result") == "unresolved_source_identity" for f in findings)
        for finding, action, reason in evaluated:
            field = FIELD_MAP.get(finding.get("field"))
            if action in {"corrected", "confirmed", "explained"}:
                if identity_unresolved:
                    action, reason = "blocked", "unresolved_source_identity"
                elif field in conflicts:
                    action, reason = "blocked", "conflicting_findings"
            if action == "corrected":
                doc[field] = finding["verified_value"]
            record = _record(finding, doc, action, reason)
            doc["metadata_verification"].append(record)
            if record["application"] in RESOLVING_APPLICATIONS:
                decisions[(doc.get("source_id"), field)].append(record)
    resolved, unresolved = [], []
    for issue in issues:
        field = ISSUE_FIELDS.get(issue.get("kind"))
        evidence = decisions.get((issue.get("source_id"), field), []) if field else []
        if not evidence:
            unresolved.append(issue)
            continue
        resolution = ("corrected" if any(e["resolution"] == "corrected" for e in evidence)
                      else "explained" if any(e["resolution"] == "explained" for e in evidence)
                      else "confirmed")
        resolved.append({**deepcopy(issue), "resolution": resolution,
                         "finding_ids": list(dict.fromkeys(e["finding_id"] for e in evidence)),
                         "evidence": deepcopy(evidence)})
    return resolved, unresolved
