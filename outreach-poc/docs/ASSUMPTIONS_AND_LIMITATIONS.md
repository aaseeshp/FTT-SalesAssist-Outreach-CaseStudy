# Assumptions, limitations and what is deferred

## Implemented
- End-to-end flow: CRM list, ✉ click, progress view, email dialog (intent tabs, subject, editable body, data links),
  summary box, admin actions with confirmation, and an action log.
- Seven-step pipeline with region guard, parallel assembly, share-class resolution, 5 signal detectors, ranking,
  evidence guard, compose and claim check.
- CrewAI crews (Intent Analyst; Writer ∥ Admin Ops → Compliance Reviewer) over 4 MCP servers (stdio).
- Providers: Claude (default) and Gemini, with model chains, timeouts and retries, plus a template fallback.
- Pre-compute and cache with warm-up at start-up. Regenerate with fact toggles, tone and an instruction.
- 27 automated tests covering every evidence rule in the sample data, plus the guardrails, the API and the Claude adapter.

## Assumptions
| Assumption | Why |
|---|---|
| "Today" is `REFERENCE_DATE` (2026-11-11) from `00_context.json` | Keeps the sample data's timing meaningful |
| A significant trade is ≥ $10,000, or ≥ 3× the previous one, within 14 days | Illustrative threshold. Configure per region or business |
| The lookback for requests and moves is 60 days; birthdays use a 7-day window; new material is anything from the last 30 days | Illustrative |
| A request is open unless a later record shows it was fulfilled | No "fulfilled" flag exists in the data |
| A fund with only one share class in the catalog resolves to that class | Casey's "Oakbridge factsheet" → P102A |
| Holdings are internal context and are never quoted to the advisor | The brief: "a recent trade does not establish current holdings" |
| Fund performance is off by default and needs a disclosure when included | Licensed, dated data |
| The email address may be stale after a firm move, so the user is asked to confirm it | Common CRM data-quality issue |
| The sender signs with their display name | No signature data supplied |

## Additional data I would add (and why)
- **Fulfilment status on CRM requests and promises**, so drafts aren't suggested for requests that are already closed.
- **Advisor communication preferences and opt-outs**, which compliance needs before any outreach.
- **Document jurisdiction and expiry**, because approved material can also be region-specific or superseded.
- **Sales user calendar free/busy**, so real meeting slots replace the mocked ones.
- **Sent-email outcomes** (opened, replied), to learn which intents and wording work.

## Limitations
- **Data and services are mocked.** JSON files stand in for the systems of record. MCP servers run over stdio on the same
  machine. Admin actions are mock executions with reference numbers.
- **Latency of an uncached advisor** is 30–60 s with the full crew (several model calls plus MCP start-up). The cache hides this
  for the click. Production would add event-driven re-warming and could use one MCP connection per worker.
- **The claim checker is pattern-based.** It checks amounts, percentages, decimals, URLs, fund names, banned terms, internal
  IDs and the disclosure. It cannot check paraphrased claims (for example "strong performance"). The Compliance Reviewer
  agent covers some of this, and a model-graded check is the next step.
- **The Intent Analyst uses CrewAI's text-based tool loop (ReAct)** with Claude, because the adapter does not declare native
  function calling. It works, but native tool use would be more efficient.
- **Model availability.** During the build, Gemini preview models were often overloaded (503) or out of quota (429). The
  Claude account was authenticated but had no API credits. The fallbacks handled both, and the trace shows which model was used.
- **No persistence.** The cache and action log live in memory, and restarting the server clears them.
- **Single tenant, no SSO.** The user switcher is a demo control. Production would take identity and region from SSO
  (for example Entra ID claims).

## Deferred
- Meeting follow-up and service check-in intents (in the taxonomy, no detectors yet).
- Learning from user edits (diff the sent email against the draft and feed it into evaluation).
- An evaluation harness with rubric grading of drafts across a larger synthetic set.
- Actual sending, which is out of scope by design.
- The PowerPoint deck, which is outside this phase.
