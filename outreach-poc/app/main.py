"""FastAPI entry point: JSON API + the light SalesAssist CRM front end."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.data.sources import JsonDataSource
from app.models import ExecuteActionsRequest, OutreachOption, OutreachResponse, RegenerateRequest
from app.pipeline import OutreachPipeline
from app.services import actions as admin
from app.services.drafting import FallbackDrafter, TemplateDrafter
from app.services.llm import select_provider
from app.services.entitlement import NotEntitled, NotFound, get_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("salesassist")
STATIC = Path(__file__).parent / "static"


def build_pipeline() -> OutreachPipeline:
    s = get_settings()
    source = JsonDataSource(s.data_dir)
    provider, model_drafter, crew_llm_factory, agent_model = select_provider(s)
    drafter = FallbackDrafter(model_drafter, TemplateDrafter())
    crew = None
    if crew_llm_factory and agent_model and s.drafter in ("auto", "crew"):
        try:
            from app.agents.crew import CrewOrchestrator
            crew = CrewOrchestrator(s, agent_model, crew_llm_factory(agent_model), provider)
        except Exception as exc:  # noqa: BLE001
            log.warning("CrewAI unavailable (%s); using single-model drafting.", exc)
    if provider in ("template", "claude-unavailable"):
        log.warning("No LLM available (provider=%s) - running rules + templates. "
                    "Run `ant auth login` or set ANTHROPIC_API_KEY to enable Claude.", provider)
    p = OutreachPipeline(source, drafter, crew)
    log.info("Outreach pipeline mode: %s", p.mode)
    return p


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pipeline = build_pipeline()
    if get_settings().warm_cache:
        threading.Thread(target=app.state.pipeline.warm, name="warm-cache", daemon=True).start()
    yield


app = FastAPI(title="SalesAssist Outreach Assist (POC)", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _pipe() -> OutreachPipeline:
    return app.state.pipeline


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, NotEntitled):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    raise exc


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    p = _pipe()
    return {"status": "ok", "mode": p.mode, "agents": bool(p.crew), "data_version": p.source.version,
            "reference_date": p.source.reference_date().isoformat()}


@app.get("/api/users")
def users():
    return [u.model_dump() for u in _pipe().source.users()]


@app.get("/api/advisors")
def advisors(user_id: str, all_regions: bool = False):
    p = _pipe()
    try:
        user = get_user(p.source, user_id)
    except NotFound as exc:
        raise _http(exc)
    rows = []
    for a in p.source.advisors():
        in_region = a.region_identifier == user.region_identifier
        if not in_region and not all_regions:
            continue
        row = {"advisor_id": a.advisor_id, "name": a.display_name, "firm": a.advisor_firm_name,
               "email": a.email_id, "region": a.region_identifier, "in_region": in_region,
               "signals": [], "last_contact": None}
        if in_region:  # never compute signals for advisors outside the user's region
            acts = p.source.activities(a.advisor_id)
            if acts:
                row["last_contact"] = {"date": acts[0].interaction_date.isoformat(),
                                       "channel": acts[0].interaction_channel}
            row["signals"] = [{"type": s.type, "title": s.title}
                              for s in p.quick_signals(user_id, a.advisor_id) if s.type != "new_material"]
        rows.append(row)
    return rows


@app.get("/api/outreach/{advisor_id}", response_model=OutreachResponse)
def outreach(advisor_id: str, user_id: str):
    """Fired by the email icon. Served from the pre-computed cache when available."""
    try:
        return _pipe().get(user_id, advisor_id)
    except (NotEntitled, NotFound) as exc:
        raise _http(exc)


@app.post("/api/outreach/{advisor_id}/regenerate", response_model=OutreachOption)
def regenerate(advisor_id: str, req: RegenerateRequest):
    try:
        included = set(req.included_fact_ids) if req.included_fact_ids is not None else None
        return _pipe().regenerate(req.user_id, advisor_id, req.intent_id, included, req.tone, req.instructions)
    except (NotEntitled, NotFound) as exc:
        raise _http(exc)


@app.post("/api/actions/execute")
def execute_actions(req: ExecuteActionsRequest):
    """Runs administrative actions. Requires explicit user confirmation (confirmed=true)."""
    if not req.confirmed:
        raise HTTPException(status_code=400, detail="Actions run only after the user confirms them.")
    if not req.action_ids:
        raise HTTPException(status_code=400, detail="Select at least one action.")
    try:
        resp = _pipe().get(req.user_id, req.advisor_id)  # re-checks entitlement
    except (NotEntitled, NotFound) as exc:
        raise _http(exc)
    option = next((o for o in resp.options if o.pack.intent.id == req.intent_id), None)
    if option is None:
        raise HTTPException(status_code=404, detail=f"Unknown intent {req.intent_id}")
    known = {a.id: a for a in option.pack.actions}
    unknown = [i for i in req.action_ids if i not in known]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown action ids: {', '.join(unknown)}")
    return {"results": admin.execute(req.user_id, req.advisor_id, [known[i] for i in req.action_ids])}


@app.get("/api/actions/log")
def action_log():
    return admin.ACTION_LOG[-50:]
