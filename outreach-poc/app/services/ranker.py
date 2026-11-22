"""Step 4 - Intent ranking.

Turns signals into outreach intents (reasons to write) with an explainable score:
    score = base weight of the signal type x recency factor (+ small bonuses)
Commitments the firm made outrank timely trades, which outrank relationship touches.
"""
from __future__ import annotations

from app.models import Intent, Signal
from app.services.context import AdvisorContext

INTENT_FOR_SIGNAL = {
    # signal type        intent type              label                                   base
    "open_request":      ("fulfil_request",       "Send requested information",           0.90),
    "firm_move":         ("firm_move_reconnect",  "Congratulate on new firm & reconnect", 0.80),
    "significant_trade": ("thank_for_trade",      "Thank for recent business",            0.75),
    "birthday":          ("birthday_greeting",    "Birthday note",                        0.35),
}
SUPPORT_ONLY = {"new_material"}  # never a reason on its own in v1; enriches other intents
MAX_OPTIONS = 3


def _recency(ctx: AdvisorContext, s: Signal) -> float:
    if s.type == "birthday" or s.date is None:
        return 1.0
    age = max(0, (ctx.reference_date - s.date).days)
    return max(0.4, 1 - age / 45)


def rank(ctx: AdvisorContext, signals: list[Signal]) -> list[Intent]:
    intents: list[Intent] = []
    for s in signals:
        if s.type in SUPPORT_ONLY or s.type not in INTENT_FOR_SIGNAL:
            continue
        itype, label, base = INTENT_FOR_SIGNAL[s.type]
        score = base * _recency(ctx, s)
        why = [f"{s.title} ({s.date:%d %b})" if s.date and s.type != "birthday" else s.title]
        if s.details.get("promised"):
            score += 0.05
            why.append("we promised a follow-up")
        if s.details.get("reconnect_requested"):
            score += 0.05
            why.append("advisor asked to reconnect")

        # Attach supporting signals that make the email more useful.
        support = []
        for o in signals:
            if o.id == s.id:
                continue
            same_product = s.product_id and o.product_id == s.product_id
            if o.type == "significant_trade" and s.type == "open_request" and same_product:
                support.append(o.id)
                why.append(f"recent {o.details['direction']} in the same fund")
            elif o.type == "new_material" and s.share_class_id and o.share_class_id == s.share_class_id:
                support.append(o.id)
        if s.type == "open_request" and s.details.get("product_name"):
            label = f"{label}: {s.details['product_name']}"

        intents.append(Intent(
            id=f"INT-{s.id.removeprefix('SIG-')}", type=itype, label=label,
            score=round(min(score, 1.0), 2), rationale="; ".join(why),
            primary_signal_id=s.id, supporting_signal_ids=support,
        ))
    intents.sort(key=lambda i: i.score, reverse=True)
    return intents[:MAX_OPTIONS]
