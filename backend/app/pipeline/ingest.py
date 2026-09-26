"""Stage 1: PDF -> doc_text + offset map (TRD §5.1).

Everything downstream (verification, pages, clause spans) indexes into `doc_text`, so this
module is the one place that decides what text the contract "contains". Invisible text is
dropped here, which closes the hidden-text prompt-injection route.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field

import pymupdf as fitz

from app.errors import ConanError
from app.pipeline import verify

MAGIC = b"%PDF-"
HEADER_FOOTER_BAND = 0.08  # top/bottom 8% of page height
MIN_FONT_PT = 4.0

# MuPDF per-span char_flags: a glyph that is neither filled nor stroked is render mode 3 (invisible).
_CHAR_FILLED, _CHAR_STROKED = 16, 32
_BOLD_FLAG = 16  # span["flags"] bit 4
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s*)?[-–—]?\s*\d{1,4}\s*[-–—]?\s*(?:(?:of|/)\s*\d{1,4})?\s*$", re.I)


@dataclass(frozen=True)
class Line:
    char_start: int
    char_end: int  # exclusive; doc_text[char_start:char_end] == text (no trailing newline)
    page_no: int  # 1-based physical page
    y0: float
    is_bold: bool
    font_size: float
    block_start: bool  # first line of a PyMuPDF block (paragraph-ish boundary)
    text: str


@dataclass
class IngestResult:
    doc_text: str
    lines: list[Line]
    page_offsets: list[tuple[int, int]]  # index = page_no - 1
    page_count: int
    dropped_invisible: int = 0
    dropped_header_footer: int = 0
    warnings: list[str] = field(default_factory=list)

    def page_of(self, offset: int) -> int:
        return verify.page_of(self.page_offsets, offset)


def check_bytes(data: bytes, max_bytes: int) -> None:
    if len(data) > max_bytes:
        raise ConanError("TOO_LARGE")
    if MAGIC not in data[:1024]:
        raise ConanError("NOT_PDF")


def _is_invisible(span: dict, page_rect: fitz.Rect) -> bool:
    if span.get("alpha", 255) == 0:
        return True
    cf = span.get("char_flags")
    if cf is not None and not cf & (_CHAR_FILLED | _CHAR_STROKED):
        return True
    color = span.get("color", 0)
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    if min(r, g, b) >= 245:  # white-on-white; we assume a white page background
        return True
    if span.get("size", 12) < MIN_FONT_PT:
        return True
    return not fitz.Rect(span["bbox"]).intersects(page_rect)


@dataclass
class _RawLine:
    page_no: int
    y0: float
    y1: float
    page_h: float
    is_bold: bool
    font_size: float
    block_start: bool
    text: str


def _norm_hf(text: str) -> str:
    return re.sub(r"\d+", "#", " ".join(text.lower().split()))


def extract(data: bytes, *, max_bytes: int, max_pages: int, timeout_s: float) -> IngestResult:
    """CPU-bound; call via asyncio.to_thread. Caps are checked before the full parse."""
    check_bytes(data, max_bytes)
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # corrupt file with a %PDF- header
        raise ConanError("NOT_PDF") from exc
    with doc:
        if doc.needs_pass or doc.is_encrypted:
            raise ConanError("ENCRYPTED")
        if doc.page_count > max_pages:
            raise ConanError("TOO_MANY_PAGES")
        if doc.page_count == 0:
            raise ConanError("NO_TEXT_LAYER")

        deadline = time.monotonic() + timeout_s
        raw: list[_RawLine] = []
        invisible = 0
        for page in doc:
            if time.monotonic() > deadline:
                raise ConanError("INTERNAL", "parse timeout")
            rect = page.rect
            blocks = page.get_text("dict", sort=True, flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)["blocks"]
            for block in blocks:
                first = True
                for line in block.get("lines", []):
                    spans = []
                    for s in line["spans"]:
                        if _is_invisible(s, rect):
                            invisible += 1
                        else:
                            spans.append(s)
                    text = "".join(s["text"] for s in spans)
                    if not text.strip():
                        continue
                    visible = [s for s in spans if s["text"].strip()]
                    bold = all(s["flags"] & _BOLD_FLAG or "bold" in s["font"].lower() for s in visible)
                    size = max(s["size"] for s in visible)
                    y0 = min(s["bbox"][1] for s in visible)
                    y1 = max(s["bbox"][3] for s in visible)
                    raw.append(_RawLine(page.number + 1, y0, y1, rect.height, bold, size, first, text.rstrip()))
                    first = False
        page_count = doc.page_count

    hf_drop = _header_footer_indices(raw, page_count)

    parts: list[str] = []
    lines: list[Line] = []
    page_offsets: list[tuple[int, int]] = []
    pos = 0
    by_page: dict[int, list[int]] = {}
    for i, rl in enumerate(raw):
        by_page.setdefault(rl.page_no, []).append(i)
    for p in range(1, page_count + 1):
        start = pos
        for i in by_page.get(p, []):
            if i in hf_drop:
                continue
            rl = raw[i]
            lines.append(Line(pos, pos + len(rl.text), p, rl.y0, rl.is_bold, rl.font_size, rl.block_start, rl.text))
            parts.append(rl.text + "\n")
            pos += len(rl.text) + 1
        page_offsets.append((start, pos))
    doc_text = "".join(parts)

    non_ws = sum(1 for c in doc_text if not c.isspace())
    if non_ws < 200 or non_ws / page_count < 50:
        raise ConanError("NO_TEXT_LAYER")

    return IngestResult(doc_text, lines, page_offsets, page_count,
                        dropped_invisible=invisible, dropped_header_footer=len(hf_drop))


def _header_footer_indices(raw: list[_RawLine], page_count: int) -> set[int]:
    """Lines in the top/bottom band whose digit-normalized text repeats on >= 50% of pages,
    plus standalone page numbers in the band."""
    def in_band(rl: _RawLine) -> bool:
        return rl.y1 <= rl.page_h * HEADER_FOOTER_BAND or rl.y0 >= rl.page_h * (1 - HEADER_FOOTER_BAND)

    band = [i for i, rl in enumerate(raw) if in_band(raw[i])]
    drop = {i for i in band if _PAGE_NUMBER.match(raw[i].text)}
    if page_count >= 2:
        pages_with: Counter[str] = Counter()
        for key in {(_norm_hf(raw[i].text), raw[i].page_no) for i in band}:
            pages_with[key[0]] += 1
        need = max(2, -(-page_count // 2))
        repeated = {k for k, n in pages_with.items() if n >= need}
        drop |= {i for i in band if _norm_hf(raw[i].text) in repeated}
    return drop
