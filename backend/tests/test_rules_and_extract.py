from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.agents import extract as ex
from app.agents.intake import DONT_KNOW, detect_language
from app.domains.consumer import rules

LAKH = Decimal(100_000)
CRORE = Decimal(10_000_000)


def test_pecuniary_boundaries_follow_2021_rules() -> None:
    assert rules.pecuniary_forum(Decimal(54_999)).value == "district"
    assert rules.pecuniary_forum(50 * LAKH).value == "district"  # "does not exceed fifty lakh"
    assert rules.pecuniary_forum(50 * LAKH + 1).value == "state"
    assert rules.pecuniary_forum(2 * CRORE).value == "state"
    assert rules.pecuniary_forum(2 * CRORE + 1).value == "national"
    assert rules.pecuniary_forum(LAKH).basis[0].section_ref == "Rule 3"


def test_fee_table_from_2023_amendment() -> None:
    assert rules.filing_fee(5 * LAKH).value == 0
    assert rules.filing_fee(5 * LAKH + 1).value == 200
    assert rules.filing_fee(20 * LAKH).value == 400
    assert rules.filing_fee(50 * LAKH).value == 1000
    assert rules.filing_fee(1 * CRORE).value == 2000
    assert rules.filing_fee(11 * CRORE).value == 7500


def test_limitation_two_years_and_statuses() -> None:
    today = date(2026, 10, 30)
    ok = rules.limitation(date(2026, 3, 15), today)
    assert ok.value["deadline"] == "2028-03-15" and ok.value["status"] == "within_time"
    urgent = rules.limitation(date(2024, 12, 1), today)
    assert urgent.value["status"] == "urgent"
    expired = rules.limitation(date(2024, 1, 1), today)
    assert expired.value["status"] == "expired"
    assert "sufficient cause" in expired.explanation_en
    leap = rules.limitation(date(2024, 2, 29), today)
    assert leap.value["deadline"] == "2026-02-28"


def test_consumer_status_exclusions() -> None:
    assert rules.consumer_status("personal", False, False).value["status"] == "likely_consumer"
    assert rules.consumer_status("commercial", False, False).value["status"] == "may_not_be_consumer"
    free = rules.consumer_status(None, True, False)
    assert "free_service" in free.value["issues"]
    assert any(b.section_ref == "Section 2(42)" for b in free.basis)


async def test_rules_are_grounded_in_ingested_sources() -> None:
    from app.db.session import session_scope

    async with session_scope() as db:
        outcome = await rules.ground(db, rules.pecuniary_forum(Decimal(10_000)))
        assert outcome.grounded
        assert outcome.basis[0].source_url and outcome.basis[0].chunk_id
        missing = await rules.ground(db, rules.RuleOutcome("x", 1, "", "", [rules.Basis("nope", "Section 1", "")]))
        assert not missing.grounded and missing.caveats


def test_inr_formatting() -> None:
    assert rules._inr(Decimal(5_499_999)) == "₹54,99,999"
    assert rules._inr(Decimal(999)) == "₹999"


def test_amount_extraction_english_hindi() -> None:
    assert ex.find_amounts("I paid Rs. 54,999 for it")[0][0] == Decimal("54999.00")
    assert ex.find_amounts("मैंने 18000 रुपये दिए")[0][0] == Decimal("18000.00")
    assert ex.find_amounts("cost was 1.5 lakh")[0][0] == Decimal("150000.00")
    assert ex.find_amounts("₹ 2,500/-")[0][0] == Decimal("2500.00")


def test_date_extraction() -> None:
    today = date(2026, 10, 30)
    assert ex.find_dates("bought on 12 March 2026", today)[0][0] == date(2026, 3, 12)
    assert ex.find_dates("on 05/06/2026", today)[0][0] == date(2026, 6, 5)
    assert ex.find_dates("५ जून २०२६ को खरीदा", today)[0][0] == date(2026, 6, 5)
    d, _, approx = ex.find_dates("2 weeks ago", today)[0]
    assert approx and d == date(2026, 10, 16)
    assert ex.find_dates("on 31/02/2026", today) == []


def test_hindi_yes_no_and_skip() -> None:
    assert ex.yes_no("हाँ") is True and ex.yes_no("हां जी, सही है") is True
    assert ex.yes_no("नहीं") is False and ex.yes_no("no") is False
    assert ex.yes_no("maybe later") is None
    assert DONT_KNOW.search("पता नहीं") and DONT_KNOW.search("skip")


def test_language_detection() -> None:
    assert detect_language("मेरा फ्रिज खराब है", "en") == "hi"
    assert detect_language("mera fridge kharab ho gaya hai aur dukandar nahi sun raha", "en") == "hi"
    assert detect_language("My fridge broke", "hi") == "hi"  # defaults to the conversation language
    assert detect_language("My fridge broke", "en") == "en"


def test_category_signals() -> None:
    assert max(ex.category_scores("The seller delivered a damaged laptop and refuses refund").items(),
               key=lambda kv: kv[1])[0] == "consumer_dispute"
    assert ex.category_scores("मेरे घर में चोरी हो गई पुलिस नहीं सुन रही")["criminal_matter"] >= 2
