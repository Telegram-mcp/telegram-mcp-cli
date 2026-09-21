# AGENT.md - Telegram MCP CLI Guide

> [!WARNING]
> **Disclaimer**: This project is an independent open-source tool and is **not affiliated with, authorized, maintained, sponsored, or endorsed by Telegram FZ-LLC, Telegram Messenger Inc., or any of their affiliates**. "Telegram" is a registered trademark of its respective owners.

This guide documents the architecture, commands, development workflow, and conventions for the `telegram-mcp-cli` project.

---

## 1. Project Overview

`telegram-mcp-cli` provides a terminal command-line interface (`tg-cli`) for controlling, testing, and interacting with Telegram bots. It directly interfaces with Telethon MTProto sessions (both SQLite `.session` files and `StringSession`), with automatic data center environment detection and an exclusive process file lock (`/tmp/telegram-mcp.lock`) to prevent concurrent key invalidation.

---

## 2. Directory Structure

```
/root/telegram-mcp-cli
├── pyproject.toml         # Package setup & console script entrypoint (tg-cli)
├── requirements.txt       # Core dependencies (telethon, python-dotenv, rich)
├── requirements-dev.txt   # Development dependencies (pytest)
├── .env.example           # Configuration template
├── .gitignore             # Git ignore rules
├── README.md              # Rich documentation
├── AGENT.md               # AI agent instructions
├── AGENT_HISTORY.md       # Agent session work log (Asia/Kolkata timezone)
├── LICENSE                # MIT License
├── cli/
│   ├── __init__.py        # Package exports
│   ├── auth.py            # Session validation & login workflows
│   ├── chat.py            # Real-time interactive terminal chat session
│   ├── config.py          # Configuration loading & .env updater
│   ├── client.py          # Telethon MTProto client
│   ├── lock.py            # Exclusive process lock manager & diagnostics
│   ├── main.py            # CLI argument parsing and subcommands
│   └── output.py          # Rich terminal renderers
└── tests/
    ├── __init__.py
    └── test_cli.py        # Automated test suite
```

---

## 3. Development Commands

- **Install Dependencies**: `pip install -r requirements.txt`
- **Install Dev Dependencies**: `pip install -r requirements-dev.txt`
- **Install in Editable Mode**: `pip install -e .`
- **Run Unit Tests**: `python3 -m pytest tests -v`
- **Run CLI**: `tg-cli --help`

---

## 4. CLI Subcommands Reference

1. `tg-cli auth [session_file | login]`
   - Points to a `.session` file path, validates SQLite integrity and DC environment, and saves `TELEGRAM_SESSION_PATH` and aligned `TELEGRAM_TEST_MODE` to `.env`.
   - Run `tg-cli auth login` for interactive phone/code or QR login.

2. `tg-cli status [--force]`
   - Checks client authorization, active user metadata, and verifies environment alignment (Test vs. Production).

3. `tg-cli unlock`
   - Inspects `/tmp/telegram-mcp.lock`, terminates conflicting process holding the lock, and safely releases the lock.

4. `tg-cli chat <target> [--history N] [--force]`
   - Starts a full two-way interactive live terminal chat with real-time incoming message polling, button clicking (`/click`), and prompt-toolkit input handling.

5. `tg-cli send <target> <text> [--reply-to ID]`
   - Sends formatted messages to bots or chats.

6. `tg-cli command <target> <cmd> [--no-wait] [--timeout SECONDS]`
   - Sends slash commands like `/start` or `/help` and displays the bot's reply and buttons.

7. `tg-cli history <target> [--limit N]`
   - Prints chat conversation history formatted with panels and timestamps.

8. `tg-cli click <target> [--button TEXT] [--index N] [--msg-id ID]`
   - Clicks inline keyboard callback buttons.

9. `tg-cli send-file <target> <file_path> [--caption TEXT] [--voice]`
   - Sends files, photos, audio, or circular voice notes.

10. `tg-cli exec <code>`
   - Executes arbitrary Telethon Python snippets directly in the MTProto client context.

---

## 5. Security & Session Safety

- **Process Locking**: Prevents concurrent MTProto sessions using `/tmp/telegram-mcp.lock`.
- **Environment Mismatch Shield**: Prevents connecting to the wrong Telegram network cluster (Test vs. Production) to avoid session key revocation.
- **Privacy**: Phone numbers in `status` and `user` payloads are automatically masked.
