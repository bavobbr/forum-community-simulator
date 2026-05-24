from datetime import date
from freezegun import freeze_time
from src.models import Member
from src.selection.pipeline import filter_inactive, build_proposal


@freeze_time("2026-05-24")
def test_filter_inactive_excludes_recent_members():
    members = [
        Member(user_id=1, username="active", post_count=1000, last_active=date(2025, 1, 1)),
        Member(user_id=2, username="gone", post_count=800, last_active=date(2023, 1, 1)),
    ]
    result = filter_inactive(members, min_inactive_years=2)
    assert len(result) == 1
    assert result[0].username == "gone"


@freeze_time("2026-05-24")
def test_filter_inactive_boundary():
    # Exactly 2 years ago today should NOT be included (not inactive enough)
    members = [
        Member(user_id=1, username="boundary", post_count=500, last_active=date(2024, 5, 24)),
    ]
    result = filter_inactive(members, min_inactive_years=2)
    assert len(result) == 0


@freeze_time("2026-05-24")
def test_filter_inactive_none_last_active():
    # Members with no last_active date are skipped
    members = [
        Member(user_id=1, username="unknown", post_count=500, last_active=None),
    ]
    result = filter_inactive(members, min_inactive_years=2)
    assert len(result) == 0


def test_build_proposal_returns_alter_egos():
    members = [
        Member(user_id=119, username="radje", post_count=8432, last_active=date(2023, 11, 4)),
        Member(user_id=50, username="test", post_count=1000, last_active=date(2022, 3, 1)),
    ]
    proposal = build_proposal(members, limit=20)
    assert len(proposal) == 2
    assert proposal[0].original_username == "radje"
    assert proposal[0].reversed_username == "ejdar"


def test_build_proposal_respects_limit():
    members = [
        Member(user_id=i, username=f"user{i}", post_count=1000 - i, last_active=date(2020, 1, 1))
        for i in range(30)
    ]
    proposal = build_proposal(members, limit=20)
    assert len(proposal) == 20


def test_build_proposal_sorted_by_post_count():
    members = [
        Member(user_id=1, username="low", post_count=100, last_active=date(2020, 1, 1)),
        Member(user_id=2, username="high", post_count=9000, last_active=date(2020, 1, 1)),
    ]
    proposal = build_proposal(members, limit=20)
    assert proposal[0].original_username == "high"
