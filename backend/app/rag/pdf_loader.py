import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any

from PyPDF2 import PdfReader


BACKEND_DIR = Path(__file__).resolve().parents[2]
CASE_PATTERN = re.compile(
    r"(?im)(?:^|\n)\s*(?:Kasus\s*(?:No\.?|Nomor)\s*\d+|Kasus\s+\d+)\b"
)
HEADING_PATTERN = re.compile(
    r"(?im)^\s*(?:BAB\s+[A-Z0-9IVXLC]+|Pasal\s+\d+[A-Z]?|"
    r"Bagian\s+[A-Z0-9]+|Paragraf\s+[A-Z0-9]+|Kasus\s+No\.?\s*\d+)"
    r"[^\n]*"
)


def _resolve_docs_dir(docs_dir: str) -> Path:
    requested = Path(docs_dir)
    if requested.is_absolute():
        candidates = [requested]
    else:
        candidates = [
            Path.cwd() / requested,
            BACKEND_DIR / requested.name,
            BACKEND_DIR / "regulations_docs",
            BACKEND_DIR / "regulation_docs",
        ]
    return next(
        (candidate.resolve() for candidate in candidates if candidate.is_dir()),
        candidates[-1].resolve(),
    )


def _regulation_type(file_name: str) -> str:
    normalized = file_name.casefold()
    if "urologi" in normalized:
        return "UROLOGY_GUIDE"
    if "manual verifikasi" in normalized:
        return "CLAIM_VERIFICATION_MANUAL"
    if "permenkes" in normalized:
        return "MINISTRY_REGULATION"
    return "REGULATORY_DOCUMENT"


class SmartRegulationLoader:
    def __init__(self, docs_dir: str = "backend/regulations_docs"):
        self.docs_dir = _resolve_docs_dir(docs_dir)

    @staticmethod
    def _clean_page_text(text: str, repeated_edge_lines: set[str]) -> str:
        lines = [re.sub(r"[\t ]+", " ", line).strip() for line in text.splitlines()]
        while lines and (not lines[0] or lines[0].casefold() in repeated_edge_lines):
            lines.pop(0)
        while lines and (not lines[-1] or lines[-1].casefold() in repeated_edge_lines):
            lines.pop()
        cleaned_lines = []
        previous_blank = False
        for line in lines:
            line = re.sub(r"\.{3,}\s*$", "", line).strip()
            if not line:
                if not previous_blank:
                    cleaned_lines.append("")
                previous_blank = True
                continue
            cleaned_lines.append(line)
            previous_blank = False
        return "\n".join(cleaned_lines).strip()

    def extract_pdf_pages(self, pdf_path: str) -> list[dict[str, Any]]:
        path = Path(pdf_path)
        if not path.is_absolute() and not path.is_file():
            path = self.docs_dir / path
        if not path.is_file():
            raise FileNotFoundError(f"Regulation PDF not found: {path}")
        reader = PdfReader(str(path))
        edge_lines = Counter()
        page_lines = []
        for page in reader.pages:
            text = page.extract_text() or ""
            lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
            page_lines.append(text)
            candidates = lines[:2] + lines[-2:]
            edge_lines.update(line.casefold() for line in candidates if line and len(line) < 180)

        threshold = max(2, len(reader.pages) // 4)
        repeated_edge_lines = {
            line for line, count in edge_lines.items() if count >= threshold
        }
        doc_name = re.sub(r"[_]+", " ", path.stem).strip()
        return [
            {
                "doc_name": doc_name,
                "file_name": path.name,
                "page_number": page_number,
                "clean_text": self._clean_page_text(text, repeated_edge_lines),
            }
            for page_number, text in enumerate(page_lines, start=1)
        ]

    @staticmethod
    def _split_regular_text(
        text: str, chunk_size: int = 500, overlap: int = 80
    ) -> list[tuple[int, int, str]]:
        chunks = []
        headings = list(HEADING_PATTERN.finditer(text))
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                boundary = max(text.rfind("\n", start + chunk_size // 2, end),
                               text.rfind(" ", start + chunk_size // 2, end))
                if boundary > start:
                    end = boundary
            chunk = text[start:end].strip()
            heading = next(
                (match.group(0).strip() for match in reversed(headings) if match.start() <= start),
                "",
            )
            if heading and not chunk.startswith(heading):
                chunk = f"{heading}\n{chunk}"
            if chunk:
                chunks.append((start, end, chunk))
            if end >= len(text):
                break
            start = max(start + 1, end - overlap)
            while start < len(text) and text[start].isspace():
                start += 1
        return chunks

    @staticmethod
    def _page_at(page_ranges: list[tuple[int, int, int]], offset: int) -> int:
        for start, end, page_number in page_ranges:
            if start <= offset < end:
                return page_number
            if offset < start:
                return page_number
        return page_ranges[-1][2] if page_ranges else 1

    def smart_chunk_text(
        self,
        pages_data: list[dict[str, Any]],
        chunk_size: int = 500,
        overlap: int = 80,
    ) -> list[dict[str, Any]]:
        if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("Require chunk_size > overlap >= 0.")
        grouped: dict[str, list[dict[str, Any]]] = {}
        for page in pages_data:
            source = str(page.get("file_name") or page.get("doc_name") or "unknown.pdf")
            grouped.setdefault(source, []).append(page)
        chunks = []
        for source, pages in grouped.items():
            pages.sort(key=lambda page: int(page["page_number"]))
            parts = []
            page_ranges = []
            offset = 0
            for page in pages:
                text = str(page.get("clean_text", "")).strip()
                if not text:
                    continue
                if parts:
                    parts.append("\n\n")
                    offset += 2
                start = offset
                parts.append(text)
                offset += len(text)
                page_ranges.append((start, offset, int(page["page_number"])))
            full_text = "".join(parts)
            if not full_text:
                continue

            sections = []
            cases = list(CASE_PATTERN.finditer(full_text))
            cursor = 0
            for index, match in enumerate(cases):
                if match.start() > cursor:
                    sections.extend(
                        (
                            cursor + start,
                            cursor + end,
                            text,
                        )
                        for start, end, text in self._split_regular_text(
                            full_text[cursor:match.start()], chunk_size, overlap
                        )
                    )
                end = cases[index + 1].start() if index + 1 < len(cases) else len(full_text)
                case_text = full_text[match.start():end].strip()
                if case_text:
                    sections.append((match.start(), end, case_text))
                cursor = end
            if not cases:
                sections.extend(self._split_regular_text(full_text, chunk_size, overlap))

            for chunk_number, (start, _end, text) in enumerate(sections, start=1):
                page_number = self._page_at(page_ranges, start)
                identity = f"{source}:{page_number}:{chunk_number}:{text}"
                chunks.append(
                    {
                        "chunk_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32],
                        "source_document": source,
                        "doc_name": str(pages[0].get("doc_name") or Path(source).stem),
                        "page_number": page_number,
                        "regulation_type": _regulation_type(source),
                        "text": text,
                    }
                )
        return chunks


class RegulationPDFLoader(SmartRegulationLoader):
    def extract_text_from_pdf(self, pdf_path: str) -> list[dict[str, Any]]:
        return [
            {
                "page_number": page["page_number"],
                "file_name": page["file_name"],
                "raw_text": page["clean_text"],
                "doc_name": page["doc_name"],
            }
            for page in self.extract_pdf_pages(pdf_path)
        ]

    def chunk_documents(
        self,
        documents: list[dict[str, Any]],
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> list[dict[str, Any]]:
        if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("Require chunk_size > overlap >= 0.")
        pages = [
            {
                "doc_name": document.get("doc_name") or document.get("file_name"),
                "file_name": document.get("file_name") or document.get("source_document"),
                "page_number": document["page_number"],
                "clean_text": document.get("raw_text") or document.get("clean_text", ""),
            }
            for document in documents
        ]
        return self.smart_chunk_text(pages, chunk_size=chunk_size, overlap=overlap)