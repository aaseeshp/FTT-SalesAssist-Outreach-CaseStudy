"""Administrative support - suggested actions and a mock executor.

Suggestions are computed with the fact pack. Nothing runs until the user selects actions
and confirms them in the UI; the API refuses unconfirmed requests.
"""
from __future__ import annotations

import itertools
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from app.models import AdminAction, Intent, Signal
from app.services.context import AdvisorContext

_counter = itertools.count(1)
ACTION_LOG: list[dict] = []


def propose_slots(ref: date, timeframe: str | None) -> list[str]:
    """Three weekday slots in the requested window (mock calendar - no free/busy lookup)."""
    if timeframe in ("later this month", "this month"):
        start, end = ref + timedelta(days=5), date(ref.year, ref.month, monthrange(ref.year, ref.month)[1])
    elif timeframe in ("next month", "early next month"):
        first = (date(ref.year, ref.month, 28) + timedelta(days=4)).replace(day=1)
        start, end = first, first + timedelta(days=13)
    else:
        start, end = ref + timedelta(days=3), ref + timedelta(days=17)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    weekdays = [d for d in days if d.weekday() < 5] or days
    picks = [weekdays[min(i, len(weekdays) - 1)] for i in (1, 3, 6)]
    times = ["10:00", "14:00", "11:00"]
    return [f"{d:%a %d %b} at {t}" for d, t in zip(dict.fromkeys(picks), times)]


def suggest_actions(ctx: AdvisorContext, intent: Intent, primary: Signal, gaps: list[str],
                    slots: list[str] | None = None) -> list[AdminAction]:
    a = ctx.advisor
    acts: list[AdminAction] = []
    log = AdminAction(
        id="ACT-LOG", type="log_activity", label="Log this email in CRM",
        description=f"Create an outbound email activity for {a.display_name} once you send it.",
        payload={"advisor_id": a.advisor_id, "channel": "Email", "direction": "Outbound",
                 "subject": intent.label, "related": primary.evidence_ids})

    if intent.type == "fulfil_request":
        if primary.details.get("promised"):
            log.label = "Log email and close the promised follow-up"
            log.description += f" Marks {', '.join(primary.evidence_ids)} as fulfilled."
        acts.append(log)
        for i, gap in enumerate(gaps, start=1):
            if "No approved external" in gap:
                acts.append(AdminAction(
                    id=f"ACT-MAT-{i}", type="request_material", label="Request approved material from marketing",
                    description=gap.replace("No approved external", "Ask marketing for an approved external"),
                    payload={"share_class_id": primary.share_class_id,
                             "content_types": primary.details.get("requested_material") or ["Factsheet"],
                             "for_advisor": a.advisor_id}))
        acts.append(AdminAction(
            id="ACT-REM", type="set_reminder", label="Remind me to check in next week",
            description=f"Follow up with {a.first_name} in 7 days to see if they need anything else.",
            payload={"due": (ctx.reference_date + timedelta(days=7)).isoformat(), "advisor_id": a.advisor_id},
            recommended=not gaps))
        if gaps:
            acts.append(AdminAction(
                id="ACT-REM-MAT", type="set_reminder", label="Remind me when the material is ready",
                description="Reminder in 3 business days to send the approved material once marketing provides it.",
                payload={"due": (ctx.reference_date + timedelta(days=5)).isoformat(), "advisor_id": a.advisor_id}))

    elif intent.type == "firm_move_reconnect":
        acts.append(AdminAction(
            id="ACT-MEET", type="schedule_meeting", label="Hold 3 meeting slots and draft an invite",
            description=f"Tentatively hold the proposed times for a reconnect with {a.first_name}.",
            payload={"advisor_id": a.advisor_id, "slots": slots or [], "duration_minutes": 30,
                     "timeframe": primary.details.get("timeframe")}))
        acts.append(AdminAction(
            id="ACT-VERIFY", type="verify_contact", label="Confirm email address at the new firm",
            description=f"{a.email_id} may belong to the previous firm. Open a CRM data-quality task.",
            payload={"advisor_id": a.advisor_id, "current_email": a.email_id, "firm": a.advisor_firm_name}))
        acts.append(log)

    elif intent.type == "thank_for_trade":
        acts.append(log)
        acts.append(AdminAction(
            id="ACT-REM", type="set_reminder", label="Remind me to check in in two weeks",
            description="Service check-in after the purchase.",
            payload={"due": (ctx.reference_date + timedelta(days=14)).isoformat(), "advisor_id": a.advisor_id},
            recommended=False))
    else:
        acts.append(log)
    return acts


def execute(user_id: str, advisor_id: str, actions: list[AdminAction]) -> list[dict]:
    """Mock execution: each type would call the matching SalesAssist admin agent / MCP tool."""
    results = []
    for act in actions:
        ref = f"{act.type.upper().replace('_', '-')}-{next(_counter):04d}"
        message = {
            "log_activity": f"CRM activity {ref} created (pending send).",
            "schedule_meeting": f"{len(act.payload.get('slots', []))} tentative holds placed; invite draft {ref} ready.",
            "request_material": f"Marketing request {ref} opened for {act.payload.get('share_class_id')}.",
            "set_reminder": f"Reminder {ref} set for {act.payload.get('due')}.",
            "verify_contact": f"Data-quality task {ref} opened to confirm the email address.",
        }[act.type]
        entry = {"ref": ref, "action_id": act.id, "type": act.type, "label": act.label, "status": "done",
                 "message": message, "user_id": user_id, "advisor_id": advisor_id,
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        ACTION_LOG.append(entry)
        results.append(entry)
    return results
