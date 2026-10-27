import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("railway_start", ROOT / "backend/railway_start.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RailwayConfigurationTests(unittest.TestCase):
    def test_deployment_configuration(self):
        config = json.loads((ROOT / "backend/railway.json").read_text())
        self.assertEqual(config["deploy"]["startCommand"], "python railway_start.py")
        self.assertEqual(config["deploy"]["healthcheckPath"], "/api/health")

    def test_runtime_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "RAILWAY_VOLUME_MOUNT_PATH": directory,
                "MIA_DATABASE_PATH": str(Path(directory) / "invitations.sqlite3"),
                "MIA_ADMIN_API_KEY": "not-a-real-key",
                "MIA_LINK_ENCRYPTION_KEY": "not-a-real-key",
                "PORT": "8080",
            }
            self.assertEqual(runtime.validate_runtime(env), 8080)
            for patch in (
                {"RAILWAY_VOLUME_MOUNT_PATH": ""},
                {"MIA_DATABASE_PATH": str(Path(directory).parent / "outside.sqlite3")},
                {"MIA_DATABASE_PATH": directory},
                {"MIA_DATABASE_PATH": "relative.sqlite3"},
                {"MIA_ADMIN_API_KEY": ""},
                {"MIA_LINK_ENCRYPTION_KEY": ""},
                {"MIA_ENABLE_DOCS": "true"},
                {"PORT": "65536"},
            ):
                with self.subTest(patch=tuple(patch)), self.assertRaises(ValueError):
                    runtime.validate_runtime(env | patch)


if __name__ == "__main__":
    unittest.main()
