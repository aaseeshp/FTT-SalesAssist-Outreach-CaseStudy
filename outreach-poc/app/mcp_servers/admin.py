"""salesassist-admin MCP server - administrative support helpers.

Agents get read-only helpers. Executing actions (logging, holds, requests) goes through the
SalesAssist API only after the sales user confirms in the UI.
"""
from datetime import date

from mcp.server.fastmcp import FastMCP

from app.mcp_servers._common import dumps, source
from app.services.actions import propose_slots

mcp = FastMCP("salesassist-admin")


@mcp.tool()
def propose_meeting_slots(timeframe: str = "later this month") -> str:
    """Three tentative weekday slots for a meeting in a timeframe such as 'later this month', 'next week',
    'next month'. (Mock calendar - no free/busy lookup.)"""
    return dumps({"slots": propose_slots(source().reference_date(), timeframe.lower())})


@mcp.tool()
def list_admin_capabilities() -> str:
    """Administrative actions SalesAssist can run after user confirmation."""
    return dumps({
        "log_activity": "Create a CRM activity for the outreach (and close promised follow-ups).",
        "schedule_meeting": "Place tentative calendar holds and draft an invite.",
        "request_material": "Open a request to marketing for approved external material.",
        "set_reminder": "Create a follow-up reminder for the sales user.",
        "verify_contact": "Open a CRM data-quality task to confirm advisor contact details.",
    })


if __name__ == "__main__":
    mcp.run()
