from io import BytesIO
from unittest.mock import Mock

import pytest

from app.core.exceptions import ApplicationError
from app.services.chunking import chunk_pages
from app.services.extraction import TextPage, extract_text
from app.services.file_ingestion import MAX_UPLOAD_BYTES, FileIngestionService
from tests.pdf_factory import make_pdf


@pytest.mark.parametrize(
    "length, count", [(1, 1), (999, 1), (1000, 1), (1001, 2), (1800, 2), (1801, 3)]
)
def test_chunk_boundaries_and_overlap(length: int, count: int) -> None:
    text = "abcdefghij" * (length // 10) + "x" * (length % 10)
    chunks = chunk_pages([TextPage(text)], document_id="doc", source="a.txt")
    assert len(chunks) == count
    assert all(0 < len(chunk.content) <= 1000 for chunk in chunks)
    assert chunks[-1].content == text[(count - 1) * 800 :]
    for left, right in zip(chunks, chunks[1:], strict=False):
        assert left.content[-200:] == right.content[:200]


def test_normalizes_newlines_and_keeps_page_boundaries() -> None:
    chunks = chunk_pages(
        [TextPage(" \r\nHello\rworld\r\n ", 1), TextPage(" ", 2), TextPage("Next", 3)],
        document_id="doc",
        source="a.pdf",
    )
    assert [(c.content, c.page) for c in chunks] == [("Hello\nworld", 1), ("Next", 3)]


def test_real_pdf_extraction_warns_for_blank_pages() -> None:
    pages, warnings = extract_text(make_pdf("First page", "", "Third page"), ".pdf")
    assert [(p.content.strip(), p.page) for p in pages] == [
        ("First page", 1),
        ("Third page", 3),
    ]
    assert len(warnings) == 1
    assert "Página 2" in warnings[0]


def test_reuploads_have_stable_keys_and_changed_files_have_new_identity() -> None:
    store = Mock()
    service = FileIngestionService(store)
    first = service.ingest("folder/a.txt", BytesIO(b"Text"))
    first_chunks = store.index_chunks.call_args.args[0]
    repeated = service.ingest("a.txt", BytesIO(b"Text"))
    assert repeated == first
    assert store.index_chunks.call_args.args[0] == first_chunks
    assert (
        service.ingest("a.txt", BytesIO(b"New text")).document_id != first.document_id
    )
    assert service.ingest("b.txt", BytesIO(b"Text")).document_id != first.document_id
    assert first.source == "a.txt"


@pytest.mark.parametrize(
    "filename,data,code",
    [
        ("a.txt", b"", 422),
        ("a.md", b" \r\n", 422),
        ("a.txt", b"\xff", 422),
        ("a.pdf", b"not a pdf", 422),
        ("a.pdf", make_pdf(""), 422),
        ("a.pdf", make_pdf("Secret", encrypted=True), 422),
        ("a.csv", b"hello", 415),
        (None, b"hello", 422),
        ("a" * 256 + ".txt", b"hello", 422),
        ("a.txt", b"a" * (MAX_UPLOAD_BYTES + 1), 413),
    ],
)
def test_invalid_files_do_not_write(
    filename: str | None, data: bytes, code: int
) -> None:
    store = Mock()
    with pytest.raises(ApplicationError) as error:
        FileIngestionService(store).ingest(filename, BytesIO(data))
    assert error.value.status_code == code
    store.index_chunks.assert_not_called()


def test_accepts_exact_size_limit() -> None:
    store = Mock()
    result = FileIngestionService(store).ingest(
        "a.txt", BytesIO(b"x" + b" " * (MAX_UPLOAD_BYTES - 1))
    )
    assert result.indexed_chunks == 1


def test_utf8_bom_and_windows_filename() -> None:
    store = Mock()
    result = FileIngestionService(store).ingest(
        "C:\\docs\\manual.MD", BytesIO("\ufeff# Guía\r\nInformación".encode())
    )
    assert result.source == "manual.MD"
    assert store.index_chunks.call_args.args[0][0].content == "# Guía\nInformación"
