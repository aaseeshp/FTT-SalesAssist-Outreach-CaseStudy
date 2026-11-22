"""Typed models.

Two families:
* Source records - mirror the JSON files 1:1 (UPPER_CASE aliases, snake_case attributes).
* Domain objects - what the pipeline produces (signals, facts, intents, drafts...).
"""
from __future__ import annotations

import datetime as dt
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- source records
class SourceRecord(BaseModel):
    model_config = ConfigDict(alias_generator=str.upper, populate_by_name=True, extra="ignore")


class User(SourceRecord):
    user_id: str
    display_name: str
    region_identifier: str


class Product(SourceRecord):
    product_share_class_id: str
    product_id: str
    product_name: str
    share_class_label: str


class Advisor(SourceRecord):
    advisor_id: str
    display_name: str
    role_title: str | None = None
    email_id: str
    advisor_parent_firm_name: str | None = None
    advisor_firm_name: str
    # The source field name contains a typo; keep the alias faithful to the feed.
    relationship_comments: str | None = Field(default=None, alias="RELANTIONSHIP_COMMENTS")
    region_identifier: str
    birthday_month_day: str | None = None

    @property
    def first_name(self) -> str:
        return self.display_name.split()[0]


class Activity(SourceRecord):
    advisor_id: str
    interaction_id: str
    interaction_date: date
    interaction_channel: str
    communication_direction: str
    meaningful_contact_flag: str | None = None
    interaction_subject: str | None = None
    interaction_details: str | None = None
    product_names: list[str] = Field(default_factory=list)
    region_identifier: str | None = None


class Holding(SourceRecord):
    advisor_id: str
    product_name: str
    product_share_class_id: str
    investment_vehicle: str | None = None
    asset_category: str | None = None
    current_holding_value: float
    previous_holding_value: float | None = None
    holding_value_change: float | None = None
    reference_date: date


class DailyDetail(SourceRecord):
    product_share_class_id: str
    product_name: str
    transaction_amount: float


class DailyTransactions(SourceRecord):
    transaction_summary_date: date
    product_share_class_details: list[DailyDetail] = Field(default_factory=list)


class Sale(SourceRecord):
    advisor_id: str
    most_recent_transaction_date: date
    most_recent_transaction_amount: float
    previous_transaction_date: date | None = None
    previous_transaction_amount: float | None = None
    recent_transaction_direction: str
    transaction_direction_changed: bool | None = None
    recent_daily_transactions: DailyTransactions | None = None


class FundReference(SourceRecord):
    reference_product_id: str
    product_share_class_id: str
    product_id: str
    product_name: str
    product_category: str | None = None
    overall_rating: int | None = None
    one_year_return_percent: float | None = None
    reference_date: date
    reference_note: str | None = None


class Document(SourceRecord):
    content_id: str
    product_share_class_id: str
    content_type: str
    release_date: date
    intended_audience: str
    review_status: str
    content_url: str


# --------------------------------------------------------------------------- domain objects
Resolution = Literal["exact", "text_match", "thread", "single_class", "unresolved"]


class ProductMention(BaseModel):
    """A product the advisor is linked to, resolved to a share class where the data allows."""
    product_name: str
    product_id: str | None
    share_class_id: str | None
    share_class_label: str | None
    source: Literal["activity", "holding", "sale"]
    evidence_id: str
    resolution: Resolution


class Signal(BaseModel):
    id: str
    type: str
    title: str
    date: dt.date | None = None
    strength: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    product_id: str | None = None
    share_class_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)


class Intent(BaseModel):
    id: str
    type: str
    label: str
    score: float
    rationale: str
    primary_signal_id: str
    supporting_signal_ids: list[str] = Field(default_factory=list)


class Fact(BaseModel):
    """One statement the draft is allowed to make, traceable to a source record."""
    id: str
    kind: str
    label: str
    statement: str
    source: str
    evidence_id: str | None = None
    as_of: date | None = None
    included: bool = True
    optional: bool = False
    warning: str | None = None
    disclosure: str | None = None
    url: str | None = None
    values: list[str] = Field(default_factory=list)  # tokens a draft may quote (amounts, %...)


class Exclusion(BaseModel):
    item: str
    reason: str
    source: str


class DataLink(BaseModel):
    content_id: str
    label: str
    url: str
    content_type: str
    share_class_id: str
    release_date: date
    audience: str
    review_status: str


class AdminAction(BaseModel):
    id: str
    type: Literal["log_activity", "schedule_meeting", "request_material", "set_reminder", "verify_contact"]
    label: str
    description: str
    payload: dict[str, Any] = Field(default_factory=dict)
    recommended: bool = True
    agent_note: str | None = None


class Tone(BaseModel):
    style: Literal["concise", "warm", "formal"] = "warm"
    max_words: int = 170
    reasons: list[str] = Field(default_factory=list)


class FactPack(BaseModel):
    intent: Intent
    facts: list[Fact]
    exclusions: list[Exclusion]
    gaps: list[str]
    links: list[DataLink]
    actions: list[AdminAction]
    tone: Tone
    banned_terms: list[str] = Field(default_factory=list)
    sender_name: str
    advisor_first_name: str

    def included_facts(self) -> list[Fact]:
        return [f for f in self.facts if f.included]


class Draft(BaseModel):
    subject: str
    body: str
    cited_fact_ids: list[str] = Field(default_factory=list)
    generator: str  # "crew" | "gemini" | "template"
    model: str | None = None
    note: str | None = None
    reviewed_by: str | None = None
    review_issues: list[str] = Field(default_factory=list)


class Verification(BaseModel):
    passed: bool
    checked: int
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OutreachOption(BaseModel):
    pack: FactPack
    draft: Draft
    verification: Verification


class TraceStep(BaseModel):
    key: str
    label: str
    ms: float
    detail: str = ""
    actor: str = "rules"


class AdvisorSnapshot(BaseModel):
    advisor_id: str
    name: str
    email: str
    firm: str
    region: str
    relationship_comments: str | None
    holdings: list[dict[str, Any]]
    recent_sale: dict[str, Any] | None
    last_contact: dict[str, Any] | None


class OutreachResponse(BaseModel):
    user: User
    advisor: AdvisorSnapshot
    reference_date: date
    generated_at: datetime
    signals: list[Signal]
    options: list[OutreachOption]
    trace: list[TraceStep]
    cache: Literal["hit", "miss"] = "miss"
    orchestrator: str = "rules"
    rejected_intents: list[dict[str, Any]] = Field(default_factory=list)


class RegenerateRequest(BaseModel):
    user_id: str
    intent_id: str
    included_fact_ids: list[str] | None = None
    tone: Literal["concise", "warm", "formal"] | None = None
    instructions: str | None = Field(default=None, max_length=500)


class ExecuteActionsRequest(BaseModel):
    user_id: str
    advisor_id: str
    intent_id: str
    action_ids: list[str]
    confirmed: bool = False
