import unittest
from unittest.mock import Mock, call
from azure.core.exceptions import ResourceNotFoundError
from azure.ai.projects.models import (
    AgentDetails,
    AgentEndpointConfig,
    AgentVersionDetails,
    PromptAgentDefinition,
)

from util import create_version_with_endpoint


class EndpointOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.project = Mock()
        self.created = AgentVersionDetails(name="sample-agent", version="2")
        self.project.agents.create_version.return_value = self.created
        self.definition = PromptAgentDefinition(model="test-deployment")

    def test_existing_endpoint_is_snapshotted_before_creation_and_restored_on_error(
        self,
    ):
        original = AgentEndpointConfig()
        self.project.agents.get.return_value = AgentDetails(agent_endpoint=original)
        with self.assertRaisesRegex(RuntimeError, "invocation failed"):
            with create_version_with_endpoint(
                self.project, "sample-agent", definition=self.definition
            ):
                raise RuntimeError("invocation failed")
        self.assertEqual(
            self.project.agents.mock_calls[0], call.get(agent_name="sample-agent")
        )
        self.assertEqual(
            self.project.agents.update_details.call_args,
            call(agent_name="sample-agent", agent_endpoint=original),
        )
        self.project.agents.delete_version.assert_called_once_with(
            agent_name="sample-agent", agent_version="2", force=True
        )
        self.project.agents.delete.assert_not_called()

    def test_new_agent_is_removed_without_deleting_an_existing_agent(self):
        self.project.agents.get.side_effect = ResourceNotFoundError("test fixture")
        with create_version_with_endpoint(
            self.project, "sample-agent", definition=self.definition
        ) as created:
            self.assertIs(created, self.created)
        self.project.agents.delete.assert_called_once_with(
            agent_name="sample-agent", force=True
        )

    def test_existing_unconfigured_agent_is_not_modified(self):
        self.project.agents.get.return_value = AgentDetails(agent_endpoint=None)
        with self.assertRaisesRegex(ValueError, "safely restore"):
            with create_version_with_endpoint(
                self.project, "sample-agent", definition=self.definition
            ):
                self.fail("An unconfigured existing agent must not be modified.")
        self.project.agents.create_version.assert_not_called()
        self.project.agents.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
