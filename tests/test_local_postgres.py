"""Local configuration must preserve login secrets and avoid leaking credentials."""
import tomllib
import unittest

from local_postgres import database_url, secrets_with_database


class LocalPostgresTests(unittest.TestCase):
    def test_inserts_database_without_changing_auth(self):
        original = '# Comentário\n[auth]\ncookie_secret = "local-secret"\n[auth.google]\nclient_id = "example"\n'
        url = "postgresql://app:fake-password@127.0.0.1:5432/skopos"
        content = secrets_with_database(original, url)
        result = tomllib.loads(content)
        self.assertEqual(result["auth"], tomllib.loads(original)["auth"])
        self.assertEqual(result["database"]["url"], url)
        self.assertIn("# Comentário", content)
        self.assertEqual(secrets_with_database(content, url), content)

    def test_updates_an_empty_section_preserving_subsequent_sections(self):
        source = '[database]\nurl = ""\n[auth]\ncookie_secret = "example"\n'
        result = tomllib.loads(secrets_with_database(source, "postgresql://local/example"))
        self.assertEqual(result["database"]["url"], "postgresql://local/example")
        self.assertEqual(result["auth"]["cookie_secret"], "example")

    def test_refuses_to_replace_another_connection(self):
        with self.assertRaises(ValueError):
            secrets_with_database('[database]\nurl = "postgresql://other/example"\n', "postgresql://local/example")

    def test_private_url_encodes_password_and_uses_dedicated_test_database(self):
        settings = {"app_user": "app", "app_password": "fake:@/?#", "port": 5432}
        url = database_url(settings)
        self.assertIn("fake%3A%40%2F%3F%23@127.0.0.1:5432/skopos", url)
        self.assertIn("/skopos_test?", database_url(settings, test=True))


if __name__ == "__main__":
    unittest.main()
