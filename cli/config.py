import os
from pathlib import Path
from typing import Optional, Dict
from dotenv import load_dotenv, set_key

DEFAULT_ENV_SEARCH_PATHS = [
    Path.cwd() / ".env",
    Path("/root/telegram-mcp-cli/.env"),
    Path("/root/bot-mcp/.env"),
]


def find_env_file() -> Optional[Path]:
    for p in DEFAULT_ENV_SEARCH_PATHS:
        if p.exists():
            return p
    return None


def load_config() -> Dict[str, str]:
    env_file = find_env_file()
    if env_file:
        load_dotenv(dotenv_path=env_file)
    else:
        load_dotenv()

    return {
        "api_id": os.environ.get("TELEGRAM_API_ID", ""),
        "api_hash": os.environ.get("TELEGRAM_API_HASH", ""),
        "session": os.environ.get("TELEGRAM_SESSION", ""),
        "session_path": os.environ.get("TELEGRAM_SESSION_PATH", ""),
        "test_mode": os.environ.get("TELEGRAM_TEST_MODE", "false").lower() == "true",
        "default_bot": os.environ.get("DEFAULT_TARGET_BOT", ""),
        "ignore_env_mismatch": os.environ.get("TELEGRAM_IGNORE_ENV_MISMATCH", "false").lower() == "true",
        "env_file": str(env_file) if env_file else "",
    }


def update_env_setting(key: str, value: str, target_env: Optional[Path] = None) -> Path:
    if target_env is None:
        target_env = find_env_file()
        if target_env is None:
            target_env = Path.cwd() / ".env"

    if not target_env.exists():
        target_env.touch(mode=0o600)

    set_key(str(target_env), key, value)
    os.environ[key] = value
    return target_env
