"""salesassist-book MCP server - recent sales and holdings."""
from mcp.server.fastmcp import FastMCP

from app.mcp_servers._common import dumps, guarded, scoped_context

mcp = FastMCP("salesassist-book")


@mcp.tool()
@guarded
def get_recent_sales(advisor_id: str) -> str:
    """Most recent reported sales/transactions for the advisor. Evidence id: SALE:<advisor_id>.
    A missing record means unknown, not zero. A trade does not establish current holdings."""
    ctx = scoped_context(advisor_id)
    if ctx.sale is None:
        return dumps({"evidence_id": None, "record": None, "note": "No sales record - unknown, not zero."})
    return dumps({"evidence_id": f"SALE:{advisor_id}", "record": ctx.sale.model_dump()})


@mcp.tool()
@guarded
def get_holdings(advisor_id: str) -> str:
    """Dated holdings snapshot. HOLDING_VALUE_CHANGE alone does NOT establish a purchase or redemption.
    A missing record means unknown, not zero."""
    ctx = scoped_context(advisor_id)
    return dumps({"holdings": [h.model_dump() for h in ctx.holdings],
                  "note": "Value changes may be market movement; use recent sales to establish trades."})


if __name__ == "__main__":
    mcp.run()
