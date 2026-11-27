import asyncio
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


def load_entry_point():
    path = Path(__file__).with_name("minimal-responses.py")
    spec = importlib.util.spec_from_file_location("minimal_responses", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load the minimal entry point: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BlockingCredential:
    def __init__(self):
        self.requests = 0
        self.closed = False

    def get_token(self, *args, **kwargs):
        self.requests += 1
        raise AssertionError("Offline tests must not request credentials.")

    def close(self):
        self.closed = True


class MinimalHostTests(unittest.TestCase):
    def test_import_does_not_require_configuration_or_start_a_host(self):
        with patch.dict(os.environ, {}, clear=True):
            module = load_entry_point()
        self.assertTrue(callable(module.main))

    def test_model_factory_does_not_request_or_close_the_callers_credential(self):
        credential = BlockingCredential()
        with patch.dict(
            os.environ,
            {
                "FOUNDRY_PROJECT_ENDPOINT": "https://project.example.invalid/api/projects/example",
                "FOUNDRY_MODEL_NAME": "test-deployment",
            },
        ):
            model = load_entry_point().build_chat_model(credential)
        try:
            self.assertEqual(credential.requests, 0)
            self.assertFalse(credential.closed)
            self.assertEqual(model.model_name, "test-deployment")
        finally:
            if model.root_client is not None:
                model.root_client.close()
            if model.root_async_client is not None:
                asyncio.run(model.root_async_client.close())


if __name__ == "__main__":
    unittest.main()
