"""
Cleaning page text before it is chunked.

  - remove headers/footers that repeat on most pages ("Handbook ... Page 3")
  - join lines that the PDF wrapped at the page width back into sentences
"""
import re
from collections import Counter

PAGE_NUMBER = re.compile(r"^(page\s*)?\d+(\s*(/|of)\s*\d+)?$", re.I)


def _shape(line):
    """'Handbook Page 3' and 'Handbook Page 7' have the same shape: digits don't matter."""
    return re.sub(r"\d+", "#", line.strip())


EDGE_LINES = 2   # headers/footers live in the first and last 2 lines of a page


def remove_headers_footers(pages):
    """Lines at the top or bottom of a page that repeat on most pages (title, "Page 3")
    are noise. Only the page edges are checked, so repeating body text is never removed."""
    def edges(lines):
        return set(range(min(EDGE_LINES, len(lines)))) | set(range(max(0, len(lines) - EDGE_LINES), len(lines)))

    split = [(n, [l for l in text.splitlines() if l.strip()]) for n, text in pages]
    counts = Counter()
    for _, lines in split:
        counts.update({_shape(lines[i]) for i in edges(lines)})
    repeated = {l for l, n in counts.items() if len(pages) >= 3 and n >= 0.6 * len(pages)}
    cleaned = []
    for number, lines in split:
        at_edge = edges(lines)
        kept = [l for i, l in enumerate(lines)
                if not (i in at_edge and (_shape(l) in repeated or PAGE_NUMBER.match(l.strip())))]
        cleaned.append((number, kept))
    return cleaned


def join_wrapped_lines(lines):
    """PDF text is wrapped at the page width. Join lines back into sentences,
    but keep table rows ('| a | b |') on their own lines."""
    out = []
    for line in lines:
        line = re.sub(r"[ \t]+", " ", line).strip()
        is_table = line.startswith("|")
        if out and not is_table and not out[-1].startswith("|") and not out[-1].endswith((".", ":", "!", "?")):
            out[-1] += " " + line
        else:
            out.append(line)
    return "\n".join(out).strip()
