"""Desktop lifetime and the limited bridge must not launch extra browsers."""
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from desktop_window import DesktopAPI, startup_html
from local_config import LocalConfig


class DesktopWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".runtime").mkdir()
        self.stop = threading.Event()
        self.api = DesktopAPI(self.root, self.stop)
        self.window = self.api._window = Mock()

    def test_ready_loads_the_app_inside_the_window(self):
        config = LocalConfig("skopos.test.localhost", 8509)
        self.api._ready(config, "test-token")
        self.window.load_url.assert_called_once_with(config.url)
        self.assertTrue((self.root / ".runtime/running.json").exists())

    def test_closing_during_setup_does_not_start_server(self):
        def setup(_):
            self.stop.set()
            return LocalConfig()
        with patch("desktop_setup.setup", side_effect=setup), patch("local_launcher.launch") as launch:
            self.api._run("Test")
        launch.assert_not_called()
        self.window.load_url.assert_not_called()

    def test_desktop_launch_owns_server_and_suppresses_browser(self):
        with patch("desktop_setup.setup", return_value=LocalConfig()), \
                patch("local_launcher.launch", side_effect=lambda *a, **kw: self.stop.set()) as launch:
            self.api._run("Test")
        self.assertFalse(launch.call_args.kwargs["open_browser"])
        self.assertIs(launch.call_args.kwargs["stop_event"], self.stop)

    def test_bridge_cannot_prepare_installation_from_a_web_page(self):
        self.window.get_current_url.return_value = "https://example.invalid"
        self.assertFalse(self.api.begin("Test"))
        self.assertIsNone(self.api._thread)

    def test_google_bridge_only_opens_google_from_local_login(self):
        self.api._home = "http://skopos.test.localhost:8509"
        self.window.get_current_url.return_value = self.api._home + "/identity/google/start"
        with patch("desktop_window.webbrowser.open", return_value=True) as browser:
            for url in ("file:///private", "https://accounts.google.com.evil.invalid/o/oauth2/v2/auth",
                        "https://example.invalid", "https://accounts.google.com/other"):
                self.assertFalse(self.api.open_google(url))
            browser.assert_not_called()
            self.assertTrue(self.api.open_google("https://accounts.google.com/o/oauth2/v2/auth?state=test"))
            self.window.get_current_url.return_value = "https://example.invalid/identity/google/start"
            self.assertFalse(self.api.open_google("https://accounts.google.com/o/oauth2/v2/auth"))
            self.assertEqual(browser.call_count, 1)

    def test_diagnostic_text_is_escaped_in_startup_page(self):
        self.assertIn("&lt;script&gt;", startup_html(False, "<script>private</script>"))


if __name__ == "__main__":
    unittest.main()
