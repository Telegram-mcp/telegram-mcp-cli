import os
import sys
import asyncio
from typing import Optional
from telethon import events
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML
from cli.client import TelegramCliClient
from cli.output import (
    console,
    print_error,
    print_success,
    print_warning,
    print_message,
    print_chat_history,
    print_status_table,
)
from rich.panel import Panel


async def start_interactive_chat(client: TelegramCliClient, target: str, history_limit: int = 10):
    tg = await client.connect()
    cleaned = client._clean_peer(target)

    try:
        entity = await tg.get_entity(cleaned)
    except Exception as e:
        print_error(f"Could not resolve target '{target}'", str(e))
        return

    target_title = getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(target)
    target_username = f" (@{entity.username})" if getattr(entity, "username", None) else ""

    banner_text = (
        f"[bold green]Connected to {target_title}{target_username}[/bold green]\n"
        f"[dim]Type messages or commands and press Enter to send.\n"
        f"Commands: [bold cyan]/click <label|index>[/bold cyan] • [bold cyan]/history [N][/bold cyan] • [bold cyan]/status[/bold cyan] • [bold cyan]/help[/bold cyan] • [bold cyan]/exit[/bold cyan][/dim]"
    )
    console.print(Panel(banner_text, title="⚡ tg-cli Interactive Chat", expand=False))

    latest_button_msg_id: Optional[int] = None

    if history_limit > 0:
        try:
            history = await client.get_history(target, limit=history_limit)
            for m in (history or []):
                if m.get("buttons"):
                    latest_button_msg_id = m["id"]
                    break
            print_chat_history(history)
        except Exception as e:
            print_warning(f"Failed to fetch initial history: {e}")

    @tg.on(events.NewMessage(chats=entity))
    async def on_new_message(event):
        nonlocal latest_button_msg_id
        msg_data = client._format_msg(event.message)
        if msg_data.get("buttons"):
            latest_button_msg_id = msg_data["id"]
        if not event.out:
            print_message(msg_data)

    @tg.on(events.MessageEdited(chats=entity))
    async def on_message_edited(event):
        nonlocal latest_button_msg_id
        msg_data = client._format_msg(event.message)
        if msg_data.get("buttons"):
            latest_button_msg_id = msg_data["id"]
        if not event.out:
            console.print("[dim italic]✏️ (Message edited)[/dim italic]")
            print_message(msg_data)

    prompt_label = HTML(f"<b style='color: #00d7af'>{target}</b> &gt; ")
    session: PromptSession = PromptSession()

    try:
        with patch_stdout(raw=True):
            while True:
                try:
                    user_input = await session.prompt_async(prompt_label)
                except (EOFError, KeyboardInterrupt):
                    break

                text = user_input.strip()
                if not text:
                    continue

                if text in ("/exit", "/quit", "/q"):
                    break
                elif text == "/help":
                    console.print("\n[bold cyan]In-Chat Commands Reference:[/bold cyan]")
                    console.print("  [bold cyan]/click <label>[/bold cyan]    - Click an inline button matching label (e.g. /click Help)")
                    console.print("  [bold cyan]/click <index>[/bold cyan]    - Click an inline button by index (1-based index)")
                    console.print("  [bold cyan]/history [N][/bold cyan]      - Fetch recent N messages (default: 10)")
                    console.print("  [bold cyan]/status[/bold cyan]           - View Telegram client connection and session status")
                    console.print("  [bold cyan]/clear[/bold cyan]            - Clear the terminal screen")
                    console.print("  [bold cyan]/help[/bold cyan]             - Show this help message")
                    console.print("  [bold cyan]/exit[/bold cyan] or [bold cyan]/quit[/bold cyan]  - Leave interactive chat\n")
                elif text.startswith("/click"):
                    arg = text[6:].strip()
                    if not arg:
                        console.print("[yellow]Usage: /click <button_label or 1-based index>[/yellow]")
                        continue
                    btn_index = None
                    btn_text = None
                    if arg.isdigit():
                        idx = int(arg)
                        btn_index = idx - 1 if idx > 0 else 0
                    else:
                        btn_text = arg
                    try:
                        res = await client.click_button(
                            target,
                            button_text=btn_text,
                            button_index=btn_index,
                            message_id=latest_button_msg_id,
                        )
                        print_success(f"Clicked button '{res['clicked']['text']}'")
                    except Exception as e:
                        print_error(f"Failed to click button: {e}")
                elif text.startswith("/history"):
                    parts = text.split()
                    lim = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
                    try:
                        msgs = await client.get_history(target, limit=lim)
                        print_chat_history(msgs)
                    except Exception as e:
                        print_error(f"Failed to fetch history: {e}")
                elif text == "/status":
                    try:
                        st = await client.get_status()
                        print_status_table(st)
                    except Exception as e:
                        print_error(f"Failed to get status: {e}")
                elif text == "/clear":
                    os.system("clear")
                else:
                    try:
                        sent = await client.send_message(target, text)
                        print_message(sent)
                    except Exception as e:
                        print_error(f"Failed to send message: {e}")
    finally:
        tg.remove_event_handler(on_new_message)
        tg.remove_event_handler(on_message_edited)
        console.print("[dim]Chat session closed.[/dim]")
