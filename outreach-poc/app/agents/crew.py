"""CrewAI orchestration over SalesAssist MCP servers (Claude by default; Gemini optional).

Two crews, with deterministic guardrails between them:

  Crew 1 - Intent crew (sequential)
      Advisor Intent Analyst  --tools-->  salesassist-crm, salesassist-book  (MCP, stdio)
      -> IntentClassification  ==> reconciled against rule-detected signals (app.pipeline)

  Crew 2 - Compose crew (one per intent; intents run in parallel threads)
      Outreach Writer           (async)  - writes from the fact pack, no tools
      Admin Operations          (async)  --tools--> salesassist-admin (MCP)
      Compliance Reviewer       (sync)   - reviews the writer's output
      ==> deterministic claim checker (app.services.verifier) has the final say

The model never sees data the user is not entitled to: MCP servers are spawned per request with
the signed-in user's id in their environment, and they enforce region scope themselves.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import ExitStack
from typing import Literal

from pydantic import BaseModel, Field

from app.config import BASE_DIR, Settings
from app.models import FactPack
from app.agents import prompts as P

log = logging.getLogger(__name__)

IntentKey = Literal["fulfil_request", "firm_move_reconnect", "thank_for_trade", "service_check_in",
                    "meeting_follow_up", "birthday_greeting"]


# ------------------------------------------------------------------ structured outputs
class ClassifiedIntent(BaseModel):
    intent_type: IntentKey
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    product_name: str | None = None
    share_class_label: str | None = None
    rationale: str


class RejectedSignal(BaseModel):
    evidence_id: str
    reason: str


class IntentClassification(BaseModel):
    advisor_id: str
    intents: list[ClassifiedIntent] = Field(default_factory=list)
    rejected_signals: list[RejectedSignal] = Field(default_factory=list)


class DraftOut(BaseModel):
    subject: str
    body: str
    cited_fact_ids: list[str] = Field(default_factory=list)


class AdminOut(BaseModel):
    recommended_action_ids: list[str] = Field(default_factory=list)
    reasons: dict[str, str] = Field(default_factory=dict)


class ReviewOut(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list)
    subject: str
    body: str
    cited_fact_ids: list[str] = Field(default_factory=list)


class ComposeResult(BaseModel):
    draft: DraftOut
    review: ReviewOut | None
    admin: AdminOut | None
    timings_ms: dict[str, float]


# ------------------------------------------------------------------ orchestrator
class CrewOrchestrator:
    name = "crew"

    def __init__(self, settings: Settings, model: str, llm, provider: str):
        self.settings = settings
        self.model = model          # first model in the provider chain that answered the start-up probe
        self.provider = provider    # "claude" | "gemini"
        self.llm = llm              # CrewAI LLM (ClaudeCrewLLM adapter or CrewAI's Gemini LLM)

    # -- MCP plumbing -------------------------------------------------------------------
    def _server(self, module: str, user_id: str):
        from mcp import StdioServerParameters
        env = {**os.environ, "SALESASSIST_USER_ID": user_id, "PYTHONPATH": str(BASE_DIR)}
        return StdioServerParameters(command=sys.executable, args=["-m", f"app.mcp_servers.{module}"],
                                     env=env, cwd=str(BASE_DIR))

    def _tools(self, stack: ExitStack, user_id: str, *modules: str) -> list:
        from crewai_tools import MCPServerAdapter
        tools: list = []
        for m in modules:
            tools.extend(stack.enter_context(MCPServerAdapter(self._server(m, user_id))))
        return tools

    # -- Crew 1: intent classification -----------------------------------------------------
    def classify(self, user_id: str, advisor_id: str, reference_date: str) -> IntentClassification:
        from crewai import Agent, Crew, Process, Task
        taxonomy = "\n".join(f"  - {k}: {v}" for k, v in P.INTENT_TAXONOMY.items())
        with ExitStack() as stack:
            tools = self._tools(stack, user_id, "crm", "book")
            analyst = Agent(role=P.INTENT_ROLE, goal=P.INTENT_GOAL, backstory=P.INTENT_BACKSTORY,
                            tools=tools, llm=self.llm, allow_delegation=False, max_iter=6, verbose=False)
            task = Task(description=P.INTENT_TASK.format(advisor_id=advisor_id, reference_date=reference_date,
                                                         taxonomy=taxonomy),
                        expected_output=P.INTENT_EXPECTED_OUTPUT, agent=analyst,
                        output_pydantic=IntentClassification)
            out = Crew(agents=[analyst], tasks=[task], process=Process.sequential, verbose=False).kickoff()
        result = out.pydantic or IntentClassification.model_validate_json(_json_only(out.raw))
        result.advisor_id = advisor_id
        return result

    # -- Crew 2: compose (writer || admin) -> reviewer -------------------------------------
    def compose(self, user_id: str, advisor_id: str, pack: FactPack,
                instructions: str | None = None) -> ComposeResult:
        from crewai import Agent, Crew, Process, Task
        t0 = time.perf_counter()
        pack_json = json.dumps(P._pack_for_prompt(pack), indent=1, default=str)
        candidates = "\n".join(f"  {a.id} - {a.type} - {a.label}" for a in pack.actions) or "  (none)"
        with ExitStack() as stack:
            admin_tools = self._tools(stack, user_id, "admin")
            writer = Agent(role=P.WRITER_ROLE, goal=P.WRITER_GOAL, backstory=P.WRITER_BACKSTORY,
                           llm=self.llm, allow_delegation=False, max_iter=2, verbose=False)
            admin = Agent(role=P.ADMIN_ROLE, goal=P.ADMIN_GOAL, backstory=P.ADMIN_BACKSTORY,
                          tools=admin_tools, llm=self.llm, allow_delegation=False, max_iter=3, verbose=False)
            reviewer = Agent(role=P.REVIEW_ROLE, goal=P.REVIEW_GOAL, backstory=P.REVIEW_BACKSTORY,
                             llm=self.llm, allow_delegation=False, max_iter=2, verbose=False)

            write = Task(description=P.drafter_system(pack) + "\n\n" + P.drafter_user_prompt(pack, instructions),
                         expected_output="JSON with subject, body, cited_fact_ids", agent=writer,
                         output_pydantic=DraftOut, async_execution=True)
            plan = Task(description=P.ADMIN_TASK.format(intent_label=pack.intent.label,
                                                        advisor_id=advisor_id,
                                                        gaps=pack.gaps or "none", candidates=candidates),
                        expected_output="JSON with recommended_action_ids and reasons", agent=admin,
                        output_pydantic=AdminOut, async_execution=True)
            review = Task(description=P.REVIEW_TASK.format(pack=pack_json, banned=", ".join(pack.banned_terms) or "none",
                                                           tone=pack.tone.style, max_words=pack.tone.max_words),
                          expected_output="JSON with approved, issues, subject, body, cited_fact_ids",
                          agent=reviewer, context=[write], output_pydantic=ReviewOut)
            Crew(agents=[writer, admin, reviewer], tasks=[write, plan, review],
                 process=Process.sequential, verbose=False).kickoff()

        draft = _as(write.output, DraftOut)
        rev = _as(review.output, ReviewOut, required=False)
        adm = _as(plan.output, AdminOut, required=False)
        return ComposeResult(draft=draft, review=rev, admin=adm,
                             timings_ms={"compose_crew": round((time.perf_counter() - t0) * 1000, 1)})


def _json_only(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{"):]
    return raw[raw.find("{"): raw.rfind("}") + 1]


def _as(task_output, model: type[BaseModel], required: bool = True):
    try:
        if task_output is None:
            raise ValueError("no output")
        if isinstance(getattr(task_output, "pydantic", None), model):
            return task_output.pydantic
        return model.model_validate_json(_json_only(task_output.raw))
    except Exception:
        if required:
            raise
        log.warning("Could not parse %s output", model.__name__)
        return None
