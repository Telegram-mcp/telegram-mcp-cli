import os
import sys
import fcntl
import asyncio
from typing import Optional, Dict, Any, List, Union
from telethon import TelegramClient, custom, errors
from telethon.sessions import StringSession, SQLiteSession
from telethon.tl import functions, types

LOCKFILE_PATH = "/tmp/telegram-mcp.lock"

TELEGRAM_TEST_IPS = {
    "149.154.167.40",
    "149.154.175.10",
    "149.154.175.117",
    "2001:67c:4e8:f002::e",
    "2001:b88:1::10",
    "2001:b88:2::bb",
}


def detect_session_environment(session_or_address: Any) -> str:
    if hasattr(session_or_address, "server_address"):
        addr = getattr(session_or_address, "server_address", None)
    else:
        addr = session_or_address

    if not addr:
        return "unknown"

    if str(addr).strip() in TELEGRAM_TEST_IPS:
        return "test"
    return "production"


class TelegramCliClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client: Optional[TelegramClient] = None
        self._lock_fd: Optional[int] = None
        self.session_mode: Optional[str] = None
        self.session_file_path: Optional[str] = None
        self.session_environment: Optional[str] = None

    def acquire_lock(self):
        if self._lock_fd is not None:
            return
        fd = os.open(LOCKFILE_PATH, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise RuntimeError(
                "Another telegram-mcp or CLI process is currently active. "
                "Simultaneous sessions risk key revocation. "
                "Please terminate the other process or check /tmp/telegram-mcp.lock."
            )
        os.write(fd, f"pid={os.getpid()}\n".encode())
        os.fsync(fd)
        self._lock_fd = fd

    def release_lock(self):
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None
            try:
                os.unlink(LOCKFILE_PATH)
            except OSError:
                pass

    async def connect(self) -> TelegramClient:
        if self.client and self.client.is_connected():
            return self.client

        self.acquire_lock()

        api_id_str = self.config.get("api_id")
        api_hash = self.config.get("api_hash")
        session_path = self.config.get("session_path", "").strip()
        session_str = self.config.get("session", "").strip()
        is_test_mode = bool(self.config.get("test_mode", False))

        if not api_id_str or not api_hash:
            raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be configured in .env.")

        # Auto-detect if session string is a file path
        if not session_path and session_str:
            cand = os.path.abspath(os.path.expanduser(session_str))
            if session_str.endswith(".session") or os.path.exists(cand) or os.path.exists(cand + ".session"):
                session_path = session_str
                session_str = ""

        api_id = int(api_id_str)

        if session_path:
            resolved_path = os.path.abspath(os.path.expanduser(session_path))
            if not os.path.exists(resolved_path) and os.path.exists(resolved_path + ".session"):
                resolved_path = resolved_path + ".session"
            if not os.path.exists(resolved_path):
                raise FileNotFoundError(f"Session file not found at: {resolved_path}")
            session = SQLiteSession(resolved_path)
            self.session_mode = "file"
            self.session_file_path = resolved_path
        elif session_str:
            session = StringSession(session_str)
            self.session_mode = "string"
            self.session_file_path = None
        else:
            raise ValueError("No TELEGRAM_SESSION or TELEGRAM_SESSION_PATH configured.")

        session_env = detect_session_environment(session)
        expected_env = "test" if is_test_mode else "production"

        if session_env != "unknown" and session_env != expected_env and not self.config.get("ignore_env_mismatch"):
            dc_info = f" (DC {session.dc_id} @ {session.server_address})" if hasattr(session, "server_address") and session.server_address else ""
            raise ValueError(
                f"Telegram environment mismatch detected!\n"
                f"  - Configured: TELEGRAM_TEST_MODE={str(is_test_mode).lower()} ({expected_env.capitalize()} Server)\n"
                f"  - Session Target: {session_env.capitalize()} Server{dc_info}\n"
                f"Set TELEGRAM_TEST_MODE={'true' if session_env == 'test' else 'false'} in .env, "
                f"or run with --ignore-mismatch."
            )

        self.session_environment = session_env
        self.client = TelegramClient(session, api_id, api_hash, flood_sleep_threshold=5)

        if is_test_mode and (session.server_address is None or session.server_address in TELEGRAM_TEST_IPS):
            self.client.session.set_dc(2, "149.154.167.40", 443)

        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise PermissionError("Telegram client is not authorized. Run 'tg-cli auth <path.session>' or login first.")

        return self.client

    async def disconnect(self):
        if self.client and self.client.is_connected():
            try:
                await self.client.disconnect()
            except Exception:
                pass
        self.client = None
        self.release_lock()

    @staticmethod
    def _clean_peer(peer: Union[str, int]) -> Union[str, int]:
        if isinstance(peer, int):
            return peer
        p = str(peer).strip()
        if (p.startswith("-100") and p[4:].isdigit()) or (p.startswith("-") and p[1:].isdigit()) or p.isdigit():
            return int(p)
        if "t.me/" in p:
            p = p.split("t.me/")[-1].split("/")[0]
        if not p.startswith("@") and not p.startswith("+"):
            return f"@{p}"
        return p

    def _format_msg(self, msg) -> Dict[str, Any]:
        buttons = None
        if getattr(msg, "buttons", None):
            buttons = []
            for row in msg.buttons:
                btn_row = []
                for b in row:
                    btn_row.append({"text": b.text, "data": b.data.decode("utf-8", "replace") if b.data else None})
                buttons.append(btn_row)

        media_type = None
        if getattr(msg, "photo", None):
            media_type = "photo"
        elif getattr(msg, "voice", None):
            media_type = "voice"
        elif getattr(msg, "audio", None):
            media_type = "audio"
        elif getattr(msg, "document", None):
            media_type = "document"

        date_str = msg.date.strftime("%Y-%m-%d %H:%M:%S") if getattr(msg, "date", None) else ""
        return {
            "id": msg.id,
            "sender": "user" if getattr(msg, "out", False) else "bot",
            "text": getattr(msg, "text", "") or "",
            "date": date_str,
            "media_type": media_type,
            "buttons": buttons,
        }

    async def get_status(self) -> Dict[str, Any]:
        client = await self.connect()
        me = await client.get_me()

        phone_masked = None
        if me.phone:
            p = str(me.phone)
            phone_masked = f"+{p[:2]} {'*' * (len(p) - 6)} {p[-4:]}" if len(p) > 6 else ("*" * len(p))

        is_test = self.config.get("test_mode", False)
        return {
            "authorized": True,
            "configured_env": "test" if is_test else "production",
            "session_environment": self.session_environment,
            "environment_match": self.session_environment == ("test" if is_test else "production"),
            "session_mode": self.session_mode,
            "session_path": self.session_file_path,
            "api_id_set": bool(self.config.get("api_id")),
            "user": {
                "id": me.id,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "username": me.username,
                "phone": phone_masked,
            },
        }

    async def send_message(self, target: str, text: str, reply_to: Optional[int] = None) -> Dict[str, Any]:
        client = await self.connect()
        peer = await client.get_input_entity(self._clean_peer(target))
        sent = await client.send_message(peer, text, reply_to=reply_to)
        return self._format_msg(sent)

    async def send_command(self, target: str, command: str, wait_response: bool = True, timeout: int = 10) -> Dict[str, Any]:
        client = await self.connect()
        cmd = command.strip()
        if not cmd.startswith("/"):
            cmd = f"/{cmd}"
        peer = await client.get_input_entity(self._clean_peer(target))
        sent = await client.send_message(peer, cmd)
        
        reply_dict = None
        if wait_response:
            poll_interval = 0.5
            start = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start < timeout:
                msgs = await client.get_messages(peer, limit=5)
                for m in msgs:
                    if not m.out and m.id > sent.id:
                        reply_dict = self._format_msg(m)
                        break
                if reply_dict:
                    break
                await asyncio.sleep(poll_interval)

        return {"command_sent": self._format_msg(sent), "reply": reply_dict}

    async def get_history(self, target: str, limit: int = 10) -> List[Dict[str, Any]]:
        client = await self.connect()
        peer = await client.get_input_entity(self._clean_peer(target))
        msgs = await client.get_messages(peer, limit=limit)
        return [self._format_msg(m) for m in msgs]

    async def click_button(self, target: str, button_text: Optional[str] = None, button_index: Optional[int] = None, message_id: Optional[int] = None) -> Dict[str, Any]:
        client = await self.connect()
        peer = await client.get_input_entity(self._clean_peer(target))
        target_msg = None

        if message_id:
            m = await client.get_messages(peer, ids=message_id)
            if m and getattr(m, "buttons", None):
                target_msg = m
        else:
            msgs = await client.get_messages(peer, limit=10)
            for m in msgs:
                if getattr(m, "buttons", None):
                    target_msg = m
                    break

        if not target_msg or not getattr(target_msg, "buttons", None):
            raise ValueError(f"No message with inline keyboard buttons found for {target}.")

        all_buttons = []
        for r_idx, row in enumerate(target_msg.buttons):
            for c_idx, btn in enumerate(row):
                all_buttons.append((r_idx, c_idx, btn))

        clicked_btn = None
        if button_text:
            for r_idx, c_idx, btn in all_buttons:
                if button_text.lower() in btn.text.lower():
                    await btn.click()
                    clicked_btn = {"text": btn.text, "row": r_idx, "col": c_idx}
                    break
        elif button_index is not None and 0 <= button_index < len(all_buttons):
            r_idx, c_idx, btn = all_buttons[button_index]
            await btn.click()
            clicked_btn = {"text": btn.text, "row": r_idx, "col": c_idx}

        if not clicked_btn:
            available = [b.text for _, _, b in all_buttons]
            raise ValueError(f"Button '{button_text or button_index}' not found. Available buttons: {available}")

        return {"clicked": clicked_btn, "message_id": target_msg.id}

    async def send_file(self, target: str, file_path: str, caption: Optional[str] = None, voice: bool = False) -> Dict[str, Any]:
        client = await self.connect()
        resolved = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"File not found: {resolved}")
        peer = await client.get_input_entity(self._clean_peer(target))
        sent = await client.send_file(peer, resolved, caption=caption, voice_note=voice)
        return self._format_msg(sent)
