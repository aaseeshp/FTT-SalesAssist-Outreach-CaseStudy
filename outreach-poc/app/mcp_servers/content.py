"""salesassist-content MCP server - shareable product material and fund reference data.

Compliance filtering happens HERE, not in the prompt: only external + approved material for
the exact share class is returned as shareable; everything else comes back as `excluded`.
"""
from mcp.server.fastmcp import FastMCP

from app.mcp_servers._common import dumps, guarded, scoped_context
from app.services.evidence import DISCLOSURE, eligible_documents

mcp = FastMCP("salesassist-content")


@mcp.tool()
@guarded
def find_shareable_material(advisor_id: str, share_class_id: str) -> str:
    """Approved external documents for one exact share class (e.g. P101I), plus same-fund documents that
    must NOT be shared and why."""
    ctx = scoped_context(advisor_id)
    docs, excluded = eligible_documents(ctx, share_class_id)
    return dumps({"shareable": [d.model_dump() for d in docs], "excluded": [e.model_dump() for e in excluded]})


@mcp.tool()
@guarded
def get_fund_reference(advisor_id: str, share_class_id: str) -> str:
    """Licensed, dated fund data (rating, 1-year return) for a share class, with the disclosure that must
    accompany any quote."""
    ctx = scoped_context(advisor_id)
    ref = ctx.fund_refs.get(share_class_id)
    if not ref:
        return dumps({"record": None})
    return dumps({"record": ref.model_dump(),
                  "disclosure": DISCLOSURE.format(date=f"{ref.reference_date:%d %b %Y}")})


if __name__ == "__main__":
    mcp.run()
