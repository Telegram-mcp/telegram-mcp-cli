import sys
import json
from typing import Any, List, Dict, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

console = Console()
err_console = Console(stderr=True)


def print_error(msg: str, detail: Optional[str] = None):
    err_console.print(f"[bold red]❌ Error:[/bold red] {msg}")
    if detail:
        err_console.print(f"[dim]{detail}[/dim]")


def print_success(msg: str):
    console.print(f"[bold green]✓[/bold green] {msg}")


def print_warning(msg: str):
    console.print(f"[bold yellow]⚠️[/bold yellow] {msg}")


def print_status_table(status: Dict[str, Any]):
    table = Table(title="Telegram Client Status", show_header=True, header_style="bold cyan")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    env_color = "yellow" if status.get("environment") == "test" else "green"
    table.add_row("Configured Target", f"[{env_color}]{status.get('configured_env', 'unknown').upper()}[/{env_color}]")
    table.add_row("Session Environment", f"[{env_color}]{status.get('session_environment', 'unknown').upper()}[/{env_color}]")
    
    match_str = "[bold green]MATCHED[/bold green]" if status.get("environment_match") else "[bold red]MISMATCH[/bold red]"
    table.add_row("Environment Alignment", match_str)

    table.add_row("Session Storage", status.get("session_mode", "none").capitalize())
    if status.get("session_path"):
        table.add_row("Session File Path", str(status.get("session_path")))

    table.add_row("API ID Configured", "Yes" if status.get("api_id_set") else "[red]Missing[/red]")
    table.add_row("Auth Status", "[green]Authorized[/green]" if status.get("authorized") else "[red]Not Authorized[/red]")

    if status.get("user"):
        u = status["user"]
        table.add_row("User ID", str(u.get("id")))
        name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
        table.add_row("Name", name)
        if u.get("username"):
            table.add_row("Username", f"@{u['username']}")
        if u.get("phone"):
            table.add_row("Phone", u["phone"])

    console.print(table)


def print_message(msg: Dict[str, Any]):
    sender = msg.get("sender", "bot")
    sender_style = "bold blue" if sender == "user" else "bold magenta"
    title = f"[{sender_style}]{sender.upper()}[/{sender_style}] (ID: {msg.get('id')}) - {msg.get('date', '')}"
    
    content = msg.get("text") or "[italic dim](No text)[/italic dim]"
    if msg.get("media_type"):
        content += f"\n[dim yellow]📎 Media: {msg['media_type']}[/dim yellow]"
    
    border_color = "blue" if sender == "user" else "magenta"
    console.print(Panel(content, title=title, border_style=border_color, expand=False))
    
    buttons = msg.get("buttons")
    if buttons:
        btn_table = Table(show_header=False, box=None, padding=(0, 1))
        for row in buttons:
            row_texts = [f"[bold cyan][[{b.get('text')}][/bold cyan]" for b in row]
            btn_table.add_row(*row_texts)
        console.print(btn_table)


def print_chat_history(messages: List[Dict[str, Any]]):
    if not messages:
        console.print("[dim italic]No messages found.[/dim italic]")
        return
    for m in reversed(messages):
        print_message(m)
