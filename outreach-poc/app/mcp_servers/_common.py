from __future__ import annotations

import functools
import json
import os
from functools import lru_cache

from app.config import get_settings
from app.data.sources import JsonDataSource
from app.services.context import AdvisorContext, assemble
from app.services.entitlement import NotEntitled, NotFound, authorize


@lru_cache(maxsize=1)
def source() -> JsonDataSource:
    return JsonDataSource(get_settings().data_dir)


def current_user_id() -> str:
    uid = os.environ.get("SALESASSIST_USER_ID")
    if not uid:
        raise RuntimeError("SALESASSIST_USER_ID not set - server must be spawned by the SalesAssist host.")
    return uid


def scoped_context(advisor_id: str) -> AdvisorContext:
    user, advisor = authorize(source(), current_user_id(), advisor_id)
    return assemble(source(), user, advisor)


def dumps(obj) -> str:
    return json.dumps(obj, default=str, indent=1)


def guarded(fn):
    """Turn entitlement errors into tool results the agent can read (instead of crashing)."""
    @functools.wraps(fn)  # keeps the signature FastMCP uses to build the tool schema
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (NotEntitled, NotFound) as exc:
            return dumps({"error": str(exc)})
    return wrapper
