"""Local address validation, OAuth origins and readiness must fail safely."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from local_config import LocalConfig, company_hostname, load_config, save_config
from local_launcher import launch, streamlit_command, validate_login, wait_ready


class LocalConfigTests(unittest.TestCase):
    def test_company_name_generates_a_loopback_name(self):
        self.assertEqual(company_hostname("Livraria São João & Filhos"), "skopos.livraria-sao-joao-filhos.localhost")
        for name in ("!!!", "a" * 64):
            with self.assertRaises(ValueError):
                company_hostname(name)

    def test_rejects_network_names_and_malformed_local_names(self):
        for hostname in ("0.0.0.0", "192.168.0.1", "empresa.com.br", "evil.localhost.example",
                         "http://skopos.empresa.localhost", "x.localhost:8501", "-x.localhost",
                         "x..localhost", "LOCALHOST", "ç.localhost", "x" * 64 + ".localhost"):
            with self.subTest(hostname=hostname), self.assertRaises(ValueError):
                LocalConfig(hostname)
        for port in (80, 65536, True, "8501"):
            with self.assertRaises(ValueError):
                LocalConfig(port=port)

    def test_missing_config_preserves_current_localhost_login(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_config(Path(directory) / "missing.json"), LocalConfig())

    def test_roundtrip_keeps_private_data_out_of_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local_app.json"
            config = LocalConfig("skopos.livraria.localhost", 8502)
            save_config(config, path)
            self.assertEqual(load_config(path), config)
            self.assertEqual(set(json.loads(path.read_text())), {"hostname", "port"})
            self.assertFalse(path.with_suffix(".json.new").exists())
            path.write_text('{"hostname":"localhost", "port":8501, "password":"fake"}')
            with self.assertRaises(ValueError):
                load_config(path)


class LocalLauncherTests(unittest.TestCase):
    def auth(self, redirect="http://localhost:8501/oauth2callback"):
        return {"auth": {"redirect_uri": redirect, "cookie_secret": "fake-strong-cookie",
                         "google": {"client_id": "fake", "client_secret": "fake-secret",
                                    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration"}}}

    def test_changing_the_hostname_does_not_silently_break_oauth(self):
        validate_login(LocalConfig(), self.auth())
        validate_login(LocalConfig(port=8502), self.auth("http://localhost:{port}/oauth2callback"))
        original = self.auth()
        with self.assertRaises(ValueError):
            validate_login(LocalConfig("skopos.empresa.localhost"), original)
        self.assertEqual(original["auth"]["redirect_uri"], "http://localhost:8501/oauth2callback")
        with self.assertRaises(ValueError):
            validate_login(LocalConfig(), {})

    def test_commands_keep_loopback_bind_and_security_and_use_private_secrets(self):
        args = streamlit_command(LocalConfig("skopos.empresa.localhost"), "C:/Python com espaço/python.exe")
        self.assertEqual(args[0], "C:/Python com espaço/python.exe")
        self.assertEqual(args[args.index("--global.developmentMode") + 1], "false")
        self.assertEqual(args[args.index("--server.address") + 1], "127.0.0.1")
        self.assertEqual(args[args.index("--browser.serverAddress") + 1], "skopos.empresa.localhost")
        self.assertEqual(args[args.index("--server.enableCORS") + 1], "true")
        self.assertEqual(args[args.index("--server.enableXsrfProtection") + 1], "true")
        self.assertTrue(args[args.index("--secrets.files") + 1].endswith("secrets.toml"))

    def test_frozen_launcher_disables_development_mode_and_keeps_data_dir(self):
        with patch("sys.frozen", True, create=True):
            args = streamlit_command(LocalConfig("skopos.empresa.localhost", 8502), "Skopos.exe")
        self.assertEqual(args[:3], ["Skopos.exe", "--serve", "--data-dir"])
        self.assertEqual(args[args.index("--global.developmentMode") + 1], "false")
        self.assertEqual(args[args.index("--server.port") + 1], "8502")

    def test_desktop_environment_prevents_streamlit_frozen_auto_detection(self):
        from desktop_entry import configure_environment
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"STREAMLIT_GLOBAL_DEVELOPMENT_MODE":"true"}):
            configure_environment(directory)
            self.assertEqual(os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"], "false")

    def test_login_failure_does_not_start_db_backup_or_browser(self):
        with patch("local_launcher.preflight", side_effect=ValueError("Login incompatível")), \
                patch("local_postgres.start") as start, patch("local_postgres.backup") as backup, \
                patch("local_launcher.webbrowser.open") as browser:
            with self.assertRaises(ValueError):
                launch(LocalConfig())
            start.assert_not_called()
            backup.assert_not_called()
            browser.assert_not_called()

    def test_exited_process_never_passes_readiness(self):
        process = Mock()
        process.poll.return_value = 1
        with self.assertRaises(RuntimeError):
            wait_ready(process, 8501, "fake-token", timeout=0.1)

    def test_health_request_is_loopback_and_has_instance_token(self):
        response = Mock(status=200)
        response.read.return_value = b"ok"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        opener = Mock()
        opener.open.return_value = response
        with patch("local_launcher.build_opener", return_value=opener):
            wait_ready(Mock(poll=Mock(return_value=None)), 8501, "test-nonce", timeout=0.1)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8501/_skopos/health")
        self.assertIn("test-nonce", request.headers.values())

    def test_server_checks_instance_token_and_rejects_missing_or_wrong_values(self):
        from local_app_server import readiness
        with patch.dict(os.environ, {"SKOPOS_INSTANCE_TOKEN": "correct"}):
            for token, status in (("", 404), ("wrong", 404), ("correct", 200)):
                response = asyncio.run(readiness(Mock(headers={"X-Skopos-Instance": token})))
                self.assertEqual(response.status_code, status)
        with patch.dict(os.environ, {"SKOPOS_INSTANCE_TOKEN": ""}):
            self.assertEqual(asyncio.run(readiness(Mock(headers={}))).status_code, 404)


if __name__ == "__main__":
    unittest.main()
