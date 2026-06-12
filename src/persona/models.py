from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pydantic import BaseModel, Field


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
    pages_loaded: int = 0          # number of batches fetched
    oldest_post_ts: int = 0        # Unix timestamp of oldest post seen; next batch loads posts before this
    is_approved: bool = False

    # Writing style (LLM-derived)
    dialect_markers: list[str] = field(default_factory=list)
    formality: str = "casual"
    sentence_length: str = "medium"
    punctuation_style: str = ""

    # Topics: forum_name -> weight 0.0-1.0
    topic_weights: dict[str, float] = field(default_factory=dict)
    opinion_fingerprint: list[str] = field(default_factory=list)

    # Relationships: username -> "ally" | "rival" | "neutral"
    frequent_interactions: dict[str, str] = field(default_factory=dict)

    # Activity pattern
    peak_hours: list[int] = field(default_factory=list)

    # Post length characteristics — average word count per post
    typical_post_length: int = 50

    # Rate limits
    daily_cap: int = 10
    hourly_cap: int = 3

    # Few-shot examples and narrative summary
    example_posts: list[str] = field(default_factory=list)
    persona_summary: str = ""

    # Deep character — used to extrapolate to new topics
    worldview: str = ""                          # core values, outlook, philosophy
    psychological_profile: str = ""              # underlying behavioral psychology and drives
    rhetorical_patterns: list[str] = field(default_factory=list)  # how they argue and engage
    interest_tags: list[str] = field(default_factory=list)

    # Conversational Mechanics
    signature_phrases: list[str] = field(default_factory=list)
    conflict_behavior: str = ""
    humor_and_sarcasm: str = ""
    pet_peeves: list[str] = field(default_factory=list)
    formatting_quirks: str = ""

    # Event orchestrator — None means manual approval only
    auto_approve_minutes: int | None = None

    # Mystery guest flag
    mystery_guest: bool = False

    @classmethod
    def from_alter_ego(cls, alter: dict) -> "PersonaProfile":
        return cls(
            user_id=int(alter["user_id"]),
            original_username=alter["original_username"],
            reversed_username=alter["reversed_username"],
            post_count=int(alter["post_count"]),
            last_active=alter["last_active"],
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PersonaProfile":
        return cls(
            user_id=int(d["user_id"]),
            original_username=d["original_username"],
            reversed_username=d["reversed_username"],
            post_count=int(d["post_count"]),
            last_active=d["last_active"],
            posts_analyzed=d.get("posts_analyzed", 0),
            pages_loaded=d.get("pages_loaded", 0),
            oldest_post_ts=d.get("oldest_post_ts", 0),
            is_approved=d.get("is_approved", False),
            dialect_markers=d.get("dialect_markers", []),
            formality=d.get("formality", "casual"),
            sentence_length=d.get("sentence_length", "medium"),
            punctuation_style=d.get("punctuation_style", ""),
            topic_weights=d.get("topic_weights", {}),
            opinion_fingerprint=d.get("opinion_fingerprint", []),
            frequent_interactions=d.get("frequent_interactions", {}),
            peak_hours=d.get("peak_hours", []),
            typical_post_length=int(d.get("typical_post_length", 50)),
            daily_cap=d.get("daily_cap", 10),
            hourly_cap=d.get("hourly_cap", 3),
            example_posts=d.get("example_posts", []),
            persona_summary=d.get("persona_summary", ""),
            worldview=d.get("worldview", ""),
            psychological_profile=d.get("psychological_profile", ""),
            rhetorical_patterns=d.get("rhetorical_patterns", []),
            interest_tags=d.get("interest_tags", []),
            signature_phrases=d.get("signature_phrases", []),
            conflict_behavior=d.get("conflict_behavior", ""),
            humor_and_sarcasm=d.get("humor_and_sarcasm", ""),
            pet_peeves=d.get("pet_peeves", []),
            formatting_quirks=d.get("formatting_quirks", ""),
            auto_approve_minutes=d.get("auto_approve_minutes", None),
            mystery_guest=d.get("mystery_guest", False),
        )


class GeneratedReply(BaseModel):
    # 1. Emotional Anchoring (VAD Model)
    valence: int = Field(ge=1, le=10, description="1 = extremely negative/hostile, 5 = neutral, 10 = extremely positive/friendly")
    arousal: int = Field(ge=1, le=10, description="1 = extremely calm/bored/tired, 10 = extremely excited/agitated/furious")
    dominance: int = Field(ge=1, le=10, description="1 = submissive/yielding, 10 = highly dominant/controlling the conversation")
    
    # 2. Cognitive Strategy
    analysis: str = Field(description="Analyze the trigger based on your VAD state. Does it hit a pet peeve? Who is the speaker?")
    core_message: str = Field(description="The literal message or opinion you want to convey.")
    style_strategy: str = Field(description="Which signature phrases, dialect markers, and formatting will you use to reflect the VAD state?")
    
    # 3. Execution
    final_reply: str = Field(description="The final public forum reply, written exactly as the persona.")
