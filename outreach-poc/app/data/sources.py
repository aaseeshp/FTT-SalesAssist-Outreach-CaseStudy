"""Source adapters.

`DataSource` is the seam between the pipeline and the systems of record. The POC ships a
JSON-file adapter; production would add CRM, sales-ledger, holdings, fund-data and DAM
adapters behind the same interface without touching the pipeline.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Protocol

from app.models import (
    Activity, Advisor, Document, FundReference, Holding, Product, Sale, User,
)


class DataSource(Protocol):
    version: str

    def reference_date(self) -> date: ...
    def users(self) -> list[User]: ...
    def advisors(self) -> list[Advisor]: ...
    def activities(self, advisor_id: str) -> list[Activity]: ...
    def holdings(self, advisor_id: str) -> list[Holding]: ...
    def sale(self, advisor_id: str) -> Sale | None: ...
    def catalog(self) -> list[Product]: ...
    def fund_references(self) -> list[FundReference]: ...
    def documents(self) -> list[Document]: ...


class JsonDataSource:
    """Reads the case-study JSON files. Each method stands in for a separate service call."""

    FILES = {
        "context": "00_context.json",
        "advisors": "01_advisors.json",
        "activities": "02_activities.json",
        "holdings": "03_holdings.json",
        "sales": "04_recent_sales.json",
        "fund_reference": "05_fund_reference.json",
        "documents": "06_documents.json",
    }

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        raw = {k: json.loads((self.data_dir / f).read_text()) for k, f in self.FILES.items()}
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
        self.version = digest[:12]  # cache key: changes whenever any source changes

        ctx = raw["context"]
        self._reference_date = date.fromisoformat(ctx["REFERENCE_DATE"])
        self._users = [User.model_validate(u) for u in ctx["USERS"]]
        self._catalog = [Product.model_validate(p) for p in ctx["PRODUCT_CATALOG"]]
        self._advisors = [Advisor.model_validate(a) for a in raw["advisors"]]
        self._activities = [Activity.model_validate(a) for a in raw["activities"]]
        self._holdings = [Holding.model_validate(h) for h in raw["holdings"]]
        self._sales = [Sale.model_validate(s) for s in raw["sales"]]
        self._fund_refs = [FundReference.model_validate(f) for f in raw["fund_reference"]]
        self._documents = [Document.model_validate(d) for d in raw["documents"]]

    def reference_date(self) -> date:
        return self._reference_date

    def users(self) -> list[User]:
        return list(self._users)

    def advisors(self) -> list[Advisor]:
        return list(self._advisors)

    def activities(self, advisor_id: str) -> list[Activity]:
        rows = [a for a in self._activities if a.advisor_id == advisor_id]
        return sorted(rows, key=lambda a: a.interaction_date, reverse=True)

    def holdings(self, advisor_id: str) -> list[Holding]:
        return [h for h in self._holdings if h.advisor_id == advisor_id]

    def sale(self, advisor_id: str) -> Sale | None:
        return next((s for s in self._sales if s.advisor_id == advisor_id), None)

    def catalog(self) -> list[Product]:
        return list(self._catalog)

    def fund_references(self) -> list[FundReference]:
        return list(self._fund_refs)

    def documents(self) -> list[Document]:
        return list(self._documents)
