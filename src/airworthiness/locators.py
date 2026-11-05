"""Pure evidence-only glossary resolution; no file, database or network writes.

Usage::

    rows = resolve_terms(terms_for_one_source, document_body, extracted=True)

``terms`` is an iterable of mappings, normally existing CSV/SQLite rows with
term, aliases (semicolon/pipe separated, or a list), source_id and chapter_id.
Pass ONLY rows belonging to the supplied body: source identity is the caller's
responsibility. An optional ``quote`` must be an exact, case-sensitive source
quotation, not an editorial definition. ``definition`` is never used as evidence.

Returns copied rows with anchor_or_url, locator_anchor, locator_status,
locator_evidence (<=240 literal source characters), locator_kind, locator_note,
definition_verified=False and has_page (CSV-compatible "true"/"false"). Original
anchors are retained in original_anchor_or_url. With chapter_id/source_id, links
are /chapters/<chapter>?source=<source>#<anchor>; without them they are fragments
or a safe supplied source_url/url/anchor_or_url, stripped of stale fragments.

verified_clause ONLY verifies a unique exact quote's textual position within an
explicit article, with a term/alias in that same quote (>=8 nonspace characters,
not merely the name). It never verifies the definition, legal effect, extraction
quality or applicability. Keyword-only, ambiguous quotes and paragraph locations
are text_match. Missing evidence is source_only. Matches are literal: no fuzzy
matching, case folding, OCR repair, number inference or semantic interpretation.
"""
import re
from urllib.parse import quote as urlquote, urlsplit

from .reading import document_locations


def _source_target(term):
    chapter, source = term.get("chapter_id"), term.get("source_id")
    if chapter and source:
        return f"/chapters/{urlquote(str(chapter), safe='')}?source={urlquote(str(source), safe='')}"
    for field in ("source_url", "url", "anchor_or_url"):
        value = str(term.get(field) or "").split("#", 1)[0]
        try:
            parsed = urlsplit(value)
        except ValueError:
            continue
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return value
        if value.startswith("/") and not value.startswith("//") and "\\" not in value:
            return value
    return ""


def _names(term):
    aliases = term.get("aliases") or []
    if isinstance(aliases, str):
        aliases = re.split(r"[;；|]", aliases)
    return list(dict.fromkeys(name.strip() for name in [term.get("term", ""), *aliases]
                              if isinstance(name, str) and name.strip()))


def _match(name, text):
    # AC must not match CAAC, TC must not match STC; Chinese substrings are useful.
    left = r"(?<![A-Za-z0-9_])" if name[0].isascii() and name[0].isalnum() else ""
    right = r"(?![A-Za-z0-9_])" if name[-1].isascii() and name[-1].isalnum() else ""
    return re.search(left + re.escape(name) + right, text)


def _snippet(text, start, length):
    if length <= 240:
        return text[start:start + length]
    return text[start:start + 240]


def resolve_terms(terms, body, extracted=False):
    """Resolve rows against exactly the body/flag used with render_document()."""
    locations = document_locations(body, extracted=extracted)
    results = []
    for term in terms:
        result = dict(term)
        base = _source_target(term)
        result.setdefault("original_anchor_or_url", term.get("anchor_or_url", ""))
        result.update(anchor_or_url=base, locator_anchor="", locator_status="source_only",
                      locator_evidence="", locator_kind="source", has_page="false",
                      definition_verified=False, locator_note="未找到可靠正文位置，仅定位来源。")
        names, matches = _names(term), []
        for location in locations:
            for name in names:
                match = _match(name, location["text"])
                if match:
                    matches.append((location, match.start(), len(name)))
                    break
        exact = term.get("quote") or ""
        quoted = []
        if isinstance(exact, str) and len(re.sub(r"\s", "", exact)) >= 8 and exact not in names:
            if any(_match(name, exact) for name in names):
                quoted = [loc for loc in locations if loc["kind"] == "paragraph"
                          and exact in loc["text"]]
        verified = (len(quoted) == 1 and quoted[0]["clause"]
                    and quoted[0]["text"].count(exact) == 1)
        if verified:
            location, start, length = quoted[0], quoted[0]["text"].index(exact), len(exact)
        elif matches:
            # Prefer actual prose to a title, then a concrete clause to a paragraph.
            location, start, length = min(matches, key=lambda item: (
                item[0]["kind"] != "paragraph", not bool(item[0]["clause"])))
            start = max(0, start - 60)
            length = min(240, len(location["text"]) - start)
        else:
            results.append(result)
            continue
        anchor = location["clause"] or location["id"]
        result.update(anchor_or_url=base + "#" + anchor, locator_anchor=anchor,
                      locator_status="verified_clause" if verified else "text_match",
                      locator_evidence=_snippet(location["text"], start, length),
                      locator_kind="clause" if location["clause"] else "paragraph", has_page="true",
                      locator_note=("已核对精确引文的条款位置；未核验术语释义。" if verified else
                                    "仅原文关键词命中；未核验精确引文或术语释义。"))
        results.append(result)
    return results
