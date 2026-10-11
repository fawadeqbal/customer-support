"""
Reading source documents into pages of text.

    read_pdf(path) -> [(page_number, text), ...]
      - text per page (pdfplumber)
      - tables kept as tables (markdown), so rows and columns stay together
      - scanned pages (images, no text layer) are read with OCR (Tesseract), if installed

To support another file type, add a reader and register it in READERS.
"""
import pdfplumber


def ocr_page(page):
    """Scanned page (an image, no text layer) -> text with Tesseract, if installed."""
    try:
        import pytesseract
        image = page.to_image(resolution=200).original
        return pytesseract.image_to_string(image)
    except Exception as e:  # Tesseract missing or failed: skip the page, keep going
        print(f"    (OCR skipped on page {page.page_number}: {e.__class__.__name__})")
        return ""


def read_pdf(path):
    """Returns [(page_number, text), ...]. Tables become markdown tables."""
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            if tables:
                boxes = [t.bbox for t in tables]

                def outside_tables(obj):
                    x0, top, x1, bottom = obj.get("x0", 0), obj.get("top", 0), obj.get("x1", 0), obj.get("bottom", 0)
                    return not any(x0 >= b[0] - 1 and x1 <= b[2] + 1 and top >= b[1] - 1 and bottom <= b[3] + 1 for b in boxes)

                text = page.filter(outside_tables).extract_text() or ""
                for t in tables:
                    rows = [[(c or "").replace("\n", " ").strip() for c in row] for row in t.extract()]
                    if rows:
                        md = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * len(rows[0])]
                        md += ["| " + " | ".join(r) + " |" for r in rows[1:]]
                        text += "\n\n" + "\n".join(md)
            else:
                text = page.extract_text() or ""
            if len(text.strip()) < 20:
                text = ocr_page(page)
            pages.append((page.page_number, text))
    return pages


READERS = {".pdf": read_pdf}
