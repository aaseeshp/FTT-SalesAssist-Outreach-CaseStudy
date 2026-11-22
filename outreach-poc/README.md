# SalesAssist · Outreach Assist (POC)

A sales professional clicks the **email icon** next to a Financial Advisor in SalesAssist. An email-style
dialog opens with:

- **Suggested emails.** One tab per reason to write (the recommended one first), each with a subject and an editable
  body that links only to approved material.
- **A summary box.** It explains why this email, which facts it uses, what was left out on purpose and why, a snapshot of
  the advisor, and how the draft was prepared (which steps were rules and which were agents).
- **Administrative actions.** You can select CRM logging, meeting holds, material requests, reminders or contact checks,
  and run one or several. Each run needs an explicit confirmation step.

SalesAssist never sends the email. The user edits it and sends it from their own mail client.

```
CRM list ──click ✉──▶ access check ▶ assemble 6 sources ▶ detect signals ▶ classify intent (agent)
                    ▶ evidence guard (fact pack) ▶ Writer ∥ Admin Ops → Compliance Reviewer (agents)
                    ▶ deterministic claim check ▶ email dialog + summary + admin actions
```

Read next: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) ·
[docs/DECISIONS.md](docs/DECISIONS.md) ·
[docs/ASSUMPTIONS_AND_LIMITATIONS.md](docs/ASSUMPTIONS_AND_LIMITATIONS.md) ·
[docs/PROMPTS.md](docs/PROMPTS.md) ·
[docs/data-map.html](docs/data-map.html) (interactive data map, open in a browser)

---

## Quick start

Requires Python 3.11+ (tested on 3.11.3, macOS).

```bash
cd outreach-poc
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install "anthropic==2.12.0"   # re-assert after crewai (see note in requirements.txt)

# Optional: enable Claude (recommended)
brew install anthropics/tap/ant && ant auth login      # or: export ANTHROPIC_API_KEY=...

.venv/bin/uvicorn app.main:app --port 8000
# open http://localhost:8000
```

**No model access is needed to try it.** Without credentials the app runs in *template mode*. The same rules,
evidence guard, claim checker and UI all work, and deterministic templates write the drafts. With Claude (or
Gemini) available, the CrewAI agents take over intent classification and drafting.

| Mode (shown top-right in the UI) | When | What writes the email |
|---|---|---|
| `CrewAI agents · claude · claude-sonnet-5-5` | `ant auth login` done or `ANTHROPIC_API_KEY` set | 4 CrewAI agents over 4 MCP servers |
| `CrewAI agents · gemini · …` | Only `GEMINI_API_KEY` set | Same crew on the first Gemini model that answers |
| `Drafting: template` | No model reachable | Deterministic templates |

Configuration lives in [.env.example](.env.example).

### Run the tests

```bash
.venv/bin/python -m pytest -q      # 24 tests, no network, no model calls
```

The tests encode every evidence rule found in the sample data (see "What to look for" below).

---

## Demo script (5 minutes)

1. **Alex Chen · T1** (default user). Click ✉ next to **Riley Morgan**.
   - The *Recommended* tab is "Send requested information: Riverstone Income Fund". It links the Class I factsheet
     and commentary (D101, D102) and thanks Riley for the $25,000 purchase.
   - *Left out on purpose* lists D103: a newer factsheet, but for Class A. The Oakbridge −$5,000 is also there,
     because a value change is not a redemption.
   - Tick the fund-data fact and click **Apply & regenerate**. The rating and return are added with their
     "as of" date and the disclosure.
2. Click ✉ next to **Jordan Ellis**.
   - "Congratulate on new firm & reconnect" offers three proposed slots. A warning asks you to confirm the email address
     at the new firm.
   - The webinar invite is excluded, because it was outbound with no reply.
   - The birthday note (in 4 days) is offered as a separate tab.
   - Select **Hold 3 meeting slots** and **Confirm email address**, then click **Run selected actions** and confirm.
     The results appear, and the "Recent admin actions" log updates.
3. Tick **Show other regions** and click ✉ next to **Casey Brooks**. You are blocked, because Casey is in region T2.
4. Switch the user to **Sam Lee · T2** and open Casey.
   - The only Oakbridge document (D104) is internal, so it is blocked. The draft says the factsheet will follow.
   - **Request approved material from marketing** is pre-selected.

---

## Project layout

```
app/
  main.py                FastAPI app + API routes, serves the front end
  pipeline.py            Orchestrates the 7 steps; cache + warm-up; agent/rule reconciliation
  config.py              Settings from env/.env
  models.py              Source records (mirror JSON) + domain objects (Signal, Fact, FactPack, Draft…)
  data/sources.py        DataSource interface + JSON adapter (swap for CRM/ledger/DAM adapters)
  services/
    entitlement.py       Step 1  region access guard
    context.py           Step 2  parallel assembly + share-class resolution
    signals.py           Step 3  pluggable signal detectors
    ranker.py            Step 4  explainable intent ranking (rules baseline / guardrail)
    evidence.py          Step 5  evidence guard → fact pack (facts, exclusions, gaps, links)
    actions.py                   administrative actions: suggestions + mock executor
    drafting.py          Step 6  Template / Gemini drafters + fallback wrapper
    llm.py                       Claude drafter, Claude→CrewAI adapter, provider selection
    model_chain.py               model fallback chain, retry/timeout policy
    verifier.py          Step 7  deterministic claim checker
  agents/
    prompts.py           All prompts (intent classifier, writer, admin ops, compliance reviewer)
    crew.py              CrewAI crews: Intent crew; Compose crew (Writer ∥ Admin Ops → Reviewer)
  mcp_servers/           Mock SalesAssist capabilities as MCP servers (stdio)
    crm.py  book.py  content.py  admin.py
  static/                Light HTML/CSS/JS front end (no build step)
data/                    Case-study JSON (synthetic) + data dictionary
docs/                    Architecture, decisions, assumptions, prompts, data map
tests/                   Rule golden tests + pipeline/API tests
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Mode, data version, reference date |
| GET | `/api/users` | Sales users (for the demo user switcher) |
| GET | `/api/advisors?user_id=&all_regions=` | CRM list with signal chips (only for in-region advisors) |
| GET | `/api/outreach/{advisor_id}?user_id=` | **Fired by the email icon.** Served from the pre-computed cache |
| POST | `/api/outreach/{advisor_id}/regenerate` | Re-draft one intent with fact toggles, tone and an instruction |
| POST | `/api/actions/execute` | Run selected admin actions. Requires `confirmed: true` |
| GET | `/api/actions/log` | Recent admin actions |

Interactive docs: http://localhost:8000/docs
