"""
Splitting cleaned pages into chunks: one chunk = one topic.

  - a heading ("Return Policy", "3. Orders") starts a new section
  - long sections are split again with overlap (LangChain splitter)
  - the heading is written into each chunk; it helps both vector and keyword search
"""
import os
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core import config
from app.rag.ingestion.cleaning import join_wrapped_lines, remove_headers_footers
from app.rag.ingestion.loaders import READERS

NUMBERED_HEADING = re.compile(r"^\d+(\.\d+)*\.?\s+[A-Z]")


def is_heading(line, next_line):
    """Short line, starts with a capital or number, no sentence punctuation at the end,
    followed by a longer line. Works for most policy/manual style PDFs."""
    s = line.strip()
    if 3 <= len(s) <= 70 and NUMBERED_HEADING.match(s) and not s.endswith("."):
        return True   # "3. Orders", "4.2 Delivery charges"
    return (
        3 <= len(s) <= 60
        and (s[0].isupper() or s[0].isdigit())
        and not s.endswith((".", ",", ";", ":", "?", "!"))
        and not s.startswith(("|", "-", "•", "*"))
        and next_line is not None
        and len(next_line.strip()) > len(s)
    )


def split_sections(pages):
    """[(page, lines)] -> [{"title", "text", "page"}], one entry per heading."""
    flat = [(n, l) for n, lines in pages for l in lines]
    sections, current = [], None
    for i, (page_no, line) in enumerate(flat):
        nxt = flat[i + 1][1] if i + 1 < len(flat) else None
        if is_heading(line, nxt):
            current = {"title": line.strip(), "lines": [], "page": page_no}
            sections.append(current)
        elif current is None:
            current = {"title": "", "lines": [line], "page": page_no}
            sections.append(current)
        else:
            current["lines"].append(line)
    out = []
    for s in sections:
        text = join_wrapped_lines(s["lines"])
        if text:
            out.append({"title": s["title"], "text": text, "page": s["page"]})
    return out

def make_chunks(path):
    reader = READERS[os.path.splitext(path)[1].lower()]
    pages = remove_headers_footers(reader(path))
    sections = split_sections(pages)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    source = os.path.basename(path)
    chunks = []
    for s in sections:
        parts = splitter.split_text(s["text"]) if len(s["text"]) > config.CHUNK_SIZE else [s["text"]]
        for i, part in enumerate(parts):
            title = s["title"] if i == 0 else f"{s['title']} (continued)"
            # The title is written into the chunk too: it helps both vector and keyword search
            content = f"{title}\n{part}" if title else part
            chunks.append({"title": title, "content": content.replace("\x00", ""), "source": source, "page": s["page"]})
    return chunks
