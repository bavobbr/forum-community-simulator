import os
import time
from dotenv import load_dotenv
from rich.console import Console
from src.session import VBulletinSession
from src.scraper.memberlist import parse_memberlist
from src.scraper.profile import parse_last_active
from src.selection.pipeline import filter_inactive, build_proposal
from src.selection.cli import run_approval_ui, save_approved

load_dotenv()
console = Console()

_RATE_LIMIT_MARKER = "wait"

def _fetch_last_active(session: VBulletinSession, user_id: int, delay: int) -> object:
    """Fetch last active date, retrying once if rate-limited."""
    time.sleep(delay)
    html = session.get(f"search.php?do=finduser&u={user_id}")
    if _RATE_LIMIT_MARKER in html and "seconds between searches" in html:
        console.print("    [yellow]Rate limited — waiting 30s...[/yellow]")
        time.sleep(30)
        html = session.get(f"search.php?do=finduser&u={user_id}")
    return parse_last_active(html)

def main():
    username = os.getenv("FORUM_USERNAME")
    password = os.getenv("FORUM_PASSWORD")
    inactivity_years = int(os.getenv("INACTIVITY_YEARS", "2"))
    search_delay = int(os.getenv("SEARCH_DELAY", "6"))

    console.print("[bold]Logging in...[/bold]")
    session = VBulletinSession()
    if not session.login(username, password):
        console.print("[red]Login failed. Check credentials in .env[/red]")
        return

    console.print("[bold]Fetching memberlist...[/bold]")
    html = session.get("memberlist.php?order=DESC&sort=posts&pp=100")
    members = parse_memberlist(html)
    console.print(f"  Found {len(members)} members in top 100.")

    eta_min = len(members) * search_delay // 60
    console.print(f"[bold]Fetching last activity dates (~{eta_min} min at {search_delay}s delay)...[/bold]")
    for i, member in enumerate(members):
        member.last_active = _fetch_last_active(session, member.user_id, search_delay)
        console.print(f"  [{i+1}/{len(members)}] {member.username}: {member.last_active}")

    inactive = filter_inactive(members, min_inactive_years=inactivity_years)
    console.print(f"\n[bold]{len(inactive)} members inactive for {inactivity_years}+ years.[/bold]")

    proposal = build_proposal(inactive, limit=30)
    approved = run_approval_ui(proposal)

    if approved:
        save_approved(approved)
    else:
        console.print("[yellow]No accounts approved. Nothing saved.[/yellow]")

if __name__ == "__main__":
    main()
