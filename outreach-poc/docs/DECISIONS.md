# Key decisions

Each entry records the decision, why it was made, and what it costs.

### D1. Rules decide what is true; the LLM decides what matters most and how to say it
The brief warns that sources support less than they seem to: an outbound invite is not interest, a trade is
not a holding, and material applies to one share class and one audience. Those are policy rules, so they are
code (`evidence.py`) with golden tests, not prompt text. The model never sees a fact it is not allowed to use.
**Trade-off:** each new need requires a small amount of code (a detector and fact rules) as well as prompt text.

### D2. Multi-agent with CrewAI, distributed by responsibility
Four agents, each with a narrow role and only the tools it needs:
- **Intent Analyst:** CRM and Sales MCP tools.
- **Writer:** no tools.
- **Admin Ops:** admin MCP, read-only.
- **Compliance Reviewer:** no tools.

The Writer and Admin Ops run in parallel, and intents are composed in parallel threads. This spreads the
load across focused calls instead of one large prompt, and each agent's output can be inspected in the trace.
**Trade-off:** more model calls and higher latency (about 30–60 s for an uncached advisor). This is why D4
pre-computes drafts.

### D3. SalesAssist capabilities as MCP servers, with policy enforced inside the tools
The brief says SalesAssist already has capabilities (unified intelligence, prioritisation, admin agents). Exposing
them over MCP is how agents would reuse them in production. Region scope comes from the server environment
(`SALESASSIST_USER_ID`), never from a tool argument, so a prompt injection cannot widen access.
`find_shareable_material` returns only material that is external, approved and the exact share class.

### D4. Pre-compute and cache, so the click is instant
The brief requires that all content is accessible immediately after the click. Drafts are computed at start-up
(in production, also on "source changed" events) and cached per user, advisor and data version. The click
only runs the access check and a cache read. Regenerating after an edit uses a single fast model call, not the full crew.

### D5. Guardrails around every agent output
- Intents are reconciled against rule-detected signals. An unsupported intent is rejected, and a rule intent the agent missed is added back.
- Admin recommendations may only use candidate action IDs.
- Every draft goes through the deterministic claim checker, and a failing model draft is replaced by the template draft.
- Every model failure degrades along the chain: crew, then a single model call, then the template.

### D6. Provider-agnostic LLM layer with a model chain
The user asked for Gemini, and later for Claude (Sonnet or Haiku). Both sit behind one interface with a fallback
chain, timeouts and retries.
- **Claude (default):** `claude-sonnet-5-5`, then `claude-haiku-5-5`. Authentication uses `ant auth login` (no stored key) or `ANTHROPIC_API_KEY`.
  CrewAI's bundled Anthropic provider pins an old SDK, so `ClaudeCrewLLM` adapts the current SDK to CrewAI's `BaseLLM`.
- **Gemini:** `gemini-4-hydrogen`, then `3.8-flash`, then `3.5-flash`, then `3.5-flash-lite`. During the build, preview models often returned 503 or 429, and the chain kept the app working.

### D7. v1 supports three needs well, rather than four needs loosely
1. **Fulfil a request or promise.** This is a commitment the firm already made, and missing it hurts the relationship most.
2. **Firm move, with an offer to reconnect.** This is time-sensitive, and the advisor asked for it.
3. **Thank for a significant trade.** This is timely, and it is folded into (1) when the trade is in the same fund.

The birthday note is offered as a separate option. Meeting follow-up and service check-in are in the taxonomy,
but the guardrail rejects them until detectors exist.

### D8. The user keeps control of external communication
Nothing is sent. Every fact can be toggled, the tone can be changed, and the body can be edited. Admin actions run
only after an explicit confirmation step, and the server enforces `confirmed=true`.

### D9. Light front end, no build step
Plain HTML, CSS and JS served by FastAPI. Reviewers can read it in minutes, and it runs anywhere Python runs.
