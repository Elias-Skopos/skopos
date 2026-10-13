import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop_google import import_credentials, parse_credentials


class GoogleConfigTests(unittest.TestCase):
    def test_import_accepts_only_matching_desktop_client_and_preserves_existing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory)/"download.json", Path(directory)/"private/google.json"
            valid = {"installed":{"client_id":"desktop-id", "client_secret":"desktop-secret", "token_uri":"https://untrusted.invalid"}}
            source.write_text(json.dumps(valid))
            import_credentials(source, destination=target, expected_id="desktop-id")
            self.assertEqual(parse_credentials(target, "desktop-id"), {"client_id":"desktop-id", "client_secret":"desktop-secret"})
            self.assertNotIn("token_uri", target.read_text())
            before = target.read_bytes()
            for document in ({"web":valid["installed"]}, {"installed":{"client_id":"wrong", "client_secret":"wrong"}},
                             {"installed":{"client_id":"desktop-id"}}, [1,2]):
                source.write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    import_credentials(source, destination=target, expected_id="desktop-id")
                self.assertEqual(target.read_bytes(), before)

    def test_access_log_filter_omits_google_codes_and_tickets(self):
        from local_app_server import PrivateAccessLog
        record = logging.LogRecord("uvicorn.access", logging.INFO, "", 1, '%s - "%s %s HTTP/%s" %d',
                                   ("127.0.0.1", "GET", "/identity/google/callback?code=secret&state=private", "1.1", 302), None)
        PrivateAccessLog().filter(record)
        self.assertNotIn("secret", record.getMessage())
        self.assertNotIn("private", record.getMessage())
        self.assertIn("/identity/google/callback", record.getMessage())

    def test_upgrade_uses_current_google_client_without_changing_local_credentials(self):
        from desktop_setup import auth_settings
        from local_config import LocalConfig
        with tempfile.TemporaryDirectory() as directory:
            auth = Path(directory)/"settings.json"
            google = Path(directory)/"google.json"
            values = {"google_client_id":"previous-google-id", "google_client_secret":"previous-google-secret",
                      "client_id":"local-client", "client_secret":"local-secret", "cookie_secret":"local-cookie",
                      "installation_id":"same-installation"}
            auth.write_text(json.dumps(values))
            before = auth.read_bytes()
            google.write_text(json.dumps({"installed":{"client_id":"previous-google-id", "client_secret":"old-secret"}}))
            with patch("desktop_setup.AUTH_PATH", auth), patch("desktop_google.CLIENT_FILE", google), \
                    patch("desktop_google.expected_client_id", return_value="current-google-id"):
                result = auth_settings(LocalConfig("skopos.test.localhost"))
                self.assertEqual(result["google_client_id"], "current-google-id")
                self.assertNotIn("google_client_secret", result)
                self.assertTrue(result["google_config_error"])
                google.write_text(json.dumps({"installed":{"client_id":"current-google-id", "client_secret":"new-secret"}}))
                result = auth_settings(LocalConfig("skopos.test.localhost"))
                self.assertEqual(result["google_client_secret"], "new-secret")
                for field in ("client_id", "client_secret", "cookie_secret", "installation_id"):
                    self.assertEqual(result[field], values[field])
                self.assertEqual(auth.read_bytes(), before)

    def test_bundled_google_is_installed_automatically_and_preserves_matching_import(self):
        from desktop_google import install_bundled_credentials
        with tempfile.TemporaryDirectory() as directory:
            seed, client = Path(directory)/"seed.json", Path(directory)/"private/google.json"
            seed.write_text(json.dumps({"installed":{"client_id":"current", "client_secret":"bundled"}}))
            with patch("desktop_google.BUNDLED_CLIENT_FILE", seed), patch("desktop_google.CLIENT_FILE", client), \
                    patch("desktop_google.expected_client_id", return_value="current"):
                self.assertTrue(install_bundled_credentials())
                self.assertEqual(parse_credentials(client, "current")["client_secret"], "bundled")
                client.write_text(json.dumps({"installed":{"client_id":"current", "client_secret":"custom"}}))
                self.assertFalse(install_bundled_credentials())
                self.assertEqual(parse_credentials(client, "current")["client_secret"], "custom")
                client.write_text(json.dumps({"installed":{"client_id":"previous", "client_secret":"old"}}))
                self.assertTrue(install_bundled_credentials())
                self.assertEqual(parse_credentials(client, "current")["client_secret"], "bundled")
                backups=list(client.parent.glob("google-client-previous-*.json"))
                self.assertEqual(len(backups), 1)
                self.assertEqual(json.loads(backups[0].read_text())["installed"]["client_id"], "previous")


if __name__ == "__main__":
    unittest.main()
