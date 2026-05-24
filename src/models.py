from dataclasses import dataclass
from datetime import date

@dataclass
class Member:
    user_id: int
    username: str
    post_count: int
    last_active: date | None

@dataclass
class AlterEgo:
    user_id: int
    original_username: str
    reversed_username: str
    post_count: int
    last_active: date | None

    @classmethod
    def from_member(cls, member: "Member") -> "AlterEgo":
        return cls(
            user_id=member.user_id,
            original_username=member.username,
            reversed_username=member.username[::-1],
            post_count=member.post_count,
            last_active=member.last_active,
        )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "original_username": self.original_username,
            "reversed_username": self.reversed_username,
            "post_count": self.post_count,
            "last_active": self.last_active.isoformat() if self.last_active else None,
        }
