"""Step 3 - Signal detection.

Each detector is a small, independently testable function that reads the assembled
context and emits typed `Signal`s with evidence IDs. Adding a new need (e.g. "market
event affecting holdings") means adding a detector here and an intent mapping in the
ranker - nothing else changes.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable

from app.models import Signal
from app.services.context import AdvisorContext

REQUEST_RX = re.compile(
    r"\b(requested|asked for|asked about|promised to send|would like (?:more )?information)\b", re.I)
PROMISE_RX = re.compile(r"\bpromised\b", re.I)
MOVE_RX = re.compile(r"\b(joining|joined|moved to|moving to|new firm|firm transition)\b", re.I)
RECONNECT_RX = re.compile(r"\b(reconnect|catch up|meet again|set up a meeting)\b", re.I)
TIMEFRAME_RX = re.compile(r"\b(later this month|this month|next week|next month|early next month)\b", re.I)
CONCISE_RX = re.compile(r"\bconcise\b", re.I)
MATERIAL_WORDS = {
    "factsheet": "Factsheet",
    "fact sheet": "Factsheet",
    "commentary": "Product commentary",
    "overview": "Product commentary",
    "investment approach": "Product commentary",
    "presentation": "Presentation",
    "prospectus": "Prospectus",
}

LOOKBACK_DAYS = 60
TRADE_WINDOW_DAYS = 14
SIGNIFICANT_TRADE_USD = 10_000
BIRTHDAY_WINDOW_DAYS = 7
NEW_MATERIAL_DAYS = 30

Detector = Callable[[AdvisorContext], list[Signal]]
DETECTORS: list[Detector] = []


def detector(fn: Detector) -> Detector:
    DETECTORS.append(fn)
    return fn


def _age(ctx: AdvisorContext, d: date) -> int:
    return (ctx.reference_date - d).days


def _is_meaningful(act) -> bool:
    return act.communication_direction.lower() in ("two-way", "inbound")


def requested_material(text: str) -> list[str]:
    low = text.lower()
    found = []
    for word, ctype in MATERIAL_WORDS.items():
        if word in low and ctype not in found:
            found.append(ctype)
    return found


@detector
def open_requests(ctx: AdvisorContext) -> list[Signal]:
    """Advisor asked for something, or we promised something, about a product."""
    threads: dict[str, dict] = {}
    for act in sorted(ctx.activities, key=lambda a: a.interaction_date):
        text = act.interaction_details or ""
        if not act.product_names or not _is_meaningful(act) or _age(ctx, act.interaction_date) > LOOKBACK_DAYS:
            continue
        if not REQUEST_RX.search(text):
            continue
        for m in ctx.mention_for_activity(act.interaction_id):
            key = m.product_id or m.product_name
            t = threads.setdefault(key, {"acts": [], "mention": m, "material": [], "promised": False})
            t["acts"].append(act)
            if m.share_class_id and (t["mention"].share_class_id is None or m.resolution == "text_match"):
                t["mention"] = m
            t["material"] += [c for c in requested_material(text) if c not in t["material"]]
            t["promised"] = t["promised"] or bool(PROMISE_RX.search(text))

    signals = []
    for i, (key, t) in enumerate(threads.items(), start=1):
        m = t["mention"]
        last = t["acts"][-1]
        label = f"{m.product_name}" + (f" Class {m.share_class_label}" if m.share_class_label else "")
        caveats = []
        if m.share_class_id is None:
            caveats.append("Share class could not be resolved from the CRM notes; material is not auto-attached.")
        signals.append(Signal(
            id=f"SIG-REQ-{i}", type="open_request",
            title=("Promised follow-up" if t["promised"] else "Open request") + f": {label}",
            date=last.interaction_date,
            evidence_ids=[a.interaction_id for a in t["acts"]],
            product_id=m.product_id, share_class_id=m.share_class_id,
            details={
                "product_name": m.product_name,
                "share_class_label": m.share_class_label,
                "resolution": m.resolution,
                "requested_material": t["material"],
                "promised": t["promised"],
                "requests": [{"id": a.interaction_id, "date": a.interaction_date.isoformat(),
                              "channel": a.interaction_channel, "text": a.interaction_details} for a in t["acts"]],
            },
            caveats=caveats,
        ))
    return signals


@detector
def firm_move(ctx: AdvisorContext) -> list[Signal]:
    """Advisor changed firms - a reason to congratulate and reconnect."""
    evidence, texts, when = [], [], None
    for act in ctx.activities:
        if _age(ctx, act.interaction_date) <= LOOKBACK_DAYS and MOVE_RX.search(act.interaction_details or ""):
            evidence.append(act.interaction_id)
            texts.append(act.interaction_details or "")
            when = max(when, act.interaction_date) if when else act.interaction_date
    comments = ctx.advisor.relationship_comments or ""
    if MOVE_RX.search(comments) or "moved" in comments.lower():
        evidence.append(f"PROFILE:{ctx.advisor.advisor_id}")
        texts.append(comments)
    if not evidence:
        return []
    joined = " ".join(texts)
    tf = TIMEFRAME_RX.search(joined)
    return [Signal(
        id="SIG-MOVE-1", type="firm_move",
        title=f"Joined {ctx.advisor.advisor_firm_name}",
        date=when, evidence_ids=evidence,
        details={
            "new_firm": ctx.advisor.advisor_firm_name,
            "reconnect_requested": bool(RECONNECT_RX.search(joined)),
            "timeframe": tf.group(1).lower() if tf else None,
            "notes": texts,
        },
        caveats=["Email address on file may belong to the previous firm - confirm before sending."],
    )]


@detector
def significant_trade(ctx: AdvisorContext) -> list[Signal]:
    s = ctx.sale
    if not s or _age(ctx, s.most_recent_transaction_date) > TRADE_WINDOW_DAYS:
        return []
    prev = s.previous_transaction_amount or 0
    big = s.most_recent_transaction_amount >= SIGNIFICANT_TRADE_USD or (prev and s.most_recent_transaction_amount >= 3 * prev)
    if not big:
        return []
    lines = []
    if s.recent_daily_transactions and s.recent_daily_transactions.transaction_summary_date == s.most_recent_transaction_date:
        lines = [d.model_dump() for d in s.recent_daily_transactions.product_share_class_details]
    top = max(lines, key=lambda d: d["transaction_amount"]) if lines else None
    return [Signal(
        id="SIG-TRADE-1", type="significant_trade",
        title=f"{s.recent_transaction_direction.title()} of ${s.most_recent_transaction_amount:,.0f}",
        date=s.most_recent_transaction_date,
        evidence_ids=[f"SALE:{ctx.advisor.advisor_id}"],
        product_id=ctx.product_id_for(top["product_share_class_id"]) if top else None,
        share_class_id=top["product_share_class_id"] if top else None,
        details={
            "amount": s.most_recent_transaction_amount,
            "direction": s.recent_transaction_direction,
            "previous_amount": s.previous_transaction_amount,
            "direction_changed": s.transaction_direction_changed,
            "lines": lines,
        },
        caveats=["A recent trade does not establish current holdings."],
    )]


@detector
def upcoming_birthday(ctx: AdvisorContext) -> list[Signal]:
    md = ctx.advisor.birthday_month_day
    if not md:
        return []
    month, day = (int(x) for x in md.split("-"))
    ref = ctx.reference_date
    try:
        nxt = date(ref.year, month, day)
        if nxt < ref:
            nxt = date(ref.year + 1, month, day)
    except ValueError:  # 02-29 in a non-leap year
        return []
    days = (nxt - ref).days
    if days > BIRTHDAY_WINDOW_DAYS:
        return []
    return [Signal(
        id="SIG-BDAY-1", type="birthday", title=f"Birthday in {days} days ({nxt:%d %b})",
        date=nxt, evidence_ids=[f"PROFILE:{ctx.advisor.advisor_id}"],
        details={"date": nxt.isoformat(), "days_until": days},
    )]


@detector
def new_material(ctx: AdvisorContext) -> list[Signal]:
    """Recently released, shareable material for a share class this advisor is linked to."""
    classes = {m.share_class_id for m in ctx.mentions if m.share_class_id}
    out = []
    for d in ctx.documents:
        if (d.product_share_class_id in classes and d.intended_audience == "external"
                and d.review_status == "approved" and _age(ctx, d.release_date) <= NEW_MATERIAL_DAYS):
            p = ctx.catalog.get(d.product_share_class_id)
            out.append(Signal(
                id=f"SIG-DOC-{d.content_id}", type="new_material",
                title=f"New {d.content_type.lower()}: {p.product_name if p else d.product_share_class_id}",
                date=d.release_date, evidence_ids=[d.content_id],
                product_id=p.product_id if p else None, share_class_id=d.product_share_class_id,
                details={"content_type": d.content_type},
            ))
    return out


def detect_all(ctx: AdvisorContext) -> list[Signal]:
    signals: list[Signal] = []
    for fn in DETECTORS:
        signals.extend(fn(ctx))
    return signals


def prefers_concise(ctx: AdvisorContext) -> list[str]:
    reasons = []
    if CONCISE_RX.search(ctx.advisor.relationship_comments or ""):
        reasons.append(f"Profile: \"{ctx.advisor.relationship_comments}\"")
    for a in ctx.activities:
        if CONCISE_RX.search(a.interaction_details or ""):
            reasons.append(f"{a.interaction_id}: \"{a.interaction_details}\"")
    return reasons
