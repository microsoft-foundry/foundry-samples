"""Verify the supported raw-body interface; no service or model is invoked."""

import json
import time
import unittest
from urllib.parse import urlparse

from azure.core.credentials import AccessToken
from azure.core.pipeline.transport import HttpResponse, HttpTransport
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    BrowserAutomationToolConnectionParameters,
    BrowserAutomationToolParameters,
)


class LocalCredential:
    def get_token(self, *args, **kwargs):
        return AccessToken("local-test-token", int(time.time()) + 3600)


class LocalResponse(HttpResponse):
    def __init__(self, request):
        super().__init__(request, None)
        self.status_code = 200
        self.headers = {"content-type": "application/json"}
        self.reason = "OK"

    def body(self):
        return b'{"name":"test-toolbox","version":"1","tools":[]}'

    def text(self, encoding=None):
        return self.body().decode(encoding or "utf-8")

    def json(self):
        return json.loads(self.body())


class CaptureTransport(HttpTransport):
    def __init__(self):
        self.payload = None
        self.is_open = False

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()

    def send(self, request, **kwargs):
        if urlparse(request.url).hostname != "project.example.invalid":
            raise AssertionError("Only a reserved offline test endpoint is permitted.")
        self.payload = json.loads(request.body)
        return LocalResponse(request)


class BrowserToolboxWireTests(unittest.TestCase):
    def test_browser_payload_is_preserved_by_the_framework_compatible_sdk(self):
        transport = CaptureTransport()
        parameters = BrowserAutomationToolParameters(
            connection=BrowserAutomationToolConnectionParameters(
                project_connection_id="test-connection"
            )
        )
        with AIProjectClient(
            endpoint="https://project.example.invalid/api/projects/example",
            credential=LocalCredential(),
            transport=transport,
        ) as project:
            project.toolboxes.create_version(
                name="test-toolbox",
                body={
                    "tools": [
                        {
                            "type": "browser_automation",
                            "browser_automation": parameters.as_dict(),
                        }
                    ]
                },
            )
        self.assertEqual(
            transport.payload["tools"],
            [
                {
                    "type": "browser_automation",
                    "browser_automation": {
                        "connection": {"project_connection_id": "test-connection"}
                    },
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
