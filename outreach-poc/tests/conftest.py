import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Tests never call a model: deterministic rules + template drafter only.
os.environ["LLM_PROVIDER"] = "template"
os.environ["WARM_CACHE"] = "false"

from app.config import get_settings  # noqa: E402
from app.data.sources import JsonDataSource  # noqa: E402
from app.pipeline import OutreachPipeline  # noqa: E402
from app.services.context import assemble  # noqa: E402
from app.services.drafting import FallbackDrafter, TemplateDrafter  # noqa: E402
from app.services.entitlement import authorize  # noqa: E402


@pytest.fixture(scope="session")
def source():
    return JsonDataSource(get_settings().data_dir)


@pytest.fixture
def ctx(source):
    def _ctx(user_id: str, advisor_id: str):
        user, advisor = authorize(source, user_id, advisor_id)
        return assemble(source, user, advisor)
    return _ctx


@pytest.fixture
def pipeline(source):
    return OutreachPipeline(source, FallbackDrafter(None, TemplateDrafter()))
