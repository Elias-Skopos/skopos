"""An upgrade must keep private storage separate from replaceable binaries."""
from pathlib import Path
import tempfile
import unittest

from local_paths import data_root, postgres_runtime


class LocalPathsTests(unittest.TestCase):
    def test_development_layout_does_not_switch_the_existing_database(self):
        app = Path(__file__).resolve().parents[1]
        self.assertEqual(data_root({}, app), app)
        self.assertEqual(postgres_runtime({}, app), app / ".local_postgres/runtime/pgsql")

    def test_installed_code_and_private_data_can_be_in_different_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app, data, runtime = root / "Programa", root / "Dados com acentos ç", root / "Programa/runtime/pgsql"
            environment = {"SKOPOS_DATA_DIR": str(data), "SKOPOS_POSTGRES_RUNTIME": str(runtime)}
            self.assertEqual(data_root(environment, app), data.resolve())
            self.assertEqual(postgres_runtime(environment, app), runtime.resolve())
            self.assertFalse(data.exists(), "Reading the configuration must not initialize storage")

    def test_relative_paths_are_rejected_instead_of_silently_creating_another_database(self):
        with self.assertRaises(ValueError):
            data_root({"SKOPOS_DATA_DIR": "dados"})
        with self.assertRaises(ValueError):
            postgres_runtime({"SKOPOS_POSTGRES_RUNTIME": "runtime/pgsql"})


if __name__ == "__main__":
    unittest.main()
