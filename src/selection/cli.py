import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from src.models import AlterEgo, Member

console = Console()

def run_approval_ui(proposal: list[AlterEgo]) -> list[AlterEgo]:
    approved = []
    console.print("\n[bold cyan]Forum Community Simulator — Account Selection[/bold cyan]\n")
    console.print(
        f"Proposed alter egos ({len(proposal)} candidates). "
        "For each: [green]y[/green]=approve, [red]n[/red]=skip, [yellow]q[/yellow]=quit.\n"
    )

    for i, alter in enumerate(proposal, 1):
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[dim]#[/dim]", f"[bold]{i}/{len(proposal)}[/bold]")
        table.add_row("[dim]Original[/dim]", alter.original_username)
        table.add_row("[dim]Alter ego[/dim]", f"[cyan]{alter.reversed_username}[/cyan]")
        table.add_row("[dim]Posts[/dim]", f"{alter.post_count:,}")
        table.add_row(
            "[dim]Last active[/dim]",
            alter.last_active.isoformat() if alter.last_active else "unknown",
        )
        console.print(table)

        choice = Prompt.ask("Include?", choices=["y", "n", "q"], default="y")
        if choice == "q":
            break
        if choice == "y":
            approved.append(alter)
        console.print()

    while True:
        add = Prompt.ask(
            "\nAdd a member manually? Enter username (or press Enter to skip)",
            default="",
        )
        if not add:
            break
        uid = Prompt.ask("  User ID")
        posts = Prompt.ask("  Post count", default="0")
        last = Prompt.ask("  Last active (YYYY-MM-DD)")
        try:
            from datetime import date
            m = Member(
                user_id=int(uid),
                username=add.strip(),
                post_count=int(posts),
                last_active=date.fromisoformat(last),
            )
            approved.append(AlterEgo.from_member(m))
            console.print(f"[green]Added {add} → {add[::-1]}[/green]")
        except (ValueError, Exception) as e:
            console.print(f"[red]Error: {e}[/red]")

    return approved


def save_approved(
    approved: list[AlterEgo], path: str = "config/approved_accounts.json"
) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = [a.to_dict() for a in approved]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    console.print(f"\n[green]Saved {len(approved)} accounts to {path}[/green]")
