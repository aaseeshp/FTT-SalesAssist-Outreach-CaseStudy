# Prompts

All prompt text lives in [`app/agents/prompts.py`](../app/agents/prompts.py) and is versioned with
`PROMPT_VERSION`. The version is written to the trace of every run, so a draft can be traced back to the prompt that
produced it.

## 1. Intent classifier (Advisor Intent Analyst agent)

**Goal:** decide *why* the sales user should write to this advisor now, using only evidence that tools return.

**Structure of the prompt:**
1. **Gather.** Call the tools: `get_advisor_profile`, `get_crm_activities` and `get_outreach_signals` on
   `salesassist-crm`, and `get_recent_sales` and `get_holdings` on `salesassist-book`. The tools are already
   limited to the signed-in user's region.
2. **Classify** into a closed taxonomy (exact keys):
   `fulfil_request`, `firm_move_reconnect`, `thank_for_trade`, `service_check_in`, `meeting_follow_up`,
   `birthday_greeting`.
3. **Follow the evidence rules (R1–R8).** These are the case study's own warnings turned into checkable rules:
   - R1: an outbound message with no response does not show interest.
   - R2: `MEANINGFUL_CONTACT_FLAG` is an opinion, not proof.
   - R3: a change in holding value does not establish a trade. Only the sales record does.
   - R4: a trade does not establish current holdings.
   - R5: a missing record means unknown, not zero.
   - R6: CRM notes name funds, not share classes. Don't guess the class.
   - R7: a request is open unless a later record closes it.
   - R8: every intent cites evidence IDs that a tool actually returned.
4. **Rank** with stated priorities (commitments, then time-sensitive relationship events, then trades, then personal notes).
   Return at most 3 intents, or an empty list if nothing justifies contact.
5. **Output** structured JSON (`IntentClassification`), including `rejected_signals` with reasons. That list shows what
   the agent decided *not* to use, which is useful for review.

**What happens to the output:** `pipeline.reconcile()` accepts an agent intent only when a rule-detected signal of
the same type, with overlapping evidence, supports it. The agent's order and confidence win. Unsupported intents are
shown in the UI under "Left out on purpose", and rule intents the agent missed are appended.

## 2. Outreach Writer, and the direct drafter used for regenerate
The system prompt has 9 hard rules:
- Use only the facts in the fact pack.
- Never mention excluded items or banned terms.
- Include every document URL exactly as given.
- Quote performance only with its date and the disclosure.
- Never imply holdings, and never promise returns.
- Describe gaps from the advisor's side.
- Follow the tone and length target.
- Greet by first name and sign with the sender's name.
- No internal IDs or process language.

The user turn is the fact pack as JSON. It contains only *included* facts, plus a list of exclusions so the model knows
what to avoid.

## 3. Admin Operations agent
It chooses which of the **pre-computed candidate actions** to recommend and gives one reason for each. It may call
`propose_meeting_slots`. It cannot invent actions (unknown IDs are ignored) and cannot execute anything.

## 4. Compliance Reviewer agent
It reviews the Writer's output against the fact pack and returns `approved`, `issues` and a minimally corrected
draft. The deterministic claim checker then runs regardless of what the reviewer returned.

## Why prompts are not the only safety layer
Prompts steer the model, and code enforces the rules. Every rule that matters for compliance is also enforced in code:
- **Evidence guard:** what the model can see.
- **MCP tools:** what an agent can fetch.
- **Claim checker:** what the user can be shown.
