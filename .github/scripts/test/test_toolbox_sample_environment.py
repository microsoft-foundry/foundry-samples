"""Regression coverage for local and deployed Toolbox sample configuration."""

from io import StringIO
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from dotenv import dotenv_values, load_dotenv
import yaml


SAMPLE_ROOT = (
    Path(__file__).resolve().parents[3] / "samples" / "python" / "hosted-agents"
)
SAMPLES = (
    ("agent-framework/responses/04-foundry-toolbox", "agent-tools"),
    ("bring-your-own/invocations/toolbox", "my-toolbox"),
    ("bring-your-own/responses/bring-your-own-toolbox", "my-toolbox"),
)


class ToolboxSampleEnvironmentTests(unittest.TestCase):
    def test_one_endpoint_supports_local_and_deployed_agents(self):
        for sample_path, toolbox_name in SAMPLES:
            with self.subTest(sample=sample_path):
                sample_root = SAMPLE_ROOT / sample_path
                manifest = yaml.safe_load(
                    (sample_root / "azure.yaml").read_text(encoding="utf-8")
                )
                agent = next(
                    service
                    for service in manifest["services"].values()
                    if service["host"] == "azure.ai.agent"
                )
                deployment_key = (
                    f"TOOLBOX_{toolbox_name.upper().replace('-', '_')}_MCP_ENDPOINT"
                )
                self.assertIn(toolbox_name, agent["uses"])
                self.assertEqual(
                    "${" + deployment_key + "}", agent["env"]["TOOLBOX_ENDPOINT"]
                )
                template = (sample_root / agent["project"] / ".env.example").read_text(
                    encoding="utf-8"
                )
                self.assertIn(
                    deployment_key,
                    dotenv_values(stream=StringIO(template), interpolate=False),
                )
                endpoint = (
                    "https://example.test/api/projects/project"
                    f"/toolboxes/{toolbox_name}/versions/1/mcp?api-version=v1"
                )
                configured = "\n".join(
                    f'{deployment_key}="{endpoint}"'
                    if line.partition("=")[0].strip() == deployment_key
                    else line
                    for line in template.splitlines()
                )

                with patch.dict(os.environ, {}, clear=True):
                    raw_values = dotenv_values(
                        stream=StringIO(configured), interpolate=False
                    )
                    self.assertEqual(endpoint, raw_values[deployment_key])
                    load_dotenv(stream=StringIO(configured), override=False)
                    self.assertEqual(endpoint, os.environ["TOOLBOX_ENDPOINT"])

                hosted_endpoint = endpoint.replace("/versions/1/", "/versions/2/")
                with patch.dict(
                    os.environ, {"TOOLBOX_ENDPOINT": hosted_endpoint}, clear=True
                ):
                    load_dotenv(stream=StringIO(configured), override=False)
                    self.assertEqual(hosted_endpoint, os.environ["TOOLBOX_ENDPOINT"])


if __name__ == "__main__":
    unittest.main()
