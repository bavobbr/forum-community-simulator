from datetime import date
from src.models import Member, AlterEgo


def filter_inactive(members: list[Member], min_inactive_years: int) -> list[Member]:
    """Filter members who have been inactive for at least min_inactive_years.

    A member is considered inactive if their last_active date is before the cutoff date.
    The cutoff is calculated as today's date minus min_inactive_years years.
    """
    cutoff = date.today().replace(year=date.today().year - min_inactive_years)
    return [
        m for m in members
        if m.last_active is not None and m.last_active < cutoff
    ]


def build_proposal(members: list[Member], limit: int = 20) -> list[AlterEgo]:
    """Build an alter ego proposal from inactive members.

    Sorts members by post_count in descending order and creates AlterEgo objects
    for the top 'limit' members.
    """
    sorted_members = sorted(members, key=lambda m: m.post_count, reverse=True)
    return [AlterEgo.from_member(m) for m in sorted_members[:limit]]
