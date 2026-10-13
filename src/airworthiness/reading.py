"""Sanitized, deterministic Markdown rendering for local source documents."""
import re
from html import escape

import bleach
import markdown
from bs4 import BeautifulSoup


def clean_extracted_text(text):
    """Normalize whitespace without changing words, numbers or paragraph order."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"(?<=[\u3400-\u9fff])[ \t]+(?=[\u3400-\u9fff])", "", text)
    return re.sub(r"\n{4,}", "\n\n\n", text).strip()


def extracted_html(text):
    """Treat PDF extraction as literal text; preserve formulas and hard line breaks."""
    blocks, paragraph = [], []
    section, length = 0, 0

    def flush():
        nonlocal section, length
        if paragraph:
            raw = "\n".join(paragraph)
            for offset in range(0, len(raw), 8000):
                chunk = raw[offset:offset + 8000]
                if length + len(chunk) >= 8000:
                    section += 1
                    blocks.append(f'<h3>阅读分段 {section:02}（自动定位）</h3>')
                    length = 0
                blocks.append('<p class="extracted-block">' + escape(chunk) + '</p>')
                length += len(chunk)
            paragraph.clear()

    for line in text.splitlines():
        stripped = line.strip()
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush()
            level, title = len(heading[1]), heading[2]
            blocks.append(f'<h{level}>' + escape(title) + f'</h{level}>')
            length = 0
        elif not stripped:
            flush()
        else:
            paragraph.append(line)
    flush()
    return "\n".join(blocks)


def render_document(text, extracted=False):
    html = extracted_html(text) if extracted else markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    tags = ["p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "strong", "em", "blockquote", "a", "code", "pre", "table", "thead", "tbody", "tr", "th", "td", "sup", "sub"]
    html = bleach.clean(html, tags=tags, attributes={"a": ["href", "title"], "p": ["class"], "th": ["colspan", "rowspan"], "td": ["colspan", "rowspan"]}, protocols=["http", "https"], strip=True)
    soup = BeautifulSoup(html, "html.parser")
    toc = []
    for n, heading in enumerate(soup.find_all(re.compile(r"^h[1-6]$")), 1):
        anchor = f"section-{n}"
        heading["id"] = anchor
        toc.append({"id": anchor, "text": heading.get_text(" ", strip=True), "level": int(heading.name[1])})
    for link in soup.find_all("a", href=True):
        if link["href"].startswith(("http://", "https://")):
            link["target"] = "_blank"
            link["rel"] = "noopener noreferrer"
    return str(soup), toc
