# SalesAssist · AI-assisted advisor outreach (case study)

A capability for the SalesAssist sales workspace. When a salesperson clicks the **email icon** next to a Financial
Advisor, a grounded, ready-to-edit email appears. It comes with the reasons behind it, the approved material to link,
and the follow-up admin tasks, which run only after confirmation.

| Deliverable | Where |
|---|---|
| Presentation (PowerPoint) | [`deck/FT_Outreach_Assist.pptx`](deck/FT_Outreach_Assist.pptx) |
| Architecture overview diagram | [`outreach-poc/docs/architecture.svg`](outreach-poc/docs/architecture.svg) · [ARCHITECTURE.md](outreach-poc/docs/ARCHITECTURE.md) |
| Working proof of concept (FastAPI, light HTML, CrewAI agents, MCP servers) | [`outreach-poc/`](outreach-poc/) (start with its [README](outreach-poc/README.md)) |
| Decisions, assumptions and limitations | [DECISIONS.md](outreach-poc/docs/DECISIONS.md) · [ASSUMPTIONS_AND_LIMITATIONS.md](outreach-poc/docs/ASSUMPTIONS_AND_LIMITATIONS.md) · [PROMPTS.md](outreach-poc/docs/PROMPTS.md) |
| Plan and interactive data map | [`planning/outreach-plan.html`](planning/outreach-plan.html) · [`outreach-poc/docs/data-map.html`](outreach-poc/docs/data-map.html) |

## Run the prototype

```bash
cd outreach-poc
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install "anthropic==2.12.0"
.venv/bin/uvicorn app.main:app --port 8000      # open http://localhost:8000
.venv/bin/python -m pytest -q                   # 27 tests, no network
```

No model key is needed. Without one, the app runs the same rules and UI and writes drafts from templates. To enable the
agents, run `ant auth login` (Claude) or set `GEMINI_API_KEY`. See [`outreach-poc/.env.example`](outreach-poc/.env.example).

## Rebuild the deck

```bash
cd deck && npm install && NODE_PATH="$PWD/node_modules" node build.js
```

`build.js` generates the deck from code, using screenshots of the running prototype in `deck/shots/`.

All data in this repository is the synthetic sample data supplied with the case study. Document URLs are placeholders.
