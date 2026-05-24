import json
from pathlib import Path

import anthropic
from rich.console import Console
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
    return _PERSONAS_DIR / f"{username}.json"


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


def _rate_samples(console: Console, samples: list[dict]) -> list[dict]:
    rated = []
    for i, sample in enumerate(samples, 1):
        console.print(Panel(
            f"[bold]{sample['label']}[/bold]\n\n"
            f"[dim]Post:[/dim] {sample['post']}\n\n"
            f"[bold cyan]Reply:[/bold cyan] {sample['reply']}",
            title=f"Sample {i}/{len(samples)}",
        ))
        while True:
            choice = console.input("[i] in-character  [x] off-character  [s] skip: ").strip().lower()
            if choice in ("i", "x", "s"):
                break
            console.print("[yellow]Kies i, x of s[/yellow]")
        rated.append({**sample, "rating": choice})
    return rated


def _run_persona_workbench(
    console: Console,
    alter: dict,
    scraper: PostScraper,
    client: anthropic.Anthropic,
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
        choice = console.input("[r] herwerk  [q] terug: ").strip().lower()
        if choice != "r":
            return
        profile.is_approved = False

    while True:
        is_first_batch = profile.pages_loaded == 0

        if is_first_batch:
            # Initial batch: fetch pages 1 and 2 together (200 posts) for richer first analysis
            console.print(f"\n[bold]Eerste batch laden (pagina 1-2, ~200 posts)...[/bold]")
            try:
                posts1, has_more1 = scraper.fetch_batch(alter["user_id"], page=1)
                posts2, has_more = scraper.fetch_batch(alter["user_id"], page=2) if has_more1 else ([], False)
            except Exception as exc:
                console.print(f"[red]Scrape mislukt: {exc}[/red]")
                return
            posts = posts1 + posts2
        else:
            next_page = profile.pages_loaded + 1
            console.print(f"\n[bold]Volgende batch laden (pagina {next_page}, ~100 posts)...[/bold]")
            try:
                posts, has_more = scraper.fetch_batch(alter["user_id"], page=next_page)
            except Exception as exc:
                console.print(f"[red]Scrape mislukt: {exc}[/red]")
                return

        if not posts:
            console.print("[yellow]Geen posts gevonden op deze pagina.[/yellow]")
            break

        console.print(f"  {len(posts)} posts opgehaald. Analyseren met Claude...")
        if is_first_batch:
            profile = analyze_first_batch(client, alter, posts)
            profile.pages_loaded = 2  # consumed pages 1 and 2
        else:
            profile = refine_with_batch(client, profile, posts)
        _save_profile(profile)
        console.print(f"  Profiel opgeslagen. Totaal geanalyseerd: {profile.posts_analyzed} posts")

        console.print("\n[bold]Voorbeeldreacties genereren...[/bold]")
        samples = generate_replies(client, profile, test_posts)
        rated = _rate_samples(console, samples)

        in_char = sum(1 for r in rated if r["rating"] == "i")
        console.print(f"\n[bold]Resultaat:[/bold] {in_char}/{len(samples)} in-character")

        if not has_more:
            console.print("[dim]Geen verdere pagina's beschikbaar.[/dim]")

        while True:
            options = "[l] volgende batch  [a] goedkeuren  [e] JSON bewerken  [q] terug naar lijst"
            if not has_more:
                options = "[a] goedkeuren  [e] JSON bewerken  [q] terug naar lijst"
            choice = console.input(f"\n{options}: ").strip().lower()

            if choice == "l" and has_more:
                break
            elif choice == "a":
                profile.is_approved = True
                _save_profile(profile)
                console.print(f"[green]✓ {username} goedgekeurd![/green]")
                return
            elif choice == "e":
                path = _persona_path(username)
                console.print(f"[dim]Bewerk: {path.resolve()}[/dim]")
                console.input("Druk Enter als klaar...")
                profile = PersonaProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
            elif choice == "q":
                return
            else:
                console.print("[yellow]Ongeldige keuze[/yellow]")


def run_workbench(
    alters: list[dict],
    scraper: PostScraper,
    client: anthropic.Anthropic,
) -> None:
    console = Console()
    test_posts = _load_test_posts()

    while True:
        console.clear()
        _show_persona_list(console, alters)

        choice = console.input("\nSelecteer persona [1-25] of q om te stoppen: ").strip().lower()
        if choice == "q":
            break
        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(alters)):
                raise ValueError
        except ValueError:
            console.print("[yellow]Ongeldige keuze[/yellow]")
            console.input("Enter om door te gaan...")
            continue

        _run_persona_workbench(console, alters[idx], scraper, client, test_posts)
        console.input("\nEnter om terug te gaan naar de lijst...")

    approved = sum(1 for a in alters if _load_profile(a).is_approved)
    console.print(f"\n[bold]Klaar. {approved}/{len(alters)} personas goedgekeurd.[/bold]")
