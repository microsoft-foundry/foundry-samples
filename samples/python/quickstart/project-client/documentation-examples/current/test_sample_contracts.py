"""Check compilation, safe imports, and declared SDK imports without Azure requests."""

import ast
import importlib
import importlib.util
from pathlib import Path
import unittest


class SampleContracts(unittest.TestCase):
    def test_examples_compile_and_import_without_configuration(self):
        for path in Path(__file__).parent.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            with self.subTest(file=path.name):
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
                spec = importlib.util.spec_from_file_location(path.stem, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

    def test_declared_imports_exist(self):
        for path in Path(__file__).parent.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    with self.subTest(file=path.name, module=node.module):
                        module = importlib.import_module(node.module)
                        for alias in node.names:
                            self.assertTrue(hasattr(module, alias.name), alias.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        with self.subTest(file=path.name, module=alias.name):
                            if (
                                alias.name == "pyaudio"
                                and importlib.util.find_spec("pyaudio") is None
                            ):
                                self.skipTest(
                                    "Optional microphone dependency: install requirements-audio.txt."
                                )
                            importlib.import_module(alias.name)

    def test_project_model_keywords_match_the_installed_sdk(self):
        for path in Path(__file__).parent.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            models = {}
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module == "azure.ai.projects.models"
                ):
                    module = importlib.import_module(node.module)
                    for alias in node.names:
                        models[alias.asname or alias.name] = getattr(module, alias.name)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(
                    node.func, ast.Name
                ):
                    continue
                model = models.get(node.func.id)
                if not isinstance(model, type):
                    continue
                allowed = set()
                for parent in model.__mro__:
                    allowed.update(getattr(parent, "__annotations__", {}))
                if allowed:
                    with self.subTest(file=path.name, model=node.func.id):
                        unknown = [
                            kw.arg
                            for kw in node.keywords
                            if kw.arg is not None and kw.arg not in allowed
                        ]
                        self.assertEqual(unknown, [])


if __name__ == "__main__":
    unittest.main()
