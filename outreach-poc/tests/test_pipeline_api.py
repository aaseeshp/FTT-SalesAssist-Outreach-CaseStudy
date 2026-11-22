"""End-to-end: pipeline output, guardrails around agents, and the HTTP API."""
import pytest
from fastapi.testclient import TestClient

from app.agents.crew import ClassifiedIntent, IntentClassification
from app.pipeline import reconcile
from app.services import ranker
from app.services.entitlement import NotEntitled
from app.services.signals import detect_all


@pytest.mark.parametrize("user,advisor,primary", [
    ("U101", "A101", "fulfil_request"),
    ("U101", "A102", "firm_move_reconnect"),
    ("U102", "A103", "fulfil_request"),
])
def test_pipeline_drafts_pass_verification(pipeline, user, advisor, primary):
    r = pipeline.run(user, advisor)
    assert r.options[0].pack.intent.type == primary
    for o in r.options:
        assert o.verification.passed, o.verification.issues
    assert [t.key for t in r.trace] == ["access", "assemble", "signals", "intents", "evidence", "draft", "verify"]


def test_riley_draft_links_right_material(pipeline):
    body = pipeline.run("U101", "A101").options[0].draft.body
    assert "D101.pdf" in body and "D102.pdf" in body and "D103" not in body
    assert "$25,000" in body


def test_cache_rechecks_entitlement(pipeline):
    pipeline.get("U102", "A103")
    with pytest.raises(NotEntitled):
        pipeline.get("U101", "A103")
    assert pipeline.get("U102", "A103").cache == "hit"


def test_reconcile_rejects_unsupported_agent_intent(ctx):
    c = ctx("U101", "A102")
    signals = detect_all(c)
    rules = ranker.rank(c, signals)
    agent = IntentClassification(advisor_id="A102", intents=[
        ClassifiedIntent(intent_type="meeting_follow_up", confidence=0.9, evidence_ids=["ACT104"],
                         rationale="Webinar invite suggests interest"),           # breaks R1 -> rejected
        ClassifiedIntent(intent_type="firm_move_reconnect", confidence=0.95, evidence_ids=["ACT103"],
                         rationale="Confirmed move, asked to reconnect"),
    ])
    accepted, rejected = reconcile(agent, rules, signals)
    assert accepted[0].type == "firm_move_reconnect" and accepted[0].score == 0.95
    assert rejected[0]["intent_type"] == "meeting_follow_up"
    assert any(i.type == "birthday_greeting" for i in accepted)  # rules keep what the agent missed


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_api_flow(client):
    assert client.get("/api/health").json()["status"] == "ok"
    rows = client.get("/api/advisors", params={"user_id": "U101"}).json()
    assert {r["advisor_id"] for r in rows} == {"A101", "A102"}
    all_rows = client.get("/api/advisors", params={"user_id": "U101", "all_regions": True}).json()
    casey = next(r for r in all_rows if r["advisor_id"] == "A103")
    assert casey["in_region"] is False and casey["signals"] == []   # nothing computed outside region

    assert client.get("/api/outreach/A103", params={"user_id": "U101"}).status_code == 403
    r = client.get("/api/outreach/A101", params={"user_id": "U101"})
    assert r.status_code == 200
    opt = r.json()["options"][0]

    regen = client.post("/api/outreach/A101/regenerate", json={
        "user_id": "U101", "intent_id": opt["pack"]["intent"]["id"], "tone": "formal",
        "included_fact_ids": ["F-DOC-D101"]})
    assert regen.status_code == 200
    body = regen.json()["draft"]["body"]
    assert "Dear Riley" in body and "D101.pdf" in body and "D102.pdf" not in body


def test_actions_require_confirmation(client):
    opt = client.get("/api/outreach/A102", params={"user_id": "U101"}).json()["options"][0]
    req = {"user_id": "U101", "advisor_id": "A102", "intent_id": opt["pack"]["intent"]["id"],
           "action_ids": ["ACT-MEET", "ACT-VERIFY"]}
    assert client.post("/api/actions/execute", json=req).status_code == 400          # not confirmed
    res = client.post("/api/actions/execute", json={**req, "confirmed": True})
    assert res.status_code == 200 and len(res.json()["results"]) == 2
    assert client.post("/api/actions/execute",
                       json={**req, "action_ids": ["ACT-BOGUS"], "confirmed": True}).status_code == 400
    bad_user = {**req, "user_id": "U102", "confirmed": True}
    assert client.post("/api/actions/execute", json=bad_user).status_code == 403
