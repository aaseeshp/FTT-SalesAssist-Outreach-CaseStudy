"""Step 1 - Access guard. Runs before any data is fetched or any model is called."""
from __future__ import annotations

from app.data.sources import DataSource
from app.models import Advisor, User


class NotFound(Exception):
    pass


class NotEntitled(Exception):
    def __init__(self, user: User, advisor: Advisor):
        self.user = user
        self.advisor = advisor
        super().__init__(
            f"{advisor.display_name} is assigned to region {advisor.region_identifier}. "
            f"{user.display_name} is assigned to region {user.region_identifier}, "
            "so SalesAssist cannot prepare outreach for this advisor."
        )


def get_user(source: DataSource, user_id: str) -> User:
    user = next((u for u in source.users() if u.user_id == user_id), None)
    if user is None:
        raise NotFound(f"Unknown user {user_id}")
    return user


def authorize(source: DataSource, user_id: str, advisor_id: str) -> tuple[User, Advisor]:
    """Each internal user works with exactly one region; advisors outside it are off-limits."""
    user = get_user(source, user_id)
    advisor = next((a for a in source.advisors() if a.advisor_id == advisor_id), None)
    if advisor is None:
        raise NotFound(f"Unknown advisor {advisor_id}")
    if advisor.region_identifier != user.region_identifier:
        raise NotEntitled(user, advisor)
    return user, advisor
