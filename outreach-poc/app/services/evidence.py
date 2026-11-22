"""Step 5 - Evidence guard.

Builds the *fact pack* for one intent: the only statements a draft may make, each tied to
a source record, plus everything deliberately left out (with the reason). This is where
the "take account of what a source actually supports" rules from the brief live.
"""
from __future__ import annotations

from app.models import (
    DataLink, Document, Exclusion, Fact, FactPack, Intent, Signal, Tone,
)
from app.services import actions as admin
from app.services.context import AdvisorContext
from app.services.signals import prefers_concise

DISCLOSURE = ("Ratings and returns shown are illustrative and as of {date}. "
              "Past performance does not guarantee future results.")
GENERIC_SUBJECT_WORDS = {"invitation", "follow-up", "followup", "email", "update", "general", "market"}


def _money(x: float) -> str:
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def is_shareable(doc: Document) -> bool:
    return doc.intended_audience.lower() == "external" and doc.review_status.lower() == "approved"


def doc_exclusion_reason(doc: Document, share_class_id: str, ctx: AdvisorContext) -> str | None:
    """Why a document for the same fund cannot be attached (None = it can)."""
    if doc.product_share_class_id != share_class_id:
        mine = ctx.catalog.get(share_class_id)
        theirs = ctx.catalog.get(doc.product_share_class_id)
        return (f"Applies to share class {theirs.share_class_label if theirs else doc.product_share_class_id}, "
                f"but the advisor's interest is class {mine.share_class_label if mine else share_class_id}.")
    if doc.intended_audience.lower() != "external":
        return f"Marked for {doc.intended_audience} audience only - cannot be sent to an advisor."
    if doc.review_status.lower() != "approved":
        return f"Review status is '{doc.review_status}', not approved."
    return None


def eligible_documents(ctx: AdvisorContext, share_class_id: str | None) -> tuple[list[Document], list[Exclusion]]:
    if not share_class_id:
        return [], []
    product_id = ctx.product_id_for(share_class_id)
    ok, excluded = [], []
    for d in ctx.documents:
        if ctx.product_id_for(d.product_share_class_id) != product_id:
            continue  # unrelated fund
        reason = doc_exclusion_reason(d, share_class_id, ctx)
        if reason is None:
            ok.append(d)
        else:
            excluded.append(Exclusion(item=f"{d.content_id} {d.content_type} ({d.release_date:%d %b %Y})",
                                      reason=reason, source="06_documents"))
    ok.sort(key=lambda d: d.release_date, reverse=True)
    return ok, excluded


def _base_exclusions(ctx: AdvisorContext, intent: Intent) -> tuple[list[Exclusion], list[str]]:
    ex: list[Exclusion] = []
    banned: list[str] = []
    for a in ctx.activities:
        details = (a.interaction_details or "").lower()
        if a.communication_direction.lower() == "outbound" and ("no response" in details or a.meaningful_contact_flag == "N"):
            ex.append(Exclusion(
                item=f"{a.interaction_id} {a.interaction_subject} ({a.interaction_date:%d %b})",
                reason="Outbound with no recorded response - not evidence of advisor interest.",
                source="02_activities"))
            banned += [w for w in (a.interaction_subject or "").lower().split()
                       if len(w) > 4 and w not in GENERIC_SUBJECT_WORDS]

    if not ctx.holdings:
        ex.append(Exclusion(item="Holdings", reason="No holdings records - unknown, not zero. No holdings claims made.",
                            source="03_holdings"))
    for h in ctx.holdings:
        if (h.holding_value_change or 0) < 0:
            ex.append(Exclusion(
                item=f"{h.product_name} holding {_money(h.holding_value_change)} (as of {h.reference_date:%d %b})",
                reason="A value change alone does not establish a redemption - not mentioned.",
                source="03_holdings"))
            banned += ["redemption", "redeemed", "sold your", "reduced your"]
    if ctx.holdings:
        ex.append(Exclusion(item="Holding values",
                            reason="Internal context only; a trade or value change does not confirm what is held today.",
                            source="03_holdings"))
    if ctx.sale is None:
        ex.append(Exclusion(item="Recent sales", reason="No sales record - unknown, not zero.", source="04_recent_sales"))

    bday = ctx.advisor.birthday_month_day
    if bday and intent.type != "birthday_greeting":
        ex.append(Exclusion(item=f"Birthday ({bday})",
                            reason="Kept out of business emails; offered as a separate note when it is near.",
                            source="01_advisors"))
    return ex, sorted(set(banned))


def build_fact_pack(ctx: AdvisorContext, intent: Intent, signals: list[Signal],
                    included_override: set[str] | None = None, tone_override: str | None = None) -> FactPack:
    by_id = {s.id: s for s in signals}
    primary = by_id[intent.primary_signal_id]
    support = [by_id[i] for i in intent.supporting_signal_ids if i in by_id]
    a = ctx.advisor

    facts: list[Fact] = [
        Fact(id="F-ADVISOR", kind="profile", label="Advisor", source="01_advisors",
             evidence_id=f"PROFILE:{a.advisor_id}",
             statement=f"Advisor {a.display_name}, {a.role_title or 'Financial Advisor'} at {a.advisor_firm_name}.",
             values=[a.first_name, a.display_name, a.advisor_firm_name]),
    ]
    exclusions, banned = _base_exclusions(ctx, intent)
    gaps: list[str] = []
    links: list[DataLink] = []
    slots: list[str] | None = None

    def add_docs(share_class_id: str | None, wanted: list[str]):
        docs, doc_ex = eligible_documents(ctx, share_class_id)
        exclusions.extend(doc_ex)
        p = ctx.catalog.get(share_class_id or "")
        for d in docs:
            name = f"{p.product_name} Class {p.share_class_label}" if p else d.product_share_class_id
            facts.append(Fact(
                id=f"F-DOC-{d.content_id}", kind="document", label=f"{d.content_type} - {name}",
                statement=f"Approved external {d.content_type.lower()} for {name}, released {d.release_date:%d %b %Y}.",
                source="06_documents", evidence_id=d.content_id, as_of=d.release_date, url=d.content_url,
                values=[d.content_url, p.product_name if p else ""]))
            links.append(DataLink(content_id=d.content_id, label=f"{name} - {d.content_type}", url=d.content_url,
                                  content_type=d.content_type, share_class_id=d.product_share_class_id,
                                  release_date=d.release_date, audience=d.intended_audience,
                                  review_status=d.review_status))
        have = {d.content_type for d in docs}
        for ctype in wanted:
            if ctype not in have and p:
                gaps.append(f"No approved external {ctype.lower()} for {p.product_name} Class "
                            f"{p.share_class_label} ({p.product_share_class_id}).")
        if share_class_id and not docs and not wanted and p:
            gaps.append(f"No approved external material for {p.product_name} Class {p.share_class_label}.")
        return docs

    def add_performance(share_class_id: str | None, has_docs: bool):
        ref = ctx.fund_refs.get(share_class_id or "")
        if not ref:
            return
        p = ctx.catalog.get(share_class_id)
        label = f"{ref.product_name} Class {p.share_class_label}" if p else ref.product_name
        bits = []
        if ref.overall_rating is not None:
            bits.append(f"overall rating {ref.overall_rating} of 5")
        if ref.one_year_return_percent is not None:
            bits.append(f"one-year return {ref.one_year_return_percent}%")
        facts.append(Fact(
            id=f"F-PERF-{share_class_id}", kind="performance", label=f"Fund data - {label}",
            statement=f"As of {ref.reference_date:%d %b %Y}, {label}: {', '.join(bits)}.",
            source="05_fund_reference", evidence_id=share_class_id, as_of=ref.reference_date,
            included=False, optional=True,
            disclosure=DISCLOSURE.format(date=f"{ref.reference_date:%d %b %Y}"),
            warning=None if has_docs else "No approved external material for this share class - "
                                          "quoting performance needs compliance review.",
            values=[f"{ref.one_year_return_percent}%", str(ref.one_year_return_percent),
                    f"{ref.overall_rating}"]))

    def add_trade(sig: Signal, included: bool = True):
        lines = sig.details.get("lines") or []
        what = ", ".join(f"{l['product_name']} ({ctx.catalog[l['product_share_class_id']].share_class_label} class)"
                         if l['product_share_class_id'] in ctx.catalog else l['product_name'] for l in lines)
        facts.append(Fact(
            id="F-TRADE", kind="trade", label="Recent business",
            statement=f"{sig.details['direction'].title()} of {_money(sig.details['amount'])} on {sig.date:%d %b %Y}"
                      + (f" in {what}" if what else "") + ".",
            source="04_recent_sales", evidence_id=sig.evidence_ids[0], as_of=sig.date, included=included,
            optional=True, values=[_money(sig.details["amount"]), f"{sig.details['amount']:,.0f}"]
            + [l["product_name"] for l in lines]))

    # ---------------------------------------------------------------- intent-specific facts
    if intent.type == "fulfil_request":
        for r in primary.details["requests"]:
            facts.append(Fact(
                id=f"F-REQ-{r['id']}", kind="request", label=f"{r['channel']} {r['date']}",
                statement=f"{r['channel']} on {r['date']}: {r['text']}", source="02_activities",
                evidence_id=r["id"], values=[primary.details.get("product_name") or ""]
                + ([f"Class {primary.details['share_class_label']}"] if primary.details.get("share_class_label") else [])))
        docs = add_docs(primary.share_class_id, primary.details.get("requested_material") or [])
        for s in support:
            if s.type == "significant_trade":
                add_trade(s)
        add_performance(primary.share_class_id, bool(docs))
        if primary.share_class_id is None:
            gaps.append("Share class not identifiable from CRM notes - confirm which class the advisor meant.")

    elif intent.type == "thank_for_trade":
        add_trade(primary)
        docs = add_docs(primary.share_class_id, [])
        for f in facts:
            if f.kind == "document":
                f.optional = True
        add_performance(primary.share_class_id, bool(docs))
        facts.append(Fact(id="F-TRADE-CAVEAT", kind="caveat", label="Caveat", included=True,
                          statement="Do not state or imply what the advisor currently holds.",
                          source="rules"))

    elif intent.type == "firm_move_reconnect":
        acts = [x for x in ctx.activities if x.interaction_id in primary.evidence_ids]
        for x in acts:
            facts.append(Fact(id=f"F-MOVE-{x.interaction_id}", kind="relationship", label=f"{x.interaction_channel} {x.interaction_date}",
                              statement=f"{x.interaction_channel} on {x.interaction_date}: {x.interaction_details}",
                              source="02_activities", evidence_id=x.interaction_id,
                              values=[primary.details["new_firm"]]))
        if primary.details.get("reconnect_requested"):
            slots = admin.propose_slots(ctx.reference_date, primary.details.get("timeframe"))
            facts.append(Fact(id="F-SLOTS", kind="scheduling", label="Proposed times",
                              statement="Proposed reconnect times (tentative): " + "; ".join(slots) + ".",
                              source="admin:scheduling", values=slots))
        gaps.append(f"{a.display_name} recently changed firms - confirm {a.email_id} is still current before sending.")

    elif intent.type == "birthday_greeting":
        facts.append(Fact(id="F-BDAY", kind="relationship", label="Birthday",
                          statement=f"Birthday on {primary.date:%d %B}.", source="01_advisors",
                          evidence_id=f"PROFILE:{a.advisor_id}", values=[]))

    # ---------------------------------------------------------------- user overrides
    if included_override is not None:
        for f in facts:
            if f.optional or f.kind in ("document",):
                f.included = f.id in included_override

    # ---------------------------------------------------------------- tone
    concise = prefers_concise(ctx)
    style = tone_override or ("concise" if concise else "warm")
    tone = Tone(style=style, max_words={"concise": 120, "warm": 170, "formal": 170}[style], reasons=concise)

    actions = admin.suggest_actions(ctx, intent, primary, gaps, slots)
    return FactPack(intent=intent, facts=facts, exclusions=exclusions, gaps=gaps, links=links, actions=actions,
                    tone=tone, banned_terms=banned, sender_name=ctx.user.display_name,
                    advisor_first_name=a.first_name)
