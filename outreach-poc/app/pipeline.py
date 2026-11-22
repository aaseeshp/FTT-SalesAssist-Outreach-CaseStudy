"""Outreach pipeline - what happens after the user clicks the email icon.

    1 access  -> 2 assemble -> 3 signals -> 4 intents -> 5 fact packs -> 6 compose -> 7 verify

Rules decide what is true and allowed (steps 1-3, 5, 7). Agents (or the template drafter)
decide wording and priorities (steps 4, 6). Results are cached per (user, advisor, data
version) and pre-computed at start-up so the panel opens instantly.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.agents.prompts import PROMPT_VERSION
from app.data.sources import DataSource
from app.models import (
    AdvisorSnapshot, Draft, FactPack, Intent, OutreachOption, OutreachResponse, Signal, TraceStep,
)
from app.services import entitlement, ranker, signals as sig
from app.services.context import AdvisorContext, assemble
from app.services.drafting import Drafter, TemplateDrafter
from app.services.evidence import build_fact_pack
from app.services.verifier import verify

log = logging.getLogger(__name__)


class _Timer:
    def __init__(self, trace: list[TraceStep]):
        self.trace = trace

    def step(self, key: str, label: str, actor: str = "rules"):
        timer = self

        class _Ctx:
            detail = ""

            def __enter__(self):
                self.t0 = time.perf_counter()
                return self

            def __exit__(self, *exc):
                timer.trace.append(TraceStep(key=key, label=label, actor=actor, detail=self.detail,
                                             ms=round((time.perf_counter() - self.t0) * 1000, 1)))
        return _Ctx()


def snapshot(ctx: AdvisorContext) -> AdvisorSnapshot:
    a = ctx.advisor
    last = next((x for x in ctx.activities if x.communication_direction.lower() != "outbound"), None) \
        or (ctx.activities[0] if ctx.activities else None)
    return AdvisorSnapshot(
        advisor_id=a.advisor_id, name=a.display_name, email=a.email_id, firm=a.advisor_firm_name,
        region=a.region_identifier, relationship_comments=a.relationship_comments,
        holdings=[h.model_dump(mode="json") for h in ctx.holdings],
        recent_sale=ctx.sale.model_dump(mode="json") if ctx.sale else None,
        last_contact={"id": last.interaction_id, "date": last.interaction_date.isoformat(),
                      "channel": last.interaction_channel, "subject": last.interaction_subject} if last else None,
    )


def reconcile(agent_result, rule_intents: list[Intent], signals: list[Signal]) -> tuple[list[Intent], list[dict]]:
    """Guardrail: accept an agent intent only if a rule-detected signal of the same type backs it
    with overlapping evidence. Agent order wins; rule intents the agent missed are appended."""
    by_sig = {s.id: s for s in signals}
    accepted: list[Intent] = []
    rejected: list[dict] = []
    for ai in agent_result.intents:
        match = None
        for ri in rule_intents:
            s = by_sig[ri.primary_signal_id]
            if ri.type == ai.intent_type and (set(ai.evidence_ids) & set(s.evidence_ids) or not ai.evidence_ids):
                match = ri
                break
        if match and match not in accepted:
            accepted.append(match.model_copy(update={
                "score": round(ai.confidence, 2),
                "rationale": f"{ai.rationale} [rules: {match.rationale}]"}))
        else:
            rejected.append({"intent_type": ai.intent_type, "evidence_ids": ai.evidence_ids,
                             "reason": "No rule-detected signal supports this intent (or v1 does not draft it)."})
    for ri in rule_intents:
        if all(ri.id != a.id for a in accepted):
            accepted.append(ri.model_copy(update={"rationale": f"{ri.rationale} [added by rules - agent did not rank it]"}))
    return accepted[: ranker.MAX_OPTIONS], rejected


class OutreachPipeline:
    def __init__(self, source: DataSource, drafter: Drafter, crew=None):
        self.source = source
        self.drafter = drafter
        self.template = TemplateDrafter()
        self.crew = crew
        self._cache: dict[tuple, OutreachResponse] = {}
        self._locks: dict[tuple, threading.Lock] = {}
        self._guard = threading.Lock()

    @property
    def mode(self) -> str:
        if self.crew:
            return f"crew · {self.crew.provider} · {self.crew.model}"
        return f"{self.drafter.name}" + (f" · {getattr(self.drafter.primary, 'model', '')}"
                                          if getattr(self.drafter, "primary", None) else "")

    # ---------------------------------------------------------------- public API
    def get(self, user_id: str, advisor_id: str) -> OutreachResponse:
        """Entitlement is checked on every call - including cache hits."""
        entitlement.authorize(self.source, user_id, advisor_id)
        key = (user_id, advisor_id, self.source.version)
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:  # if warm-up is computing this key, wait for it instead of duplicating the work
            if key in self._cache:
                return self._cache[key].model_copy(update={"cache": "hit"})
            resp = self.run(user_id, advisor_id)
            self._cache[key] = resp
            return resp

    def warm(self) -> None:
        for u in self.source.users():
            for a in self.source.advisors():
                if a.region_identifier == u.region_identifier:
                    try:
                        self.get(u.user_id, a.advisor_id)
                    except Exception:  # noqa: BLE001
                        log.exception("Warm-up failed for %s/%s", u.user_id, a.advisor_id)

    def quick_signals(self, user_id: str, advisor_id: str) -> list[Signal]:
        user, advisor = entitlement.authorize(self.source, user_id, advisor_id)
        return sig.detect_all(assemble(self.source, user, advisor))

    # ---------------------------------------------------------------- full run
    def run(self, user_id: str, advisor_id: str) -> OutreachResponse:
        trace: list[TraceStep] = []
        t = _Timer(trace)

        with t.step("access", "Checked region access") as s:
            user, advisor = entitlement.authorize(self.source, user_id, advisor_id)
            s.detail = f"{user.display_name} ({user.region_identifier}) → {advisor.display_name} ({advisor.region_identifier})"
        with t.step("assemble", "Pulled CRM, sales, holdings, fund data and documents") as s:
            ctx = assemble(self.source, user, advisor)
            s.detail = (f"{len(ctx.activities)} activities · {len(ctx.holdings)} holdings · "
                        f"{'1 sale' if ctx.sale else 'no sales record'} · {len(ctx.mentions)} product links")
        with t.step("signals", "Detected outreach signals") as s:
            signals = sig.detect_all(ctx)
            s.detail = ", ".join(x.type for x in signals) or "none"
        rule_intents = ranker.rank(ctx, signals)

        rejected: list[dict] = []
        intents = rule_intents
        if self.crew:
            with t.step("intents", "Classified intent (Intent Analyst agent via MCP)", actor="agent") as s:
                try:
                    result = self.crew.classify(user_id, advisor_id, ctx.reference_date.isoformat())
                    intents, rejected = reconcile(result, rule_intents, signals)
                    s.detail = (f"agent proposed {len(result.intents)}, accepted "
                                f"{len(intents) - sum('added by rules' in i.rationale for i in intents)}, "
                                f"rejected {len(rejected)} · prompt {PROMPT_VERSION}")
                except Exception as exc:  # noqa: BLE001
                    log.exception("Intent crew failed")
                    s.detail = f"agent failed ({type(exc).__name__}); rule ranking used"
        else:
            trace.append(TraceStep(key="intents", label="Ranked intents (rules)", ms=0.0,
                                   detail=", ".join(f"{i.type} {i.score}" for i in intents) or "none"))

        with t.step("evidence", "Applied evidence rules and built fact packs") as s:
            packs = [build_fact_pack(ctx, i, signals) for i in intents]
            s.detail = (f"{sum(len(p.included_facts()) for p in packs)} facts allowed · "
                        f"{len({e.item for p in packs for e in p.exclusions})} items excluded · "
                        f"{sum(len(p.gaps) for p in packs)} gaps")

        actor = "agent" if self.crew else ("model" if self.drafter.name == "gemini" else "rules")
        label = ("Drafted in parallel (Writer + Admin Ops + Compliance agents)" if self.crew
                 else f"Drafted emails ({self.drafter.name})")
        with t.step("draft", label, actor=actor) as s:
            with ThreadPoolExecutor(max_workers=max(1, len(packs))) as pool:
                options = list(pool.map(lambda p: self._compose(user_id, advisor_id, p, ctx), packs))
            s.detail = " · ".join(f"{o.pack.intent.type}: {o.draft.generator}" for o in options) or "nothing to draft"
        trace.append(TraceStep(
            key="verify", label="Verified every claim against source data", ms=0.0,
            detail=" · ".join(f"{o.pack.intent.type}: {'pass' if o.verification.passed else 'FAIL'} "
                              f"({o.verification.checked} checks)" for o in options)))

        return OutreachResponse(
            user=user, advisor=snapshot(ctx), reference_date=ctx.reference_date,
            generated_at=datetime.now(timezone.utc), signals=signals, options=options, trace=trace,
            orchestrator=self.mode, rejected_intents=rejected)

    # ---------------------------------------------------------------- compose + verify one intent
    def _catalog_names(self, ctx: AdvisorContext) -> list[str]:
        return sorted({p.product_name for p in ctx.catalog.values()})

    def _compose(self, user_id: str, advisor_id: str, pack: FactPack, ctx: AdvisorContext,
                 instructions: str | None = None, use_crew: bool = True) -> OutreachOption:
        draft: Draft
        if self.crew and use_crew:
            try:
                res = self.crew.compose(user_id, advisor_id, pack, instructions)
                final = res.review if (res.review and res.review.body.strip()) else res.draft
                draft = Draft(subject=final.subject, body=final.body, cited_fact_ids=final.cited_fact_ids,
                              generator="crew", model=self.crew.model,
                              reviewed_by="Compliance Reviewer agent" if res.review else None,
                              review_issues=res.review.issues if res.review else [])
                if res.admin:
                    valid = {a.id for a in pack.actions}
                    picks = [i for i in res.admin.recommended_action_ids if i in valid]
                    if picks:
                        for a in pack.actions:
                            a.recommended = a.id in picks
                            a.agent_note = res.admin.reasons.get(a.id)
            except Exception as exc:  # noqa: BLE001
                log.exception("Compose crew failed")
                draft = self.drafter.draft(pack, instructions)  # single model call, then template
                draft.note = f"Agents unavailable ({type(exc).__name__}); " + (draft.note or f"drafted by {draft.generator}.")
        else:
            draft = self.drafter.draft(pack, instructions)

        check = verify(draft, pack, self._catalog_names(ctx))
        if not check.passed and draft.generator != "template":
            # Deterministic safety net: never show a model draft that fails the claim check.
            fallback = self.template.draft(pack)
            fb_check = verify(fallback, pack, self._catalog_names(ctx))
            fallback.note = ("Model draft failed the claim check (" + "; ".join(check.issues[:3]) +
                             "). Showing the rule-based draft instead.")
            return OutreachOption(pack=pack, draft=fallback, verification=fb_check)
        return OutreachOption(pack=pack, draft=draft, verification=check)

    def regenerate(self, user_id: str, advisor_id: str, intent_id: str, included: set[str] | None,
                   tone: str | None, instructions: str | None) -> OutreachOption:
        """Fast path for user edits: one direct model call (not the full crew) + verification."""
        base = self.get(user_id, advisor_id)
        user, advisor = entitlement.authorize(self.source, user_id, advisor_id)
        ctx = assemble(self.source, user, advisor)
        signals = sig.detect_all(ctx)
        intent = next((o.pack.intent for o in base.options if o.pack.intent.id == intent_id), None)
        if intent is None:
            raise entitlement.NotFound(f"Unknown intent {intent_id}")
        pack = build_fact_pack(ctx, intent, signals, included_override=included, tone_override=tone)
        prev = next(o.pack for o in base.options if o.pack.intent.id == intent_id)
        for a in pack.actions:  # keep agent recommendations from the original run
            old = next((x for x in prev.actions if x.id == a.id), None)
            if old:
                a.recommended, a.agent_note = old.recommended, old.agent_note
        return self._compose(user_id, advisor_id, pack, ctx, instructions, use_crew=False)
