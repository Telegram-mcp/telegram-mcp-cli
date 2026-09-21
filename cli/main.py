import sys
import os
import asyncio
import argparse
from pathlib import Path
from cli.config import load_config, update_env_setting, find_env_file
from cli.client import TelegramCliClient, detect_session_environment
from cli.output import (
    console,
    err_console,
    print_error,
    print_success,
    print_warning,
    print_status_table,
    print_message,
    print_chat_history,
)


def handle_auth(args):
    target = args.session_file
    if not target or target.lower() == "login":
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        config = load_config()
        api_id_str = config.get("api_id")
        api_hash = config.get("api_hash")
        if not api_id_str or not api_hash:
            print_error("TELEGRAM_API_ID or TELEGRAM_API_HASH missing in .env")
            sys.exit(1)
            
        api_id = int(api_id_str)
        console.print("[bold cyan]Starting interactive Telegram authentication...[/bold cyan]")
        session = StringSession()
        client = TelegramClient(session, api_id, api_hash)
        
        async def run_login():
            if config.get("test_mode"):
                client.session.set_dc(2, "149.154.167.40", 443)
            await client.start()
            me = await client.get_me()
            saved = client.session.save()
            env_file = update_env_setting("TELEGRAM_SESSION", saved)
            print_success(f"Authenticated as {me.first_name} (ID: {me.id})")
            print_success(f"Saved TELEGRAM_SESSION to {env_file}")
            await client.disconnect()

        asyncio.run(run_login())
        return

    # Provided a .session file path
    path = os.path.abspath(os.path.expanduser(target))
    if not path.endswith(".session") and not os.path.exists(path) and os.path.exists(path + ".session"):
        path = path + ".session"

    if not os.path.exists(path):
        print_error(f"Session file not found at: {path}")
        sys.exit(1)

    try:
        from telethon.sessions import SQLiteSession
        s = SQLiteSession(path)
        detected_env = detect_session_environment(s)
        console.print(f"[bold cyan]Validating session file:[/bold cyan] {path}")
        console.print(f"  • Data Center: [bold]{s.dc_id}[/bold]")
        console.print(f"  • Server IP: [bold]{s.server_address or 'Not set'}[/bold]")
        console.print(f"  • Environment: [bold {'yellow' if detected_env == 'test' else 'green'}]{detected_env.upper()}[/]")
    except Exception as e:
        print_error("Failed to inspect SQLite session file", str(e))
        sys.exit(1)

    env_path = update_env_setting("TELEGRAM_SESSION_PATH", path)
    if detected_env in ("test", "production"):
        update_env_setting("TELEGRAM_TEST_MODE", "true" if detected_env == "test" else "false")

    print_success(f"Configured active session path in {env_path}")
    print_success(f"Environment auto-aligned to: TELEGRAM_TEST_MODE={'true' if detected_env == 'test' else 'false'}")


def handle_unlock():
    from cli.client import unlock_session
    res = unlock_session()
    if res["killed"]:
        for p in res["killed"]:
            print_success(f"Terminated conflicting process PID {p['pid']} ({p.get('cmd') or 'unknown'})")
    if res["removed_lockfile"]:
        print_success("Removed /tmp/telegram-mcp.lock")
    if not res["killed"] and not res["removed_lockfile"]:
        console.print("[bold green]✓[/bold green] No active session lock or conflicting process found.")
    else:
        print_success("Session lock released successfully. You can now run tg-cli commands.")


def run_async(coro):
    try:
        return asyncio.run(coro)
    except Exception as e:
        print_error(str(e))
        sys.exit(1)


def main():
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--force", "-f",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Force takeover of session lock by terminating conflicting background processes"
    )

    parser = argparse.ArgumentParser(
        prog="tg-cli",
        parents=[common_parser],
        description="Telegram MCP CLI: Interact with and test Telegram bots directly from terminal."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # unlock
    subparsers.add_parser(
        "unlock",
        parents=[common_parser],
        help="Release session lock and terminate any conflicting background process"
    )

    # auth
    auth_parser = subparsers.add_parser("auth", parents=[common_parser], help="Configure session file path or run interactive login")
    auth_parser.add_argument("session_file", nargs="?", help="Path to .session file, or 'login' for interactive flow")

    # status
    subparsers.add_parser("status", parents=[common_parser], help="Check client connection, environment, and authorization status")

    # send
    send_parser = subparsers.add_parser("send", parents=[common_parser], help="Send a message to a bot or chat")
    send_parser.add_argument("target", help="Bot or chat username (e.g. @bot or bot)")
    send_parser.add_argument("text", help="Text payload to send")
    send_parser.add_argument("--reply-to", type=int, help="Optional message ID to reply to")

    # command
    cmd_parser = subparsers.add_parser("command", parents=[common_parser], help="Send a command (e.g. /start) and await reply")
    cmd_parser.add_argument("target", help="Bot username")
    cmd_parser.add_argument("cmd", help="Command string (e.g. /start, /help)")
    cmd_parser.add_argument("--no-wait", action="store_true", help="Do not wait for bot reply")
    cmd_parser.add_argument("--timeout", type=int, default=10, help="Wait timeout in seconds (default: 10)")

    # history
    hist_parser = subparsers.add_parser("history", parents=[common_parser], help="Retrieve recent message history")
    hist_parser.add_argument("target", help="Bot or chat username")
    hist_parser.add_argument("--limit", type=int, default=10, help="Number of messages (default: 10)")

    # click
    click_parser = subparsers.add_parser("click", parents=[common_parser], help="Click an inline keyboard button")
    click_parser.add_argument("target", help="Bot username")
    click_parser.add_argument("--button", help="Button label text (case-insensitive substring)")
    click_parser.add_argument("--index", type=int, help="Button 0-based index")
    click_parser.add_argument("--msg-id", type=int, help="Specific message ID (default: latest message with buttons)")

    # send-file
    file_parser = subparsers.add_parser("send-file", parents=[common_parser], help="Upload a file, photo, or audio")
    file_parser.add_argument("target", help="Bot or chat username")
    file_parser.add_argument("path", help="Local file path")
    file_parser.add_argument("--caption", help="Optional caption text")
    file_parser.add_argument("--voice", action="store_true", help="Send as round voice note")

    # chat
    chat_parser = subparsers.add_parser("chat", parents=[common_parser], help="Open an interactive real-time chat session with a bot or user")
    chat_parser.add_argument("target", help="Bot or chat username (e.g. @my_bot)")
    chat_parser.add_argument("--history", type=int, default=10, help="Number of initial history messages to load (default: 10)")

    # exec
    exec_parser = subparsers.add_parser("exec", parents=[common_parser], help="Execute arbitrary MTProto Python code in client sandbox")
    exec_parser.add_argument("code", help="Python code snippet to execute")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "unlock":
        handle_unlock()
        return

    if args.command == "auth":
        handle_auth(args)
        return

    config = load_config()
    client = TelegramCliClient(config, force=getattr(args, "force", False))

    async def execute():
        try:
            if args.command == "status":
                status = await client.get_status()
                print_status_table(status)
            elif args.command == "send":
                msg = await client.send_message(args.target, args.text, reply_to=args.reply_to)
                print_success(f"Message sent (ID: {msg['id']})")
                print_message(msg)
            elif args.command == "command":
                res = await client.send_command(args.target, args.cmd, wait_response=not args.no_wait, timeout=args.timeout)
                print_success(f"Command sent (ID: {res['command_sent']['id']})")
                if res.get("reply"):
                    console.print("\n[bold]Bot Reply:[/bold]")
                    print_message(res["reply"])
                else:
                    print_warning("No response received within timeout.")
            elif args.command == "history":
                msgs = await client.get_history(args.target, limit=args.limit)
                print_chat_history(msgs)
            elif args.command == "click":
                res = await client.click_button(args.target, button_text=args.button, button_index=args.index, message_id=args.msg_id)
                print_success(f"Clicked button '{res['clicked']['text']}' on message {res['message_id']}")
            elif args.command == "send-file":
                sent = await client.send_file(args.target, args.path, caption=args.caption, voice=args.voice)
                print_success(f"File sent successfully (ID: {sent['id']})")
            elif args.command == "chat":
                from cli.chat import start_interactive_chat
                await start_interactive_chat(client, args.target, history_limit=args.history)
            elif args.command == "exec":
                tg = await client.connect()
                local_scope = {"client": tg, "asyncio": asyncio}
                res = eval(compile(args.code, "<string>", "eval"), {}, local_scope)
                if asyncio.iscoroutine(res):
                    res = await res
                console.print(res)
        finally:
            await client.disconnect()

    run_async(execute())


if __name__ == "__main__":
    main()
