import json
import re
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich import box

from src.persona.models import PersonaProfile
from src.persona.scraper import PostScraper
from src.persona.analyzer import analyze_first_batch, refine_with_batch
from src.persona.generator import generate_replies

_PERSONAS_DIR = Path("personas")
_TEST_POSTS_PATH = Path("config/test_posts.json")


def _persona_path(username: str) -> Path:
    safe = re.sub(r'[^\w\-]', '_', username)
    return _PERSONAS_DIR / f"{safe}.json"


def _load_profile(alter: dict) -> PersonaProfile:
    path = _persona_path(alter["original_username"])
    if path.exists():
        return PersonaProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
    return PersonaProfile.from_alter_ego(alter)


def _save_profile(profile: PersonaProfile) -> None:
    _PERSONAS_DIR.mkdir(exist_ok=True)
    path = _persona_path(profile.original_username)
    path.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _load_test_posts() -> list[dict]:
    return json.loads(_TEST_POSTS_PATH.read_text(encoding="utf-8"))


def _show_persona_list(console: Console, alters: list[dict]) -> None:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=4)
    table.add_column("Username", min_width=18)
    table.add_column("Posts", justify="right")
    table.add_column("Analyzed", justify="right")
    table.add_column("Status", min_width=14)

    approved = 0
    for i, alter in enumerate(alters, 1):
        profile = _load_profile(alter)
        if profile.is_approved:
            approved += 1
        status = "[green]✓ approved[/green]" if profile.is_approved else (
            f"[yellow]{profile.posts_analyzed} posts[/yellow]" if profile.posts_analyzed > 0
            else "[dim]not started[/dim]"
        )
        table.add_row(
            str(i),
            alter["original_username"],
            f"{alter['post_count']:,}",
            str(profile.posts_analyzed),
            status,
        )

    console.print(Panel(table, title=f"Personas — {approved}/{len(alters)} approved"))


def _show_profile_summary(console: Console, profile: PersonaProfile) -> None:
    dialect = ", ".join(profile.dialect_markers[:8]) if profile.dialect_markers else "—"
    top_topics = sorted(profile.topic_weights.items(), key=lambda x: x[1], reverse=True)[:5]
    topics_str = "  ".join(f"{name} ({w:.2f})" for name, w in top_topics) if top_topics else "—"
    fingerprint = "\n".join(f"  • {p}" for p in profile.opinion_fingerprint[:6]) if profile.opinion_fingerprint else "  —"

    rhetorical = "\n".join(f"  • {p}" for p in profile.rhetorical_patterns[:4]) if profile.rhetorical_patterns else "  —"

    console.print(Panel(
        f"[bold]Persoonlijkheid:[/bold] {escape(profile.persona_summary or '—')}\n\n"
        f"[bold]Wereldvisie:[/bold] {escape(profile.worldview or '—')}\n\n"
        f"[bold]Standpunten ({len(profile.opinion_fingerprint)}):[/bold]\n{escape(fingerprint)}\n\n"
        f"[bold]Retorische patronen:[/bold]\n{escape(rhetorical)}\n\n"
        f"[bold]Stijl:[/bold] {profile.formality} | zinnen: {profile.sentence_length} | ~{profile.typical_post_length} woorden/post\n"
        f"[bold]Dialect:[/bold] {escape(dialect)}\n"
        f"[bold]Actief in:[/bold] {escape(topics_str)}\n"
        f"[bold]Caps:[/bold] {profile.hourly_cap}/uur  {profile.daily_cap}/dag  "
        f"| {profile.posts_analyzed} posts geanalyseerd",
        title=f"Profiel — {escape(profile.original_username)}",
        border_style="cyan",
    ))


def _rate_samples(console: Console, samples: list[dict]) -> list[dict]:
    rated = []
    for i, sample in enumerate(samples, 1):
        console.print(Panel(
            f"[bold]{escape(sample['label'])}[/bold]\n\n"
            f"[dim]Post:[/dim] {escape(sample['post'])}\n\n"
            f"[bold cyan]Reply:[/bold cyan]\n{escape(sample['reply'])}",
            title=f"Sample {i}/{len(samples)}",
        ))
        while True:
            choice = console.input(r"\[i] in-character  \[x] off-character  \[s] skip: ").strip().lower()
            if choice in ("i", "x", "s"):
                break
            console.print("[yellow]Kies i, x of s[/yellow]")
        rated.append({**sample, "rating": choice})
    return rated


_INITIAL_BATCHES = 4  # ~750-800 posts fetched and sent to LLM in one shot


def _fetch_and_analyze(
    console: Console,
    alter: dict,
    scraper: PostScraper,
    profile: PersonaProfile,
) -> None:
    if profile.pages_loaded == 0:
        _initial_fetch_and_analyze(console, alter, scraper, profile)
    else:
        _incremental_fetch_and_analyze(console, alter, scraper, profile)


def _initial_fetch_and_analyze(
    console: Console,
    alter: dict,
    scraper: PostScraper,
    profile: PersonaProfile,
) -> None:
    """Fetch all initial batches, combine, and analyze in one LLM call."""
    all_posts: list[dict] = []
    oldest_ts: int | None = None
    seen_ids: set[int] = set()

    for batch_i in range(_INITIAL_BATCHES):
        before_ts = oldest_ts if oldest_ts else None
        console.print(f"\n[bold]Batch {batch_i + 1}/{_INITIAL_BATCHES} laden...[/bold]")
        try:
            posts, oldest_ts = scraper.fetch_window(alter["original_username"], before_ts=before_ts)
        except Exception as exc:
            console.print(f"[red]Scrape mislukt: {exc}[/red]")
            if not all_posts:
                return
            break

        new_posts = [p for p in posts if p["post_id"] not in seen_ids]
        seen_ids.update(p["post_id"] for p in new_posts)
        all_posts.extend(new_posts)
        console.print(f"  {len(new_posts)} nieuwe posts ({len(all_posts)} totaal)")

        if not posts:
            console.print("[yellow]Geen verdere posts gevonden.[/yellow]")
            break

    if not all_posts:
        return

    console.print(f"\n[bold]{len(all_posts)} posts versturen naar Gemini...[/bold]")
    try:
        new_profile = analyze_first_batch(alter, all_posts)
    except ValueError as exc:
        console.print(f"[red]Analyse mislukt: {exc}[/red]")
        return

    new_profile.pages_loaded = _INITIAL_BATCHES
    new_profile.oldest_post_ts = oldest_ts or 0
    profile.__dict__.update(new_profile.__dict__)
    _save_profile(profile)


def _incremental_fetch_and_analyze(
    console: Console,
    alter: dict,
    scraper: PostScraper,
    profile: PersonaProfile,
) -> None:
    """Fetch one more batch and refine the existing profile."""
    before_ts = profile.oldest_post_ts if profile.oldest_post_ts > 0 else None
    label = f"berichten vóór batch {profile.pages_loaded}"
    console.print(f"\n[bold]Batch laden ({label})...[/bold]")

    try:
        posts, oldest_ts = scraper.fetch_window(alter["original_username"], before_ts=before_ts)
    except Exception as exc:
        console.print(f"[red]Scrape mislukt: {exc}[/red]")
        return

    if not posts:
        console.print("[yellow]Geen verdere posts gevonden.[/yellow]")
        return

    console.print(f"  {len(posts)} posts opgehaald. Verfijnen met Gemini...")
    try:
        new_profile = refine_with_batch(profile, posts)
    except ValueError as exc:
        console.print(f"[red]Analyse mislukt: {exc}[/red]")
        return

    new_profile.pages_loaded = profile.pages_loaded + 1
    new_profile.oldest_post_ts = oldest_ts or 0
    profile.__dict__.update(new_profile.__dict__)
    _save_profile(profile)


def _run_persona_workbench(
    console: Console,
    alter: dict,
    scraper: PostScraper,
    test_posts: list[dict],
) -> None:
    profile = _load_profile(alter)
    username = alter["original_username"]

    console.print(Panel(
        f"[bold]{username}[/bold] (ID {alter['user_id']}, {alter['post_count']:,} posts)\n"
        f"Posts analyzed: {profile.posts_analyzed} | Approved: {profile.is_approved}",
        title="Persona Workbench",
    ))

    if profile.is_approved:
        console.print("[green]Deze persona is al goedgekeurd.[/green]")
        choice = console.input(r"\[r] herwerk  \[x] reset  \[q] terug: ").strip().lower()
        if choice == "x":
            _persona_path(username).unlink(missing_ok=True)
            console.print(f"[yellow]Profiel gewist. Analyse herstart...[/yellow]")
            _run_persona_workbench(console, alter, scraper, test_posts)
            return
        if choice != "r":
            return
        profile.is_approved = False

    # First batch: fetch automatically on first visit
    if profile.pages_loaded == 0:
        _fetch_and_analyze(console, alter, scraper, profile)
        if profile.pages_loaded == 0:
            return  # scrape or analysis failed

    # Main action loop — user drives from here
    while True:
        _show_profile_summary(console, profile)
        choice = console.input(
            r"\[l] meer pagina's laden  \[s] voorbeeldreacties  \[a] goedkeuren"
            r"  \[e] JSON bewerken  \[x] reset  \[q] terug: "
        ).strip().lower()

        if choice == "l":
            _fetch_and_analyze(console, alter, scraper, profile)
        elif choice == "s":
            console.print("\n[bold]Voorbeeldreacties genereren...[/bold]")
            samples = generate_replies(profile, test_posts)
            rated = _rate_samples(console, samples)
            in_char = sum(1 for r in rated if r["rating"] == "i")
            console.print(f"\n[bold]Resultaat:[/bold] {in_char}/{len(samples)} in-character")
        elif choice == "a":
            profile.is_approved = True
            _save_profile(profile)
            console.print(f"[green]✓ {username} goedgekeurd![/green]")
            return
        elif choice == "e":
            path = _persona_path(username)
            console.print(f"[dim]Bewerk: {path.resolve()}[/dim]")
            console.input("Druk Enter als klaar...")
            try:
                profile = PersonaProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, KeyError) as exc:
                console.print(f"[red]Ongeldig JSON — profiel niet herladen: {exc}[/red]")
        elif choice == "x":
            _persona_path(username).unlink(missing_ok=True)
            console.print(f"[yellow]Profiel gewist. Analyse herstart...[/yellow]")
            _run_persona_workbench(console, alter, scraper, test_posts)
            return
        elif choice == "q":
            return
        else:
            console.print("[yellow]Ongeldige keuze[/yellow]")


def _bulk_analyze(console: Console, alters: list[dict], scraper: PostScraper) -> None:
    pending = [a for a in alters if _load_profile(a).pages_loaded == 0]
    if not pending:
        console.print("[yellow]Geen ongeanalyseerde personas gevonden.[/yellow]")
        console.input("Enter om door te gaan...")
        return

    console.print(f"\n[bold]Bulk analyse: {len(pending)} personas te verwerken.[/bold]")
    console.print("[dim]Druk Ctrl+C om te stoppen.[/dim]\n")

    done = 0
    failed = 0
    for alter in pending:
        profile = _load_profile(alter)
        username = alter["original_username"]
        console.rule(f"[bold]{username}[/bold] ({done + failed + 1}/{len(pending)})")
        _fetch_and_analyze(console, alter, scraper, profile)
        if profile.pages_loaded > 0:
            done += 1
            console.print(f"[green]✓ {username} — {profile.posts_analyzed} posts geanalyseerd[/green]")
        else:
            failed += 1
            console.print(f"[red]✗ {username} — mislukt[/red]")

    console.print(f"\n[bold]Klaar: {done} geanalyseerd, {failed} mislukt.[/bold]")
    console.input("Enter om terug te gaan naar de lijst...")


def run_workbench(
    alters: list[dict],
    scraper: PostScraper,
) -> None:
    console = Console()
    test_posts = _load_test_posts()

    while True:
        console.clear()
        _show_persona_list(console, alters)

        choice = console.input(
            "\nSelecteer persona (1-25), b voor bulk analyse, of q om te stoppen: "
        ).strip().lower()
        if choice == "q":
            break
        if choice == "b":
            _bulk_analyze(console, alters, scraper)
            continue
        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(alters)):
                raise ValueError
        except ValueError:
            console.print("[yellow]Ongeldige keuze[/yellow]")
            console.input("Enter om door te gaan...")
            continue

        _run_persona_workbench(console, alters[idx], scraper, test_posts)
        console.input("\nEnter om terug te gaan naar de lijst...")

    approved = sum(1 for a in alters if _load_profile(a).is_approved)
    console.print(f"\n[bold]Klaar. {approved}/{len(alters)} personas goedgekeurd.[/bold]")
