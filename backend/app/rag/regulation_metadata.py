"""Curated status metadata for source PDFs used by the regulatory RAG index."""

from __future__ import annotations

from pathlib import Path
from typing import Any


_DOCUMENTS: dict[str, dict[str, Any]] = {
    "2021permenkes026.pdf": {
        "legal_status": "active",
        "berlaku_sejak": "2021-08-30",
        "dicabut_sejak": "",
        "replaced_by": "",
        "document_kind": "regulation",
    },
    "2016permenkes076.pdf": {
        "legal_status": "superseded",
        "berlaku_sejak": "",
        "dicabut_sejak": "2021-08-30",
        "replaced_by": "2021permenkes026.pdf",
        "document_kind": "regulation",
    },
}


def metadata_for_document(source_document: str) -> dict[str, Any]:
    """Return curated status, treating unclassified material as reference material."""
    filename = Path(source_document).name
    return {
        "legal_status": "reference",
        "berlaku_sejak": "",
        "dicabut_sejak": "",
        "replaced_by": "",
        "document_kind": "reference",
        **_DOCUMENTS.get(filename, {}),
    }


def registered_regulations() -> list[dict[str, str]]:
    return [
        {"source_document": filename, **{key: str(value) for key, value in metadata.items()}}
        for filename, metadata in sorted(_DOCUMENTS.items())
    ]


def old_regulation_replacement(query: str) -> str | None:
    normalized = query.casefold()
    old_names = (
        "permenkes 76 tahun 2016",
        "permenkes nomor 76 tahun 2016",
        "permenkes 76/2016",
        "2016permenkes076",
    )
    if any(name in normalized for name in old_names):
        return "Permenkes 76 Tahun 2016 telah dicabut dan digantikan oleh Permenkes 26 Tahun 2021."
    return None
