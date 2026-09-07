"""Extracción de texto sin OCR ni persistencia del archivo original."""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.core.exceptions import ApplicationError


@dataclass(frozen=True)
class TextPage:
    content: str
    page: int | None = None


def invalid_document(message: str) -> ApplicationError:
    return ApplicationError(message, status_code=422, code="invalid_document")


def extract_text(data: bytes, extension: str) -> tuple[list[TextPage], list[str]]:
    warnings: list[str] = []
    if extension in {".txt", ".md"}:
        try:
            pages = [TextPage(data.decode("utf-8-sig"))]
        except UnicodeDecodeError as exc:
            raise invalid_document("El archivo de texto debe usar UTF-8.") from exc
    else:
        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise invalid_document("No se admiten PDF cifrados.")
            pages = []
            for number, page in enumerate(reader.pages, start=1):
                content = page.extract_text() or ""
                if content.strip():
                    pages.append(TextPage(content, number))
                else:
                    warnings.append(
                        f"Página {number} omitida: no contiene texto extraíble; "
                        "si es una imagen, necesita OCR."
                    )
        except (
            PyPdfError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            OSError,
        ) as exc:
            raise invalid_document("No se pudo extraer el texto del PDF.") from exc
    if not any(page.content.strip() for page in pages):
        raise invalid_document(
            "El archivo no contiene texto extraíble. Los PDF escaneados necesitan OCR."
        )
    return pages, warnings
