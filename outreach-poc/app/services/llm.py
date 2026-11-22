"""LLM providers: Claude (default) and Gemini, behind one shape.

Each provider supplies:
  * a model chain   - preferred model first, cheaper/faster fallbacks after
  * probe()         - first model in the chain that answers (used for the agents)
  * drafter()       - single-call drafter with structured output (fast regenerate path)
  * crew_llm(model) - the LLM object CrewAI agents run on

Claude auth: the Anthropic SDK resolves ANTHROPIC_API_KEY, or the profile created by
`ant auth login` - no key needs to be stored in this project.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from app.agents.prompts import drafter_system, drafter_user_prompt
from app.config import Settings
from app.models import Draft, FactPack
from app.services.model_chain import call_with_chain

log = logging.getLogger(__name__)


class _DraftOut(BaseModel):
    subject: str
    body: str
    cited_fact_ids: list[str] = Field(default_factory=list)


class RefusalError(RuntimeError):
    """Model declined (stop_reason == 'refusal'); the chain moves to the next model."""


# =============================================================================================
# Claude
# =============================================================================================
def claude_client(settings: Settings):
    import anthropic
    # Zero-arg credential resolution: ANTHROPIC_API_KEY -> ANTHROPIC_AUTH_TOKEN -> `ant auth login` profile.
    return anthropic.Anthropic(timeout=settings.llm_timeout_s, max_retries=1)


class ClaudeDrafter:
    name = "claude"

    def __init__(self, settings: Settings, models: list[str]):
        self.client = claude_client(settings)
        self.models = models
        self.model = models[0]

    def draft(self, pack: FactPack, instructions: str | None = None) -> Draft:
        def call(model: str):
            resp = self.client.messages.parse(
                model=model,
                max_tokens=4000,
                system=drafter_system(pack),
                messages=[{"role": "user", "content": drafter_user_prompt(pack, instructions)}],
                output_format=_DraftOut,
                output_config={"effort": "low"},  # short, fact-bound writing: low effort is enough
            )
            if resp.stop_reason == "refusal":
                raise RefusalError(f"{model} declined")
            return resp
        resp, used = call_with_chain(self.models, call)
        out: _DraftOut = resp.parsed_output
        note = None if used == self.models[0] else f"{self.models[0]} was unavailable; drafted with {used}."
        return Draft(subject=out.subject, body=out.body, cited_fact_ids=out.cited_fact_ids,
                     generator="claude", model=used, note=note)


def _crew_base():
    from crewai.llms.base_llm import BaseLLM
    return BaseLLM


class ClaudeCrewLLM(_crew_base()):  # type: ignore[misc]
    """CrewAI LLM backed by the current Anthropic SDK.

    CrewAI's bundled Anthropic provider pins an old SDK and only reads ANTHROPIC_API_KEY.
    This adapter uses SDK 2.x (so `ant auth login` works) and lets CrewAI drive tools with
    its text-based ReAct loop (no native function calling declared).
    """
    effort: str = "low"
    max_output_tokens: int = 8000
    timeout_s: float = 60.0
    _client: Any = PrivateAttr(default=None)

    def model_post_init(self, __context: Any) -> None:
        import anthropic
        self._client = anthropic.Anthropic(timeout=self.timeout_s, max_retries=2)

    def call(self, messages, tools=None, callbacks=None, available_functions=None,
             from_task=None, from_agent=None, response_model=None) -> str:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        system = "\n\n".join(_text(m.get("content")) for m in messages if m.get("role") == "system")
        conv = [{"role": m["role"], "content": _text(m.get("content")) or "(empty)"}
                for m in messages if m.get("role") in ("user", "assistant")]
        if not conv or conv[0]["role"] != "user":
            conv.insert(0, {"role": "user", "content": "Begin."})
        if conv[-1]["role"] == "assistant":  # no assistant prefill on current models
            conv.append({"role": "user", "content": "Continue."})
        kwargs: dict[str, Any] = dict(model=self.model, max_tokens=self.max_output_tokens, messages=conv,
                                      output_config={"effort": self.effort})
        if system:
            kwargs["system"] = system
        stops = [s for s in (self.stop or []) if s and s.strip()]
        if stops:
            kwargs["stop_sequences"] = stops
        resp = self._client.messages.create(**kwargs)
        if resp.stop_reason == "refusal":
            raise RefusalError(f"{self.model} declined")
        return "".join(b.text for b in resp.content if b.type == "text")

    def supports_stop_words(self) -> bool:
        return True

    def get_context_window_size(self) -> int:
        return 200_000


def _text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return str(content)


def claude_probe(settings: Settings, models: list[str]) -> str | None:
    client = claude_client(settings)
    try:
        _, used = call_with_chain(models, lambda m: client.messages.create(
            model=m, max_tokens=16, output_config={"effort": "low"},
            messages=[{"role": "user", "content": "Reply OK."}]), attempts_per_model=1)
        return used
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "credit balance" in msg:
            hint = "Authenticated, but the organization has no API credits (Console > Plans & Billing)."
        elif "authentication" in msg.lower() or "api_key" in msg:
            hint = "No credentials. Run `ant auth login` or set ANTHROPIC_API_KEY."
        else:
            hint = msg[:160]
        log.warning("Claude not available: %s", hint)
        return None


# =============================================================================================
# Provider selection
# =============================================================================================
class Provider(BaseModel):
    name: str
    agent_model: str | None  # model the CrewAI agents run on (None = agents disabled)
    chain: list[str]

    model_config = {"arbitrary_types_allowed": True}


def select_provider(settings: Settings):
    """Returns (provider_name, drafter_or_None, crew_llm_factory_or_None, agent_model)."""
    want = settings.llm_provider
    if want in ("auto", "claude"):
        chain = [settings.claude_model] + [m for m in settings.claude_fallback_models if m != settings.claude_model]
        model = claude_probe(settings, chain)
        if model:
            factory = lambda m: ClaudeCrewLLM(model=m, effort="low", timeout_s=settings.llm_timeout_s)  # noqa: E731
            return "claude", ClaudeDrafter(settings, chain), factory, model
        if want == "claude":
            return "claude-unavailable", None, None, None
    if want in ("auto", "gemini") and settings.gemini_api_key:
        from app.services.drafting import GeminiDrafter
        from app.services.model_chain import model_chain, resolve_available
        chain = model_chain(settings)
        model = resolve_available(settings)
        drafter = GeminiDrafter(settings.gemini_api_key, chain, settings.gemini_timeout_ms)
        if model:
            from crewai import LLM
            factory = lambda m: LLM(model=f"gemini/{m}", api_key=settings.gemini_api_key,  # noqa: E731
                                    temperature=0.2, timeout=settings.gemini_timeout_ms / 1000)
            return "gemini", drafter, factory, model
        return "gemini", drafter, None, None
    return "template", None, None, None
