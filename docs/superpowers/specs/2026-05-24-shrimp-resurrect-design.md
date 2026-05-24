# Shrimp Resurrect — Design Specification

**Date:** 2026-05-24
**Project:** Shrimp Resurrect
**Forum:** https://forum.shrimprefuge.be/ (VBulletin, Dutch-language)

---

## Overview

A 24-hour AI experiment on an existing Dutch-language gaming community forum. The 20 most historically active members who have been absent for 2+ years are resurrected as "dark mirror" alter egos — AI agents that respond to live forum activity as those members would have, based on analysis of their post history.

The event starts overnight as a surprise. Members will recognise the alter egos immediately from the reversed usernames and mirrored avatars. The goal is one lively day that feels like the old days, with current members interacting with echoes of former friends.

**Non-goals:** This is not deception. The uncanny aesthetic (reversed names, mirrored avatars) signals "alter ego" clearly. Alters never initiate new threads. They do not spam. They respect the community's natural tone, including harsh banter and strong opinions, which are part of the culture.

---

## System Phases

The system has three sequential phases:

1. **Account selection** — identify and curate the 20 alter egos
2. **Persona workbench** — build, iterate, and approve each persona profile
3. **The event** — 24-hour live run with review queue and optional auto-approve

---

## Phase 0: Account Selection

### Goal
Produce an approved list of alter egos before any persona work begins.

### Process

1. Scrape the top 100 members by all-time post count from the memberlist page
2. For each member, check their profile page for last activity date
3. Filter to members inactive for **2+ years**
4. Sort by all-time post count descending
5. Present the ranked proposal to the forum owner for review

### Selection UI

A simple interface (terminal checklist or basic web page) showing each candidate:

```
#  Username     Posts    Last seen       Reversed name
1  radje        8 432    2023-11-04      ejdar
2  ...
```

The owner can:
- **Approve** — include this member as an alter ego
- **Skip** — exclude them (e.g., personal reasons, too recognisable in a sensitive way)
- **Add manually** — include someone not in the top 100 who was culturally significant

The approved list (target: ~20 members) locks in and drives all downstream work.

---

## Phase 1: Persona Workbench

### Goal

Produce a validated persona profile document for each alter ego before the event. Each profile must be approved by the forum owner before the alter goes live.

### Data Source

All post data is gathered by scraping the VBulletin "find all posts by user" page per member. Posts are fetched in batches of 100, starting from the most recent and going further back in time. The scraper tracks pagination state per user so batches can be added incrementally.

No full database export is required. The member ranking query is the only use case for database access, and even that is covered by the memberlist scrape.

### Persona Profile Contents

Each profile is a structured document (JSON or YAML) containing:

- **Identity** — username, user ID, reversed username, avatar path
- **Writing style** — sentence length, formality register, Dutch/Flemish dialect markers, punctuation habits, use of BBCode (heavy quoter? uses bold for emphasis? never formats?)
- **Topics of interest** — subforums and discussion types they engaged with, with a relative weight per topic (used for relevance gating during the event)
- **Opinion fingerprint** — recurring positions on topics they cared about (politics, gaming, music, etc.), extracted from post patterns
- **Relationship map** — members they engaged with most, and in what tone (ally, sparring partner, ignored)
- **Activity pattern** — time-of-day and day-of-week tendencies (used for time-aware rate limiting)
- **Typical post length** — short/medium/long, derived from post length distribution
- **Rate limits** — daily cap and hourly cap, derived from historical average (see Rate Limits section)
- **Example posts** — 10–20 verbatim posts selected as representative of their voice. These are included in every reply generation prompt as few-shot examples.

### Analysis Process

For each batch of 100 posts added:

1. **LLM pass 1** — analyse the batch for style, vocabulary, and topic distribution
2. **LLM pass 2** — read the current profile draft and the new batch, identify what is missing or should be updated
3. **Synthesis** — merge the new findings into the profile document
4. **Sample generation** — generate responses to the standard test post set using the updated profile

The profile is never rebuilt from scratch on each iteration; new batches refine and extend it.

### Test Post Set

A fixed set of diverse test prompts defined once by the forum owner before workbench work begins. Suggested types:

- A political debate post
- A gaming-related question or hot take
- Lighthearted banter directed at the alter
- A movie or music opinion thread
- A post where someone disagrees aggressively

The same test set is used for all 20 personas, enabling comparison across alters and across iterations.

### Iteration Loop

```
Load next 100 posts
    → Refine profile
    → Generate samples against test post set
    → Owner reviews samples
    → Rate each sample: ✓ in-character / ✗ off-character (with note)
    → If satisfied: mark persona as ready
    → If not: load next 100 posts and repeat
```

A persona is flagged as **ready** when all test post samples are rated in-character across two consecutive iterations with no manual profile edits between them.

### Human Validation

The forum owner is the final validator. After automated analysis, they review and can directly edit the profile to add what the LLM missed — inside jokes, community-specific references, things only a longtime member would know. This layer is what pushes a profile from "plausible" to "recognisable."

---

## Phase 2: The Event

### Account Setup

Before the event, the forum owner manually creates one VBulletin account per approved alter ego:

- **Username**: reversed (e.g., "radje" → "ejdar")
- **Avatar**: the original member's avatar, horizontally flipped
- **Profile**: minimal — left mostly blank or a short bio in Dutch

Account credentials are stored in a local config file (never committed to version control). All accounts share one password for simplicity. The persona analysis pipeline outputs the full account setup list so creation is mechanical.

### Orchestrator

A single service that runs on a configurable polling interval (default: every 5 minutes). It fetches recently-active threads from the forum and for each new post runs the five-gate decision pipeline.

#### Five-Gate Decision Pipeline

Each new post is evaluated against each approved persona:

1. **Relevance check** — does the thread topic match this persona's interest profile? Posts in topics outside the persona's interest range are skipped.
2. **Mention check** — was the alter's account directly addressed or replied to? If yes, the relevance gate is bypassed.
3. **Probability roll** — each persona has a per-topic response likelihood (0–1, derived from profile). A random draw against this score determines if they "feel like" responding.
4. **Rate limit check** — if the persona has hit their hourly or daily cap, skip.
5. **Cooldown check** — avoid multiple alters responding to the same post in the same polling cycle to prevent pile-ons.

Posts that pass all five gates proceed to reply generation.

### Rate Limits

Per-persona limits are derived from historical post data:

- Calculate average posts per day over the member's active period (total posts / active days)
- Scale down proportionally to reflect current forum size vs. historical size (forum is ~100 active members today vs. 500+ historically)
- Apply a hard cap regardless of history: **maximum 3 posts per hour, maximum 20 posts per 24 hours**

These limits are generated automatically and stored in the persona config. The forum owner reviews and can adjust them before the event.

### Reply Generation

When a post passes the decision pipeline, the LLM is called with a three-layer prompt:

1. **System prompt** — the full persona profile, including example posts. Instructs the model to write in Dutch, stay in character, use VBulletin BBCode naturally where the persona would, and not break the fourth wall or invent biographical facts.
2. **Thread context** — the last 5–10 posts from the thread, formatted as a conversation.
3. **Generation constraints** — keep length consistent with this persona's typical post length; do not use uncharacteristic greetings; stay within the persona's topic range.

The generated reply is in Dutch and may use VBulletin BBCode syntax (quotes, bold, URLs, etc.) where natural.

**Content filter:** A loose post-processing check catches technical failures only — wrong language (not Dutch), reply is empty or too short/long, or content clearly breaks the persona's factual profile. Harsh language, swearing, aggressive debate, and banter are part of the community culture and are never filtered.

Flagged replies go to the review queue marked for attention rather than being silently dropped.

### Review Queue

A lightweight local web UI showing pending replies before they post. Each card displays:

- Thread title and link
- The post being replied to (with author)
- Which alter is responding
- The generated reply (with BBCode rendered)

**Actions per card:** Approve / Edit then approve / Discard / Rate (in-character ✓ / off-character ✗ with note) / Regenerate

Ratings and notes accumulate per persona and are included in subsequent generation prompts as a feedback summary.

#### Auto-Approve Escalation

Each persona can be given an **auto-approve timer** (e.g., 10 minutes). Replies are automatically approved and posted after that delay unless manually discarded. This is how the system transitions from monitored to autonomous. The timer can be set per persona — trust is earned individually based on review queue performance.

### Posting Mechanism

Approved replies are posted to VBulletin by logging in as the alter ego account and submitting via HTTP form POST, mirroring normal browser behaviour. Each alter maintains its own session cookie, refreshed as needed.

A **randomised delay** of 1–5 minutes is added after approval before the post is submitted, to avoid all alters posting at the same second. Time-of-day awareness optionally narrows the posting window to hours consistent with the persona's historical activity pattern.

---

## Simulation Mode

Simulation mode is the **default**. Nothing touches the forum until `LIVE_MODE` is explicitly enabled.

In simulation mode, the orchestrator runs the full pipeline — scraping, decision gates, reply generation — but routes all output to the review queue only. The review queue functions identically. This mode is used for:

- Development and testing (the full pipeline can be exercised without a live forum account)
- Pre-event validation (final check that all personas produce realistic output against real current forum activity)
- Verifying that all alter accounts have valid credentials before enabling live mode

The transition to live mode is a deliberate, explicit act — not a default.

---

## Key Design Decisions

- **Reactive only** — alters never create new threads, only reply to existing activity
- **Simulation-first** — live mode is opt-in; simulation mode is the safe default throughout development
- **Incremental persona building** — post batches are added one at a time, starting from most recent, stopping when the persona is approved
- **Human as final validator** — automated analysis produces drafts; the forum owner approves all personas and the alter list
- **Posts via HTTP** — replies are submitted through the VBulletin web interface as a logged-in user, not via direct database writes
- **Dutch throughout** — all persona analysis, profile documents, and generated replies operate in Dutch; the system prompt instructs the LLM to write in the persona's specific Dutch register
