import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from cli.config import load_config, update_env_setting, find_env_file
from cli.client import TelegramCliClient, detect_session_environment
from cli.output import print_status_table, print_message, print_chat_history
from cli.main import handle_auth


class TestTelegramCli(unittest.TestCase):
    def test_detect_session_environment(self):
        self.assertEqual(detect_session_environment("149.154.167.40"), "test")
        self.assertEqual(detect_session_environment("149.154.175.10"), "test")
        self.assertEqual(detect_session_environment("149.154.167.51"), "production")
        self.assertEqual(detect_session_environment("91.108.56.130"), "production")
        self.assertEqual(detect_session_environment(None), "unknown")

    def test_clean_peer(self):
        self.assertEqual(TelegramCliClient._clean_peer("mybot"), "@mybot")
        self.assertEqual(TelegramCliClient._clean_peer("@mybot"), "@mybot")
        self.assertEqual(TelegramCliClient._clean_peer("https://t.me/mybot"), "@mybot")
        self.assertEqual(TelegramCliClient._clean_peer("12345678"), 12345678)
        self.assertEqual(TelegramCliClient._clean_peer("-100123456789"), -100123456789)

    def test_config_update_env_setting(self):
        with tempfile.TemporaryDirectory() as td:
            env_path = Path(td) / ".env"
            update_env_setting("TEST_KEY", "test_value", target_env=env_path)
            content = env_path.read_text()
            self.assertIn("TEST_KEY='test_value'", content)

    def test_handle_auth_session_file(self):
        import argparse
        from telethon.sessions import SQLiteSession

        with tempfile.NamedTemporaryFile(suffix=".session") as tf, \
             tempfile.TemporaryDirectory() as td:
            s = SQLiteSession(tf.name)
            s.set_dc(2, "149.154.167.40", 443)
            s.save()
            s.close()

            env_path = Path(td) / ".env"
            with patch("cli.main.update_env_setting", side_effect=lambda k, v: update_env_setting(k, v, target_env=env_path)):
                args = argparse.Namespace(session_file=tf.name)
                handle_auth(args)
                content = env_path.read_text()
                self.assertIn("TELEGRAM_SESSION_PATH", content)
                self.assertIn("TELEGRAM_TEST_MODE='true'", content)

    def test_output_renderers(self):
        # Ensure status and message formatters run without raising exceptions
        status_data = {
            "authorized": True,
            "configured_env": "test",
            "session_environment": "test",
            "environment_match": True,
            "session_mode": "file",
            "session_path": "/tmp/test.session",
            "api_id_set": True,
            "user": {
                "id": 123,
                "first_name": "Tester",
                "last_name": "Bot",
                "username": "tester",
                "phone": "+1 555 *** 1234",
            },
        }
        print_status_table(status_data)

        msg_data = {
            "id": 1,
            "sender": "bot",
            "text": "Hello world",
            "date": "2026-09-21 12:00:00",
            "media_type": None,
            "buttons": [[{"text": "Btn 1", "data": "d1"}]],
        }
        print_message(msg_data)
        print_chat_history([msg_data])

    def test_chat_parser(self):
        import argparse
        from cli.main import main

        # Verify parser accepts chat subcommand with options
        with patch("sys.argv", ["tg-cli", "chat", "@my_bot", "--history", "20"]), \
             patch("cli.main.TelegramCliClient") as mock_client, \
             patch("cli.main.run_async") as mock_run_async:
            mock_inst = MagicMock()
            mock_client.return_value = mock_inst
            main()
            self.assertTrue(mock_run_async.called)

    def test_unlock_command(self):
        from cli.main import main
        from cli.client import unlock_session

        with patch("sys.argv", ["tg-cli", "unlock"]), \
             patch("cli.client.unlock_session", return_value={"killed": [{"pid": 9999, "cmd": "dummy"}], "removed_lockfile": True}):
            main()

    def test_force_flag(self):
        from cli.main import main

        with patch("sys.argv", ["tg-cli", "--force", "status"]), \
             patch("cli.main.TelegramCliClient") as mock_client, \
             patch("cli.main.run_async") as mock_run_async:
            mock_inst = MagicMock()
            mock_client.return_value = mock_inst
            main()
            mock_client.assert_called_with(unittest.mock.ANY, force=True)


if __name__ == "__main__":
    unittest.main()
