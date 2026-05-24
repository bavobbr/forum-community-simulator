from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class PersonaProfile:
    # Identity (from approved_accounts.json)
    user_id: int
    original_username: str
    reversed_username: str
    post_count: int
    last_active: str  # ISO date string

    # Analysis state
    posts_analyzed: int = 0
    pages_loaded: int = 0
    is_approved: bool = False

    # Writing style (LLM-derived)
    dialect_markers: list[str] = field(default_factory=list)
    formality: str = "casual"
    sentence_length: str = "medium"
    bbcode_habits: list[str] = field(default_factory=list)
    punctuation_style: str = ""

    # Topics: forum_name -> weight 0.0-1.0
    topic_weights: dict[str, float] = field(default_factory=dict)
    opinion_fingerprint: list[str] = field(default_factory=list)

    # Relationships: username -> "ally" | "rival" | "neutral"
    frequent_interactions: dict[str, str] = field(default_factory=dict)

    # Activity pattern
    peak_hours: list[int] = field(default_factory=list)

    # Post length characteristics
    typical_post_length: str = "medium"  # "short" | "medium" | "long"

    # Rate limits
    daily_cap: int = 10
    hourly_cap: int = 3

    # Few-shot examples and narrative summary
    example_posts: list[str] = field(default_factory=list)
    persona_summary: str = ""

    @classmethod
    def from_alter_ego(cls, alter: dict) -> "PersonaProfile":
        return cls(
            user_id=alter["user_id"],
            original_username=alter["original_username"],
            reversed_username=alter["reversed_username"],
            post_count=alter["post_count"],
            last_active=alter["last_active"],
        )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "original_username": self.original_username,
            "reversed_username": self.reversed_username,
            "post_count": self.post_count,
            "last_active": self.last_active,
            "posts_analyzed": self.posts_analyzed,
            "pages_loaded": self.pages_loaded,
            "is_approved": self.is_approved,
            "dialect_markers": self.dialect_markers,
            "formality": self.formality,
            "sentence_length": self.sentence_length,
            "bbcode_habits": self.bbcode_habits,
            "punctuation_style": self.punctuation_style,
            "topic_weights": self.topic_weights,
            "opinion_fingerprint": self.opinion_fingerprint,
            "frequent_interactions": self.frequent_interactions,
            "peak_hours": self.peak_hours,
            "typical_post_length": self.typical_post_length,
            "daily_cap": self.daily_cap,
            "hourly_cap": self.hourly_cap,
            "example_posts": self.example_posts,
            "persona_summary": self.persona_summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PersonaProfile":
        return cls(
            user_id=d["user_id"],
            original_username=d["original_username"],
            reversed_username=d["reversed_username"],
            post_count=d["post_count"],
            last_active=d["last_active"],
            posts_analyzed=d.get("posts_analyzed", 0),
            pages_loaded=d.get("pages_loaded", 0),
            is_approved=d.get("is_approved", False),
            dialect_markers=d.get("dialect_markers", []),
            formality=d.get("formality", "casual"),
            sentence_length=d.get("sentence_length", "medium"),
            bbcode_habits=d.get("bbcode_habits", []),
            punctuation_style=d.get("punctuation_style", ""),
            topic_weights=d.get("topic_weights", {}),
            opinion_fingerprint=d.get("opinion_fingerprint", []),
            frequent_interactions=d.get("frequent_interactions", {}),
            peak_hours=d.get("peak_hours", []),
            typical_post_length=d.get("typical_post_length", "medium"),
            daily_cap=d.get("daily_cap", 10),
            hourly_cap=d.get("hourly_cap", 3),
            example_posts=d.get("example_posts", []),
            persona_summary=d.get("persona_summary", ""),
        )
