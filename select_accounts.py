import os
from dotenv import load_dotenv
from rich.console import Console
from src.session import VBulletinSession
from src.scraper.memberlist import parse_memberlist
from src.scraper.profile import parse_last_active
from src.selection.pipeline import filter_inactive, build_proposal
from src.selection.cli import run_approval_ui, save_approved

load_dotenv()
console = Console()

def main():
    username = os.getenv("FORUM_USERNAME")
    password = os.getenv("FORUM_PASSWORD")
    inactivity_years = int(os.getenv("INACTIVITY_YEARS", "2"))

    console.print("[bold]Logging in...[/bold]")
    session = VBulletinSession()
    if not session.login(username, password):
        console.print("[red]Login failed. Check credentials in .env[/red]")
        return

    console.print("[bold]Fetching memberlist...[/bold]")
    html = session.get("memberlist.php?order=DESC&sort=posts&pp=100")
    members = parse_memberlist(html)
    console.print(f"  Found {len(members)} members in top 100.")

    console.print("[bold]Fetching last activity dates (this takes ~2 min)...[/bold]")
    for i, member in enumerate(members):
        search_html = session.get(f"search.php?do=finduser&u={member.user_id}")
        member.last_active = parse_last_active(search_html)
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
