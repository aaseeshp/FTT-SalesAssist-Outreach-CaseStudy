"""salesassist-crm MCP server - advisor profile, CRM activity and outreach signals."""
from mcp.server.fastmcp import FastMCP

from app.mcp_servers._common import dumps, guarded, scoped_context
from app.services.signals import detect_all

mcp = FastMCP("salesassist-crm")


@mcp.tool()
@guarded
def get_advisor_profile(advisor_id: str) -> str:
    """Advisor identity, current firm, relationship comments and birthday (MM-DD). Evidence id: PROFILE:<advisor_id>."""
    ctx = scoped_context(advisor_id)
    a = ctx.advisor
    return dumps({"evidence_id": f"PROFILE:{a.advisor_id}", "reference_date": ctx.reference_date,
                  **a.model_dump(exclude={"email_id"})})


@mcp.tool()
@guarded
def get_crm_activities(advisor_id: str, days: int = 60) -> str:
    """CRM meetings, calls and emails for the advisor in the last `days` days, newest first.
    Includes product share-class resolution for each activity. Evidence id: INTERACTION_ID."""
    ctx = scoped_context(advisor_id)
    rows = []
    for a in ctx.activities:
        if (ctx.reference_date - a.interaction_date).days <= days:
            rows.append({**a.model_dump(), "resolved_products": [m.model_dump() for m in ctx.mention_for_activity(a.interaction_id)]})
    return dumps({"reference_date": ctx.reference_date, "activities": rows,
                  "note": "Outbound messages without a response are not evidence of interest."})


@mcp.tool()
@guarded
def get_outreach_signals(advisor_id: str) -> str:
    """Rule-based signals from SalesAssist proactive prioritisation (open requests, firm moves, significant
    trades, upcoming birthdays, new approved material), each with evidence ids and caveats."""
    ctx = scoped_context(advisor_id)
    return dumps([s.model_dump() for s in detect_all(ctx)])


if __name__ == "__main__":
    mcp.run()
