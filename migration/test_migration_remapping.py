import pytest
from migration.v1_to_v2_migration import (
    remap_connection_ids_in_tool,
    v1_assistant_to_v2_agent,
)
import migration.v1_to_v2_migration as migration_module


@pytest.fixture(autouse=True)
def setup_arm_prefix():
    original_prefix = migration_module.TARGET_PROJECT_ARM_PREFIX
    migration_module.TARGET_PROJECT_ARM_PREFIX = (
        "/subscriptions/00000000-0000-0000-0000-000000000000"
        "/resourceGroups/my-rg-v2/providers/Microsoft.CognitiveServices"
        "/accounts/my-foundry/projects/my-project"
    )
    yield
    migration_module.TARGET_PROJECT_ARM_PREFIX = original_prefix


def test_remap_connection_id():
    """Verify standard 'connection_id' is renamed to 'project_connection_id' and resolved."""
    input_config = {
        "connection_id": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.MachineLearningServices/workspaces/ws/connections/conn1"
    }
    remapped = remap_connection_ids_in_tool(input_config)
    assert "project_connection_id" in remapped
    assert "connection_id" not in remapped
    assert remapped["project_connection_id"].endswith("/connections/conn1")


def test_remap_index_connection_id_azure_ai_search():
    """Verify 'index_connection_id' for Azure AI Search tools is renamed to 'project_connection_id'."""
    search_config = {
        "indexes": [
            {
                "index_connection_id": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.MachineLearningServices/workspaces/ws/connections/search-service-conn",
                "index_name": "products-catalog",
            }
        ]
    }
    remapped = remap_connection_ids_in_tool(search_config)
    assert "indexes" in remapped
    index_entry = remapped["indexes"][0]
    assert "project_connection_id" in index_entry
    assert "index_connection_id" not in index_entry
    assert index_entry["index_name"] == "products-catalog"
    assert index_entry["project_connection_id"].endswith(
        "/connections/search-service-conn"
    )


def test_v1_assistant_to_v2_agent_with_azure_ai_search_tool():
    """Verify end-to-end transformation of v1 assistant containing azure_ai_search tool."""
    v1_assistant = {
        "id": "asst_search_01",
        "name": "SearchAssistant",
        "model": "gpt-4o",
        "instructions": "Search documentation.",
        "tools": [
            {
                "type": "azure_ai_search",
                "azure_ai_search": {
                    "indexes": [
                        {
                            "index_connection_id": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.MachineLearningServices/workspaces/ws/connections/my-search",
                            "index_name": "docs-index",
                        }
                    ]
                },
            }
        ],
        "tool_resources": {},
    }

    v2_result = v1_assistant_to_v2_agent(v1_assistant)
    tools = v2_result["v2_agent_version"]["definition"]["tools"]

    assert len(tools) == 1
    search_tool = tools[0]
    assert search_tool["type"] == "azure_ai_search"
    indexes = search_tool.get("azure_ai_search", {}).get("indexes", [])
    assert len(indexes) == 1
    assert "project_connection_id" in indexes[0]
    assert "index_connection_id" not in indexes[0]
    assert indexes[0]["project_connection_id"].endswith("/connections/my-search")
