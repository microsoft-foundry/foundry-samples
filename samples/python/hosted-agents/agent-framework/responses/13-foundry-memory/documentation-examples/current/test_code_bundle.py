import tempfile
from pathlib import Path
import unittest
import zipfile

from code_bundle import create_code_zip


class CodeBundleTests(unittest.TestCase):
    def test_bundle_includes_only_reviewed_runtime_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("main.py", "pyproject.toml", "uv.lock", ".env", "private.py"):
                (root / name).write_text("test fixture", encoding="utf-8")
            archive = create_code_zip(root)
            try:
                with zipfile.ZipFile(archive) as bundle:
                    self.assertEqual(
                        set(bundle.namelist()), {"main.py", "pyproject.toml", "uv.lock"}
                    )
            finally:
                archive.unlink()

    def test_missing_lock_fails_before_creating_a_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "main.py").write_text("test fixture", encoding="utf-8")
            (root / "pyproject.toml").write_text("test fixture", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "uv.lock"):
                create_code_zip(root)

    def test_directory_cannot_replace_a_runtime_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "main.py").mkdir()
            with self.assertRaisesRegex(ValueError, "main.py"):
                create_code_zip(root)


if __name__ == "__main__":
    unittest.main()
