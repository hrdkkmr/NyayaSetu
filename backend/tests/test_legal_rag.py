from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from app.db.session import session_scope
from app.legal.chunking import chunk_statute, normalise
from app.legal.retrieval import search

SNAPSHOTS = Path(__file__).resolve().parents[1] / "data" / "legal_sources" / "snapshots"


def test_act_is_chunked_by_section_with_chapters() -> None:
    reader = PdfReader(str(SNAPSHOTS / "cpa_2019_gazette_210422.pdf"))
    chunks = chunk_statute(normalise("\n".join(p.extract_text() or "" for p in reader.pages)), "Section")
    refs = {c.section_ref for c in chunks}
    for n in range(1, 108):  # the Act has 107 sections
        assert any(r == f"Section {n}" or (r or "").startswith(f"Section {n}(") for r in refs), n
    assert "Section 2(7)" in refs and "Section 2(11)" in refs
    s35 = next(c for c in chunks if c.section_ref == "Section 35")
    assert "(a) the consumer" in s35.text  # clause lines are not mistaken for marginal notes
    assert s35.chapter and "Consumer Disputes Redressal Commission" in s35.chapter
    assert all(len(c.text) <= 1800 for c in chunks)


@pytest.mark.parametrize("query,expected", [
    ("how long do I have to file a consumer complaint", "Section 69"),
    ("शिकायत करने की समय सीमा क्या है", "Section 69"),
    ("which commission has jurisdiction for complaint value 3 lakh", "Rule 3"),
    ("fee for filing consumer complaint", "Rule 2"),
])
async def test_retrieval_finds_the_governing_provision(query: str, expected: str) -> None:
    async with session_scope() as db:
        result = await search(db, query, legal_domain="consumer_protection", limit=3)
    assert expected in [r.section_ref for r in result.results], [r.section_ref for r in result.results]
    assert result.confidence in ("medium", "high")


async def test_results_carry_source_metadata_and_amendment_notice() -> None:
    async with session_scope() as db:
        result = await search(db, "where can complaint be instituted complainant resides", limit=3)
    top = next(r for r in result.results if r.section_ref == "Section 34")
    assert top.source_url.startswith("https://egazette.gov.in/")
    assert top.publication_date and top.publication_date.isoformat() == "2019-08-09"
    assert top.verification_status == "fetched_official"
    assert top.effective_date is None and top.effective_date_note  # never invented
    assert top.amendment_notices and "2021" in top.amendment_notices[0]


async def test_unrelated_query_reports_low_confidence() -> None:
    async with session_scope() as db:
        result = await search(db, "patent infringement of semiconductor designs", limit=3)
    assert result.confidence in ("low", "none")


async def test_hindi_query_expansion_is_reported() -> None:
    async with session_scope() as db:
        result = await search(db, "मुआवजा कैसे मिलेगा", limit=3)
    assert result.glossary_terms and "compensation" in result.expanded_query
