# tests/test_models.py
from src.models import Member, AlterEgo
from datetime import date

def test_member_fields():
    m = Member(user_id=119, username="radje", post_count=8432, last_active=date(2023, 11, 4))
    assert m.user_id == 119
    assert m.username == "radje"

def test_alter_ego_reversed_username():
    m = Member(user_id=119, username="radje", post_count=8432, last_active=date(2023, 11, 4))
    a = AlterEgo.from_member(m)
    assert a.reversed_username == "ejdar"

def test_alter_ego_reversed_username_palindrome():
    m = Member(user_id=1, username="aba", post_count=100, last_active=date(2020, 1, 1))
    a = AlterEgo.from_member(m)
    assert a.reversed_username == "aba"

def test_alter_ego_to_dict():
    m = Member(user_id=119, username="radje", post_count=8432, last_active=date(2023, 11, 4))
    a = AlterEgo.from_member(m)
    d = a.to_dict()
    assert d["user_id"] == 119
    assert d["original_username"] == "radje"
    assert d["reversed_username"] == "ejdar"
    assert d["post_count"] == 8432
    assert d["last_active"] == "2023-11-04"

def test_alter_ego_to_dict_none_last_active():
    m = Member(user_id=1, username="test", post_count=0, last_active=None)
    a = AlterEgo.from_member(m)
    d = a.to_dict()
    assert d["last_active"] is None
