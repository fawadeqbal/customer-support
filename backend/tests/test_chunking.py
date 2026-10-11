"""The real handbook PDF must split into one chunk per policy, without page headers/footers."""
from app.core import config
from app.rag.ingestion.chunking import make_chunks
from app.rag.ingestion.cleaning import join_wrapped_lines, remove_headers_footers

PDF = config.DATA_DIR / "shopease_support_handbook.pdf"


def test_handbook_splits_into_one_chunk_per_policy():
    chunks = make_chunks(str(PDF))
    titles = [c["title"] for c in chunks]
    assert len(chunks) == 63                         # cover + 62 policies
    for expected in ("Return Policy", "Non-Returnable Items", "Mobile Phones and PTA", "Refund Timelines",
                     "Talking to a Person", "Opening a Support Ticket", "Waiting in the Support Queue"):
        assert expected in titles
    assert next(c for c in chunks if c["title"] == "Non-Returnable Items")["page"] == 7


def test_headers_and_footers_are_removed():
    chunks = make_chunks(str(PDF))
    assert not any("Handbook Page" in c["content"] for c in chunks)


def test_repeating_header_footer_dropped_but_repeating_body_kept():
    pages = [(i, f"My Handbook\nPage {i}\nSection about topic {i}\nTotal {i * 100} PKR per order\nUnique text {i}x\nEnd of page {i}")
             for i in range(1, 6)]
    for i, lines in remove_headers_footers(pages):
        assert "My Handbook" not in lines and f"Page {i}" not in lines        # header lines at the top
        assert f"Total {i * 100} PKR per order" in lines                     # repeats, but in the body


def test_wrapped_lines_are_joined_but_tables_kept():
    text = join_wrapped_lines(["Refunds take five", "working days.", "| a | b |", "| 1 | 2 |"])
    assert text == "Refunds take five working days.\n| a | b |\n| 1 | 2 |"
