from pathlib import Path
from src.scraper.memberlist import parse_memberlist

FIXTURE = Path("tests/fixtures/memberlist.html").read_text(encoding="utf-8")

def test_parse_returns_list_of_members():
    members = parse_memberlist(FIXTURE)
    assert isinstance(members, list)
    assert len(members) > 0

def test_parse_member_fields():
    members = parse_memberlist(FIXTURE)
    first = members[0]
    assert isinstance(first.user_id, int)
    assert isinstance(first.username, str)
    assert len(first.username) > 0
    assert isinstance(first.post_count, int)
    assert first.post_count > 0

def test_parse_members_sorted_by_post_count_descending():
    members = parse_memberlist(FIXTURE)
    counts = [m.post_count for m in members]
    assert counts == sorted(counts, reverse=True)

def test_radje_present():
    members = parse_memberlist(FIXTURE)
    usernames = [m.username.lower() for m in members]
    assert "radje" in usernames

def test_radje_user_id():
    members = parse_memberlist(FIXTURE)
    radje = next(m for m in members if m.username.lower() == "radje")
    assert radje.user_id == 119

def test_radje_post_count():
    members = parse_memberlist(FIXTURE)
    radje = next(m for m in members if m.username.lower() == "radje")
    assert radje.post_count == 45261

def test_all_members_have_none_last_active():
    # last_active is not available from memberlist — always None at this stage
    members = parse_memberlist(FIXTURE)
    assert all(m.last_active is None for m in members)
