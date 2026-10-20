"""Safe reading HTML and a shared, conservative index of literal source locations.

Only explicit 第…条/第…章 and PDF page labels acquire semantic IDs. Decimal
quantities and bare numeric outlines are never inferred to be legal headings.
IDs encode the explicit number; repeated occurrences get --2, --3, etc. Directory
entries have a separate toc- namespace, so they cannot steal a body's anchor.
"""
import hashlib
import re
from collections import Counter
from html import escape

import bleach
import markdown
from bs4 import BeautifulSoup

ORDINAL = re.compile(
    r"^第\s*([0-9０-９][0-9０-９ \t.．]*|[零〇一二三四五六七八九十百千万两]+)\s*([条章])(.*)$"
)
# This deliberately broader detector can only CLEAR ownership, never make IDs.
# Rejected titles, spaced Chinese numerals and malformed OCR still bound scope.
CLAUSE_BOUNDARY = re.compile(r"^第\s*[0-9０-９零〇一二三四五六七八九十百千万两 \t.．]+条")
PAGE = re.compile(r"^第\s*([0-9]+)\s*页$")
LEADER = re.compile(r"(?:\.{3,}|…{2,}|[·．]{3,})\s*\d*\s*$")
REFERENCE = re.compile(r"^(?:规定|要求|中的|的|和|至|第|款|[（(]|界定|将|确立|涉及|仅|为根据)")
HEADINGS = re.compile(r"^h[1-6]$")


def _number(raw):
    raw = re.sub(r"\s+", "", raw).translate(str.maketrans("０１２３４５６７８９．", "0123456789."))
    if re.fullmatch(r"\d+(?:\.\d+)*", raw):
        return raw.replace(".", "-") if "." in raw else str(int(raw))
    if not re.fullmatch(r"[零〇一二三四五六七八九十百千万两]+", raw):
        return None
    digits = dict(zip("零〇一二三四五六七八九两", (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 2)))
    if all(char in digits for char in raw):
        return str(int("".join(str(digits[char]) for char in raw)))
    # Reject malformed OCR (一百百/十百/一二十), never guess its intended number.
    if raw.count("万") > 1:
        return None
    for part in raw.split("万"):
        units = [{"十": 10, "百": 100, "千": 1000}[c] for c in part if c in "十百千"]
        if any(a <= b for a, b in zip(units, units[1:])) or re.search(r"[一二三四五六七八九两]{2}", part):
            return None
    total = section = digit = 0
    for char in raw:
        if char in digits:
            digit = digits[char]
        elif char == "万":
            total += (section + digit) * 10000
            section = digit = 0
        else:
            section += (digit or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            digit = 0
    return str(total + section + digit)


def _legal_heading(title):
    match = ORDINAL.fullmatch(title.strip())
    if not match:
        return None
    number = _number(match[1])
    if not number or (match[2] == "章" and "-" in number):
        return None
    tail = match[3]
    # Whitespace is required after 条: 第25.603条要求… is a reference, not a heading.
    if tail and match[2] == "条" and not tail[0].isspace():
        return None
    if REFERENCE.match(re.sub(r"\s+", "", tail)):
        return None
    if match[2] == "章" and not LEADER.search(tail) and (len(tail) > 120 or re.search(r"[。；]", tail)):
        return None
    kind = "clause" if match[2] == "条" else "chapter"
    return kind, f"{kind}-{number}", title[:len(title) - len(tail)] if tail else title, tail


def _line_heading(line, previous=""):
    title = line.strip()
    marked = re.match(r"^(#{1,6})\s+(.+)$", title)
    if marked:
        return len(marked[1]), marked[2], ""
    page = re.fullmatch(r"#{1,6}\s*(第\s*\d+\s*页)", title)
    if page:
        return 2, page[1], ""
    if re.sub(r"\s+", "", title) == "目录":
        return 2, title, ""
    legal = _legal_heading(title)
    if not legal:
        return None
    kind, _, label, tail = legal
    # A standalone number inside a vertical PDF table is not a section boundary.
    if kind == "clause" and not tail.strip() and previous.strip():
        return None
    if kind == "clause" and not LEADER.search(tail) and (len(tail) > 45 or re.search(r"[。；，]", tail)):
        return 3, label, tail
    return (3 if kind == "clause" else 2), title, ""


def clean_extracted_text(text):
    """Normalize line endings/NULs, preserving word and heading separators."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return re.sub(r"\n{4,}", "\n\n\n", text).strip()


def extracted_html(text):
    """Treat extraction as literal text, with only explicit structural labels."""
    blocks, paragraph = [], []
    section, length = 0, 0

    def flush():
        nonlocal section, length
        if paragraph:
            raw = "\n".join(paragraph)
            # Reading aids may precede a paragraph but never cut a word/formula.
            if length + len(raw) >= 8000:
                section += 1
                blocks.append(f'<h3>阅读分段 {section:02}（自动定位）</h3>')
                length = 0
            blocks.append('<p class="extracted-block">' + escape(raw) + '</p>')
            length += len(raw)
            paragraph.clear()

    previous = ""
    for line in text.splitlines():
        stripped = line.strip()
        heading = _line_heading(line, previous)
        if heading:
            flush()
            level, title, tail = heading
            blocks.append(f'<h{level}>' + escape(title) + f'</h{level}>')
            length = 0
            if tail:
                paragraph.append(tail)
        elif not stripped:
            flush()
        else:
            paragraph.append(line)
        previous = line
    flush()
    return "\n".join(blocks)


def _markdown_html(text):
    lines, fence, previous = [], "", ""
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            if not fence:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = ""
            lines.append(line)
        elif fence or line.startswith(("    ", "\t")):
            lines.append(line)
        else:
            heading = _line_heading(line, previous)
            if heading:
                level, title, tail = heading
                lines.extend(["", f"<h{level}>{escape(title)}</h{level}>", ""])
                if tail:
                    lines.extend([tail, ""])
            else:
                lines.append(line)
        previous = line
    return markdown.markdown("\n".join(lines), extensions=["tables", "fenced_code", "sane_lists"])


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _render_indexed(text, extracted=False):
    html = extracted_html(text) if extracted else _markdown_html(text)
    tags = ["p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "strong", "em", "blockquote", "a", "code", "pre", "table", "thead", "tbody", "tr", "th", "td", "sup", "sub"]
    html = bleach.clean(html, tags=tags, attributes={"a": ["href", "title"], "p": ["class"], "th": ["colspan", "rowspan"], "td": ["colspan", "rowspan"]}, protocols=["http", "https"], strip=True)
    soup = BeautifulSoup(html, "html.parser")
    toc, locations, counts = [], [], Counter()
    in_directory, directory_numbers, clause = False, set(), ""
    for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td"]):
        if node.find_parent(["pre", "code", "blockquote"]) or node.find(["p", "li"]):
            continue
        literal = node.get_text()
        title = literal.strip()
        is_heading = bool(HEADINGS.fullmatch(node.name))
        legal = _legal_heading(title) if is_heading else None
        is_directory = re.sub(r"\s+", "", title) == "目录"
        if is_directory:
            in_directory, clause = True, ""
            directory_numbers.clear()
        if is_heading and title == "正文":
            in_directory = False
        if in_directory and not is_heading:
            # Numeric outlines are not headings. A substantive narrative line
            # can end their directory, but grants paragraph evidence only.
            for prose in re.finditer(r"(?m)^.*[。；].*$", literal):
                if len(prose[0].strip()) >= 20 and not LEADER.search(prose[0]):
                    literal = literal[prose.start():]
                    title = literal.strip()
                    in_directory, clause = False, ""
                    break
        page = PAGE.fullmatch(title) if is_heading else None
        kind, base = "paragraph", "paragraph-" + _digest(literal)
        if legal:
            kind, base = legal[:2]
            if in_directory and base in directory_numbers and not LEADER.search(title):
                in_directory = False
            if in_directory or LEADER.search(title):
                directory_numbers.add(base)
                kind, base = "toc_entry", "toc-" + base
        elif page:
            kind, base = "page", "page-" + str(int(page[1]))
        elif is_heading:
            kind, base = "heading", "section-" + _digest(title)
            if re.fullmatch(r"阅读分段 \d+（自动定位）", title):
                kind = "segment"
        counts[base] += 1
        anchor = base if counts[base] == 1 else f"{base}--{counts[base]}"
        node["id"] = anchor
        if is_heading:
            toc.append(dict(id=anchor, text=title, level=int(node.name[1]), kind=kind))
            if kind == "clause":
                clause = anchor
            elif kind not in {"page", "segment"}:
                clause = ""
        if kind == "paragraph" and clause:
            # A rejected heading may still start a new article. Clear this whole
            # block and following prose even when its number/tail is uncertain,
            # including blocks excluded from evidence by the directory filter.
            if any(CLAUSE_BOUNDARY.match(line.strip()) for line in literal.splitlines()):
                clause = ""
        if in_directory or is_directory or kind == "toc_entry" or LEADER.search(title):
            continue
        if kind not in {"paragraph", "clause"} or not title:
            continue
        # Evidence must be a verbatim substring of the supplied body. For formatted
        # Markdown, use individual text runs rather than invent a joined quotation.
        runs = [literal] if literal in text else [str(run) for run in node.strings if str(run) in text]
        for run in runs:
            if run.strip():
                locations.append(dict(id=anchor, text=run, kind=kind, clause=clause))
    for link in soup.find_all("a", href=True):
        if link["href"].startswith(("http://", "https://")):
            link["target"] = "_blank"
            link["rel"] = "noopener noreferrer"
    return str(soup), toc, locations


def document_locations(text, extracted=False):
    """Return verbatim text runs and IDs allocated by the same reader pipeline.

    Directory entries, code, block quotes and inferred numeric subsections are
    excluded. ``clause`` is empty outside an explicit article, and resets at a
    chapter or other heading (but persists across explicit PDF page boundaries).
    Any unpromoted article-like prefix conservatively clears article ownership;
    recognizing that boundary does not require accepting its number or title.
    This is a location index, not a statement of legal or semantic authority.
    """
    return _render_indexed(text, extracted)[2]


def render_document(text, extracted=False):
    """Return (sanitized HTML, TOC); existing callers need no signature changes."""
    html, toc, _ = _render_indexed(text, extracted)
    return html, toc
