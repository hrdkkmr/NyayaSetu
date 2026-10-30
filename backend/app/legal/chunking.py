"""Normalisation and section-aware chunking of Indian statutes and rules.

Gazette PDFs interleave three kinds of noise with the operative text:
running page headers, marginal notes (short side headings printed in the margin),
and Hindi text that some extractors render as replacement characters. We drop
these, then split on numbered sections so every chunk carries a citable reference.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_PAGE_HEADER = re.compile(
    r"^(\d+\s+)?THE GAZETTE OF INDIA\s*[:]?\s*EXTRAORDINARY.*$|^\[?P\s?ART\s+II.*$|"
    r"^SEC\.\s*\d.*\]\s*THE GAZETTE.*$|^Uploaded by Dte\. of Printing.*$|"
    r"^and Published by the Controller of Publications.*$|^\s*\d+\s*$|"
    r"^.*REGD\. No\..*$|^CG-DL-E-.*$|^xxxGID.*$|^MGIPMRND.*$|^\d+ GI/\d{4}.*$",
    re.IGNORECASE,
)
_SECTION_START = re.compile(r"^(?P<num>\d{1,3}[A-Z]?)\.\s+(?=\(?[1A-Za-z\"“])")
_CHAPTER = re.compile(r"^CHAPTER\s+([IVXLC]+)\b\s*(?P<title>[A-Z ,\-]*)$")
_DEFINITION = re.compile(
    r"^\((?P<num>\d{1,2})\)\s+[\"“](?P<term>[^\"”]{2,60})[\"”]\s+(means|includes)", re.MULTILINE
)
_TERMINAL = (".", ";", ":", ",", "—", "-", "–", ")")

MAX_CHUNK_CHARS = 1800
TARGET_CHUNK_CHARS = 1200


@dataclass
class Chunk:
    ordinal: int
    section_ref: str | None
    heading: str | None
    chapter: str | None
    text: str


def _could_be_marginal(line: str) -> bool:
    """Marginal notes are short, never open a numbered clause and never end a lead-in."""
    return (
        len(line) <= 28
        and not re.match(r"^\(\w{1,4}\)", line)
        and not line.endswith(("—", ":", ";", "-"))
        and not _SECTION_START.match(line)
        and not _CHAPTER.match(line)
    )


def _is_marginal_run(lines: list[str]) -> bool:
    return len(lines) >= 2 and all(_could_be_marginal(line) for line in lines)


def normalise(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw)
    text = text.replace("—", "—").replace("�", "")
    # Drop characters outside Latin/punctuation (rendering artefacts from Devanagari fonts).
    text = re.sub(r"[^\x09\x0a\x20-\x7e–—‘’“”₹]", " ", text)
    text = re.sub(r"P\s+ART\b", "PART", text)
    text = re.sub(r"\(\s+(\d+)\s*\)", r"(\1)", text)

    lines = [line.rstrip() for line in text.splitlines()]
    kept: list[str] = []
    run: list[str] = []

    def flush_run() -> None:
        # A run of very short lines is a block of marginal notes; drop it.
        if not _is_marginal_run([r.strip() for r in run]):
            kept.extend(run)
        run.clear()

    for line in lines:
        stripped = line.strip()
        # Lines left with almost no Latin letters are residue of stripped Devanagari text
        # in bilingual Gazette notifications.
        if not stripped or _PAGE_HEADER.match(stripped) or len(re.findall(r"[A-Za-z]", stripped)) < 3:
            flush_run()
            continue
        if _could_be_marginal(stripped):
            run.append(stripped)
            continue
        flush_run()
        kept.append(stripped)
    flush_run()

    # Re-join wrapped lines into paragraphs; keep breaks before numbered units.
    out: list[str] = []
    for line in kept:
        starts_unit = bool(
            _SECTION_START.match(line)
            or _CHAPTER.match(line)
            or re.match(r"^\(\w{1,4}\)\s", line)
            or line.startswith(("Provided", "Explanation", "TABLE", "Sl. No"))
        )
        if out and not starts_unit and not out[-1].endswith(_TERMINAL[:3]):
            out[-1] = f"{out[-1]} {line}"
        elif out and not starts_unit and out[-1].endswith(("—", "-")):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    joined = "\n".join(out)
    joined = re.sub(r"[ \t]{2,}", " ", joined)
    return joined.strip()


def _split_long(text: str) -> list[str]:
    """Split an over-long section at sub-section or clause boundaries."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    units = re.split(r"\n(?=\(\w{1,4}\)\s|Provided|Explanation)", text)
    parts: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + len(unit) + 1 > TARGET_CHUNK_CHARS:
            parts.append(current)
            current = unit
        else:
            current = f"{current}\n{unit}" if current else unit
        while len(current) > MAX_CHUNK_CHARS:
            cut = current.rfind(" ", 0, TARGET_CHUNK_CHARS)
            cut = cut if cut > 200 else TARGET_CHUNK_CHARS
            parts.append(current[:cut])
            current = current[cut:].lstrip()
    if current:
        parts.append(current)
    return parts


def chunk_statute(text: str, unit_label: str = "Section") -> list[Chunk]:
    """Chunk normalised text by numbered section (Acts) or rule (Rules)."""
    chunks: list[Chunk] = []
    chapter: str | None = None
    pending_chapter: str | None = None
    current_ref: str | None = None
    current_lines: list[str] = []
    preamble: list[str] = []
    last_num = 0

    def emit() -> None:
        nonlocal current_lines
        if not current_lines:
            return
        body = "\n".join(current_lines).strip()
        heading = current_lines[0][:160]
        for piece in _emit_pieces(body, current_ref):
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    section_ref=piece[0],
                    heading=heading,
                    chapter=chapter,
                    text=piece[1],
                )
            )
        current_lines = []

    lines = text.split("\n")
    for index, line in enumerate(lines):
        chapter_match = _CHAPTER.match(line)
        if chapter_match:
            title = chapter_match.group("title").strip()
            if not title and index + 1 < len(lines) and lines[index + 1].isupper():
                title = lines[index + 1].strip()
            pending_chapter = f"Chapter {chapter_match.group(1)} — {title.title()}".rstrip(" —")
            continue
        if pending_chapter and line.isupper() and len(line) < 120:
            continue
        match = _SECTION_START.match(line)
        if match:
            num_text = match.group("num")
            num = int(re.match(r"\d+", num_text).group())  # type: ignore[union-attr]
            # Accept only forward progress so stray numbered lines (tables, clauses) don't split.
            if num == last_num + 1 or (num == last_num and num_text[-1].isalpha()) or last_num == 0:
                emit()
                if pending_chapter:
                    chapter = pending_chapter
                    pending_chapter = None
                last_num = num
                current_ref = f"{unit_label} {num_text}"
                current_lines = [line]
                continue
        if current_ref is None:
            preamble.append(line)
        else:
            current_lines.append(line)
    emit()

    if preamble:
        pre_text = "\n".join(preamble).strip()
        if len(pre_text) > 40:
            for i, piece in enumerate(_split_long(pre_text)):
                chunks.insert(i, Chunk(0, "Preamble", pre_text[:160], None, piece))
    for i, chunk in enumerate(chunks):
        chunk.ordinal = i
    return chunks


def _emit_pieces(body: str, ref: str | None) -> list[tuple[str | None, str]]:
    # Definitions sections are split per defined term so each term is citable.
    if ref and ref.endswith(" 2") and _DEFINITION.search(body.replace("\n", "\n")):
        pieces: list[tuple[str | None, str]] = []
        blocks = re.split(r"\n(?=\(\d{1,2}\)\s+[\"“])", body)
        for block in blocks:
            m = re.match(r"^\((\d{1,2})\)\s+[\"“]", block)
            sub = f"{ref}({m.group(1)})" if m else ref
            for part in _split_long(block):
                pieces.append((sub, part))
        return pieces
    return [(ref, part) for part in _split_long(body)]
