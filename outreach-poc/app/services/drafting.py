"""Step 6 - Drafting.

Two interchangeable drafters behind one interface:
* TemplateDrafter - deterministic; works offline; also the fallback when the model fails.
* GeminiDrafter   - single structured-output call to Gemini (used for fast regenerate).
The multi-agent crew (app/agents) uses its own drafting agent and falls back to these.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Protocol

from pydantic import BaseModel, Field

from app.models import Draft, FactPack
from app.agents.prompts import drafter_system, drafter_user_prompt
from app.services.model_chain import call_with_chain

log = logging.getLogger(__name__)


class Drafter(Protocol):
    name: str

    def draft(self, pack: FactPack, instructions: str | None = None) -> Draft: ...


def _d(iso: str) -> str:
    return f"{date.fromisoformat(iso):%-d %B}"


class TemplateDrafter:
    name = "template"

    def draft(self, pack: FactPack, instructions: str | None = None) -> Draft:
        f = {x.id: x for x in pack.included_facts()}
        docs = [x for x in pack.included_facts() if x.kind == "document"]
        perf = [x for x in pack.included_facts() if x.kind == "performance"]
        trade = f.get("F-TRADE")
        concise = pack.tone.style == "concise"
        formal = pack.tone.style == "formal"
        hi = f"Dear {pack.advisor_first_name}," if formal else f"Hi {pack.advisor_first_name},"
        lines: list[str] = []
        t = pack.intent.type

        if t == "fulfil_request":
            reqs = [x for x in pack.included_facts() if x.kind == "request"]
            last = reqs[-1] if reqs else None
            product = reqs[0].values[0] if reqs and reqs[0].values else "the fund"
            cls = reqs[0].values[1] if reqs and len(reqs[0].values) > 1 else ""
            name = f"{product} {cls}".strip()
            when = _d(last.label.split()[-1]) if last else "our recent conversation"
            subject = f"{name}: the information you requested"
            if docs:
                lines.append(f"Thank you for your time on {when}. As promised, here is the approved information on {name}:")
                lines.append("")
                lines += [f"- {d.label.split(' - ')[0]}: {d.url}" for d in docs]
            else:
                lines.append(f"Thank you for your time on {when} and for asking about {name}.")
                lines.append("I'm arranging the latest approved material and will send it to you as soon as it is available.")
            if trade:
                lines += ["", f"Thank you also for your recent {trade.values[0]} investment in the fund."]
            for p in perf:
                lines += ["", p.statement, p.disclosure or ""]
            lines += ["", "Happy to walk through any of it whenever suits you." if not concise else "Happy to discuss if useful."]

        elif t == "thank_for_trade":
            subject = "Thank you for your recent business"
            lines.append(f"Thank you for your recent {trade.values[0]} investment"
                         + (f" in {trade.values[2]}." if trade and len(trade.values) > 2 else ".") if trade
                         else "Thank you for your recent business with us.")
            if docs:
                lines += ["", "In case it is useful for your clients, here is the latest approved material:"]
                lines += [f"- {d.label.split(' - ')[0]}: {d.url}" for d in docs]
            for p in perf:
                lines += ["", p.statement, p.disclosure or ""]
            lines += ["", "If there is anything I can help with, from portfolio support to client materials, just let me know."]

        elif t == "firm_move_reconnect":
            firm = next((x.values[0] for x in pack.included_facts() if x.kind == "relationship" and x.values), "your new firm")
            subject = f"Congratulations on joining {firm}"
            lines.append(f"Congratulations on joining {firm}. I hope the transition is going smoothly.")
            slots = f.get("F-SLOTS")
            if slots:
                lines += ["", "You mentioned reconnecting later this month. Would any of these times work for a quick catch-up?"]
                lines += [f"- {s}" for s in slots.values]
            else:
                lines += ["", "I'd welcome the chance to reconnect once you are settled."]
            lines += ["", "In the meantime, let me know if there is anything I can do to help as you get set up."]

        elif t == "birthday_greeting":
            subject = f"Happy birthday, {pack.advisor_first_name}"
            lines.append("Wishing you a very happy birthday and a great year ahead.")
        else:
            subject = pack.intent.label
            lines.append("I wanted to reach out and see how things are going.")

        sign = ["", "Kind regards," if formal else "Best regards,", pack.sender_name]
        body = "\n".join([hi, ""] + [l for l in lines if l is not None] + sign)
        return Draft(subject=subject, body=body, cited_fact_ids=list(f.keys()), generator="template")


class _DraftOut(BaseModel):
    subject: str
    body: str
    cited_fact_ids: list[str] = Field(default_factory=list)


class GeminiDrafter:
    name = "gemini"

    def __init__(self, api_key: str, models: list[str], timeout_ms: int = 45000):
        from google import genai  # imported lazily so template mode needs no SDK init
        from google.genai import types
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))
        self.models = models
        self.model = models[0]

    def draft(self, pack: FactPack, instructions: str | None = None) -> Draft:
        from google.genai import types

        def call(model: str):
            return self._client.models.generate_content(
                model=model,
                contents=drafter_user_prompt(pack, instructions),
                config=types.GenerateContentConfig(
                    system_instruction=drafter_system(pack),
                    response_mime_type="application/json",
                    response_schema=_DraftOut,
                    temperature=0.4,
                ),
            )
        resp, used = call_with_chain(self.models, call)
        out = resp.parsed if isinstance(resp.parsed, _DraftOut) else _DraftOut.model_validate(json.loads(resp.text))
        note = None if used == self.models[0] else f"{self.models[0]} was busy; drafted with {used}."
        return Draft(subject=out.subject, body=out.body, cited_fact_ids=out.cited_fact_ids,
                     generator="gemini", model=used, note=note)


class FallbackDrafter:
    """Try the model; on any error fall back to the template so the panel always opens."""

    def __init__(self, primary: Drafter | None, fallback: Drafter):
        self.primary, self.fallback = primary, fallback
        self.name = primary.name if primary else fallback.name

    def draft(self, pack: FactPack, instructions: str | None = None) -> Draft:
        if self.primary:
            try:
                return self.primary.draft(pack, instructions)
            except Exception as exc:  # noqa: BLE001 - any model failure degrades gracefully
                log.warning("Model drafter failed, using template: %s", exc)
                d = self.fallback.draft(pack, instructions)
                d.note = f"Model unavailable ({type(exc).__name__}); template used."
                return d
        return self.fallback.draft(pack, instructions)
