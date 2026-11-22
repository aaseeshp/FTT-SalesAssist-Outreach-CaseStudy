"""Step 2 - Context assembly.

Pulls every source for one advisor (in parallel - each call stands in for a separate
service) and resolves product references to share classes through the product catalog.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date

from app.data.sources import DataSource
from app.models import (
    Activity, Advisor, Document, FundReference, Holding, Product, ProductMention, Sale, User,
)

CLASS_RX = re.compile(r"\bclass\s+([A-Z0-9]{1,3})\b", re.IGNORECASE)


@dataclass
class AdvisorContext:
    user: User
    advisor: Advisor
    reference_date: date
    activities: list[Activity]
    holdings: list[Holding]
    sale: Sale | None
    catalog: dict[str, Product]                 # by share class id
    fund_refs: dict[str, FundReference]         # by share class id
    documents: list[Document]
    mentions: list[ProductMention] = field(default_factory=list)

    # ---- helpers used by later stages
    def products_by_name(self, name: str) -> list[Product]:
        key = name.strip().lower()
        return [p for p in self.catalog.values() if p.product_name.lower() == key]

    def product_id_for(self, share_class_id: str | None) -> str | None:
        p = self.catalog.get(share_class_id or "")
        return p.product_id if p else None

    def mention_for_activity(self, interaction_id: str) -> list[ProductMention]:
        return [m for m in self.mentions if m.source == "activity" and m.evidence_id == interaction_id]


def assemble(source: DataSource, user: User, advisor: Advisor) -> AdvisorContext:
    aid = advisor.advisor_id
    with ThreadPoolExecutor(max_workers=6) as pool:
        f_act = pool.submit(source.activities, aid)
        f_hold = pool.submit(source.holdings, aid)
        f_sale = pool.submit(source.sale, aid)
        f_cat = pool.submit(source.catalog)
        f_ref = pool.submit(source.fund_references)
        f_docs = pool.submit(source.documents)
        activities = [a for a in f_act.result()
                      # activities are region-tagged too; keep only those in the user's region
                      if a.region_identifier in (None, user.region_identifier)]
        ctx = AdvisorContext(
            user=user,
            advisor=advisor,
            reference_date=source.reference_date(),
            activities=activities,
            holdings=f_hold.result(),
            sale=f_sale.result(),
            catalog={p.product_share_class_id: p for p in f_cat.result()},
            # Join on PRODUCT_SHARE_CLASS_ID; REFERENCE_PRODUCT_ID is deliberately not used.
            fund_refs={r.product_share_class_id: r for r in f_ref.result()},
            documents=f_docs.result(),
        )
    ctx.mentions = resolve_mentions(ctx)
    return ctx


def resolve_mentions(ctx: AdvisorContext) -> list[ProductMention]:
    """Link holdings, sales and CRM activities to catalog share classes.

    Holdings and sales carry PRODUCT_SHARE_CLASS_ID (exact). CRM activities carry only fund
    names, so the class is resolved in this order:
      1. fund has a single share class in the catalog        -> single_class
      2. the free text names a class ("Class I")             -> text_match
      3. an earlier activity in the same thread resolved it  -> thread
      4. otherwise                                           -> unresolved (never guessed)
    """
    mentions: list[ProductMention] = []

    for h in ctx.holdings:
        p = ctx.catalog.get(h.product_share_class_id)
        mentions.append(ProductMention(
            product_name=h.product_name, product_id=p.product_id if p else None,
            share_class_id=h.product_share_class_id, share_class_label=p.share_class_label if p else None,
            source="holding", evidence_id=f"HOLD:{h.product_share_class_id}", resolution="exact"))

    if ctx.sale and ctx.sale.recent_daily_transactions:
        for d in ctx.sale.recent_daily_transactions.product_share_class_details:
            p = ctx.catalog.get(d.product_share_class_id)
            mentions.append(ProductMention(
                product_name=d.product_name, product_id=p.product_id if p else None,
                share_class_id=d.product_share_class_id, share_class_label=p.share_class_label if p else None,
                source="sale", evidence_id=f"SALE:{ctx.advisor.advisor_id}", resolution="exact"))

    thread: dict[str, Product] = {}  # product_id -> class resolved earlier in the conversation
    for act in sorted(ctx.activities, key=lambda a: a.interaction_date):
        for name in act.product_names:
            classes = ctx.products_by_name(name)
            chosen: Product | None = None
            resolution = "unresolved"
            if len(classes) == 1:
                chosen, resolution = classes[0], "single_class"
            elif classes:
                labels = {m.group(1).upper() for m in CLASS_RX.finditer(act.interaction_details or "")}
                hits = [p for p in classes if p.share_class_label.upper() in labels]
                if len(hits) == 1:
                    chosen, resolution = hits[0], "text_match"
                elif classes[0].product_id in thread:
                    chosen, resolution = thread[classes[0].product_id], "thread"
            if chosen:
                thread[chosen.product_id] = chosen
            mentions.append(ProductMention(
                product_name=name,
                product_id=chosen.product_id if chosen else (classes[0].product_id if classes else None),
                share_class_id=chosen.product_share_class_id if chosen else None,
                share_class_label=chosen.share_class_label if chosen else None,
                source="activity", evidence_id=act.interaction_id, resolution=resolution))
    return mentions
