"""Golden tests: every evidence rule from the case-study data, enforced in code."""
import pytest

from app.models import Draft
from app.services import ranker
from app.services.entitlement import NotEntitled, authorize
from app.services.evidence import build_fact_pack
from app.services.signals import detect_all
from app.services.verifier import verify


def packs(ctx):
    signals = detect_all(ctx)
    return {i.type: build_fact_pack(ctx, i, signals) for i in ranker.rank(ctx, signals)}, signals


# ---------------------------------------------------------------- access
def test_region_boundary(source):
    with pytest.raises(NotEntitled):
        authorize(source, "U101", "A103")   # Alex (T1) -> Casey (T2)
    authorize(source, "U102", "A103")       # Sam (T2) -> Casey (T2)


# ---------------------------------------------------------------- joins / share-class resolution
def test_activity_share_class_resolution(ctx):
    c = ctx("U101", "A101")
    by_act = {m.evidence_id: m for m in c.mentions if m.source == "activity"}
    assert by_act["ACT101"].share_class_id == "P101I" and by_act["ACT101"].resolution == "text_match"
    assert by_act["ACT102"].share_class_id == "P101I" and by_act["ACT102"].resolution == "thread"
    c3 = ctx("U102", "A103")
    m = next(m for m in c3.mentions if m.evidence_id == "ACT105")
    assert m.share_class_id == "P102A" and m.resolution == "single_class"


def test_fund_reference_joined_on_share_class(ctx):
    c = ctx("U101", "A101")
    assert set(c.fund_refs) == {"P101I", "P102A"}


# ---------------------------------------------------------------- signals + ranking
def test_riley_signals_and_primary_intent(ctx):
    c = ctx("U101", "A101")
    types = {s.type for s in detect_all(c)}
    assert {"open_request", "significant_trade"} <= types
    intents = ranker.rank(c, detect_all(c))
    assert intents[0].type == "fulfil_request"
    assert any(sid.startswith("SIG-TRADE") for sid in intents[0].supporting_signal_ids)


def test_jordan_firm_move_and_birthday(ctx):
    c = ctx("U101", "A102")
    sigs = {s.type: s for s in detect_all(c)}
    assert sigs["firm_move"].details["reconnect_requested"] is True
    assert sigs["firm_move"].details["timeframe"] == "later this month"
    assert sigs["birthday"].details["days_until"] == 4
    assert ranker.rank(c, list(sigs.values()))[0].type == "firm_move_reconnect"


def test_riley_birthday_not_a_signal(ctx):
    assert all(s.type != "birthday" for s in detect_all(ctx("U101", "A101")))


# ---------------------------------------------------------------- evidence rules
def test_wrong_share_class_document_excluded(ctx):
    p, _ = packs(ctx("U101", "A101"))
    pack = p["fulfil_request"]
    assert {l.content_id for l in pack.links} == {"D101", "D102"}
    assert any(e.item.startswith("D103") and "share class A" in e.reason for e in pack.exclusions)


def test_internal_document_blocked_and_gap_raised(ctx):
    p, _ = packs(ctx("U102", "A103"))
    pack = p["fulfil_request"]
    assert pack.links == []
    assert any(e.item.startswith("D104") and "internal" in e.reason for e in pack.exclusions)
    assert any("factsheet" in g for g in pack.gaps)
    assert any(a.type == "request_material" for a in pack.actions)


def test_unanswered_outbound_is_not_interest(ctx):
    p, _ = packs(ctx("U101", "A102"))
    pack = p["firm_move_reconnect"]
    assert any(e.item.startswith("ACT104") for e in pack.exclusions)
    assert "webinar" in pack.banned_terms


def test_holding_drop_is_not_a_redemption(ctx):
    p, _ = packs(ctx("U101", "A101"))
    pack = p["fulfil_request"]
    assert any("Oakbridge" in e.item and "redemption" in e.reason for e in pack.exclusions)
    assert "redemption" in pack.banned_terms


def test_missing_records_mean_unknown(ctx):
    p, _ = packs(ctx("U101", "A102"))
    reasons = " ".join(e.reason for e in p["firm_move_reconnect"].exclusions)
    assert "unknown, not zero" in reasons


def test_performance_optional_dated_and_disclosed(ctx):
    p, _ = packs(ctx("U101", "A101"))
    perf = next(f for f in p["fulfil_request"].facts if f.kind == "performance")
    assert perf.included is False and perf.optional is True
    assert perf.as_of.isoformat() == "2026-10-31" and "Past performance" in perf.disclosure
    p3, _ = packs(ctx("U102", "A103"))
    perf3 = next(f for f in p3["fulfil_request"].facts if f.kind == "performance")
    assert perf3.warning and "compliance review" in perf3.warning


def test_concise_tone_from_relationship_notes(ctx):
    p, _ = packs(ctx("U101", "A101"))
    assert p["fulfil_request"].tone.style == "concise"


def test_firm_move_actions_include_scheduling_and_contact_check(ctx):
    p, _ = packs(ctx("U101", "A102"))
    types = {a.type for a in p["firm_move_reconnect"].actions}
    assert {"schedule_meeting", "verify_contact", "log_activity"} <= types


# ---------------------------------------------------------------- claim checker
CATALOG = ["Riverstone Income Fund", "Oakbridge Equity Fund"]


def test_verifier_flags_unsupported_claims(ctx):
    p, _ = packs(ctx("U101", "A101"))
    pack = p["fulfil_request"]
    bad = Draft(generator="test", subject="Hi", body=(
        "You invested $40,000 and the fund returned 9.9%. See https://example.invalid/D103.pdf. "
        "Also consider Oakbridge Equity Fund after your redemption."))
    v = verify(bad, pack, CATALOG)
    joined = " ".join(v.issues)
    assert not v.passed
    for needle in ("$40,000", "9.9%", "D103", "Oakbridge", "redemption"):
        assert needle in joined


def test_verifier_requires_disclosure_when_performance_included(ctx):
    c = ctx("U101", "A101")
    signals = detect_all(c)
    intent = ranker.rank(c, signals)[0]
    pack = build_fact_pack(c, intent, signals,
                           included_override={"F-DOC-D101", "F-DOC-D102", "F-TRADE", "F-PERF-P101I"})
    d = Draft(generator="test", subject="s", body="As of 31 Oct 2026 the one-year return was 5.2%.")
    assert any("disclosure" in i for i in verify(d, pack, CATALOG).issues)


def test_verifier_flags_internal_ids_but_not_urls(ctx):
    p, _ = packs(ctx("U102", "A103"))
    pack = p["fulfil_request"]
    leak = Draft(generator="test", subject="s", body="The factsheet for P102A (see ACT105) will follow.")
    assert any("Internal identifiers" in i for i in verify(leak, pack, CATALOG).issues)
    p1, _ = packs(ctx("U101", "A101"))
    ok = Draft(generator="test", subject="s", body="Factsheet: https://example.invalid/D101.pdf")
    assert not any("Internal identifiers" in i for i in verify(ok, p1["fulfil_request"], CATALOG).issues)
