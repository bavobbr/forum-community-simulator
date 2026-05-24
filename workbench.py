import json
import os
from pathlib import Path
from dotenv import load_dotenv
import anthropic
from rich.console import Console

from src.session import VBulletinSession
from src.persona.scraper import PostScraper
from src.workbench.cli import run_workbench

load_dotenv()

_APPROVED_ACCOUNTS = Path("config/approved_accounts.json")

def main() -> None:
    console = Console()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ANTHROPIC_API_KEY ontbreekt in .env[/red]")
        return

    username = os.getenv("FORUM_USERNAME")
    password = os.getenv("FORUM_PASSWORD")
    search_delay = int(os.getenv("SEARCH_DELAY", "6"))

    if not username or not password:
        console.print("[red]FORUM_USERNAME of FORUM_PASSWORD ontbreekt in .env[/red]")
        return

    try:
        alters = json.loads(_APPROVED_ACCOUNTS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        console.print(f"[red]Bestand niet gevonden: {_APPROVED_ACCOUNTS}[/red]")
        return
    except json.JSONDecodeError as exc:
        console.print(f"[red]Ongeldig JSON in {_APPROVED_ACCOUNTS}: {exc}[/red]")
        return
    console.print(f"[bold]{len(alters)} alter egos geladen.[/bold]")

    console.print("[bold]Inloggen op forum...[/bold]")
    session = VBulletinSession()
    if not session.login(username, password):
        console.print("[red]Login mislukt. Controleer credentials in .env[/red]")
        return
    console.print("[green]Ingelogd.[/green]")

    scraper = PostScraper(session, delay=search_delay)
    client = anthropic.Anthropic(api_key=api_key)

    run_workbench(alters, scraper, client)


if __name__ == "__main__":
    main()
