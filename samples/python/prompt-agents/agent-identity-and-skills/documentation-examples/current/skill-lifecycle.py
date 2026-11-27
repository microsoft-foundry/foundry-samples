# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_104():
    # <doc_skills_attach_skills_to_a_toolbox_preview>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=endpoint,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        from azure.ai.projects.models import ToolboxSkillReference

        toolbox_version = project.toolboxes.create_version(
            name="my-toolbox",
            description="Toolbox with a skill reference",
            tools=[],
            skills=[ToolboxSkillReference(name="greeting")],
        )
        print(f"Created toolbox version: {toolbox_version.version}")
    # </doc_skills_attach_skills_to_a_toolbox_preview>


def example_105():
    # <doc_skills_option_1_create_from_inline_content_json>
    import os
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import SkillInlineContent

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project,
    ):
        created = project.beta.skills.create(
            name="greeting",
            inline_content=SkillInlineContent(
                description="Generate a personalized greeting for the user.",
                instructions="You are a friendly greeting assistant. Keep greetings brief and warm.",
            ),
        )
        print(f"Created skill: {created.name} version: {created.version}")
    # </doc_skills_option_1_create_from_inline_content_json>


def example_106():
    # <doc_skills_option_2_create_from_a_skill_md_zip>
    import os
    from pathlib import Path
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import CreateSkillVersionFromFilesBody

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project,
    ):
        skill_zip_path = Path(os.environ["FOUNDRY_SKILL_ZIP_PATH"])
        imported = project.beta.skills.create_from_files(
            "greeting",
            content=CreateSkillVersionFromFilesBody(
                files=[(skill_zip_path.name, skill_zip_path.read_bytes())]
            ),
        )
        print(f"Created skill: {imported.name} version: {imported.version}")
    # </doc_skills_option_2_create_from_a_skill_md_zip>


def example_107():
    # <doc_skills_list_skills>
    import os
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project,
    ):
        skills = list(project.beta.skills.list())
        print(f"Found {len(skills)} skill(s)")
        for skill in skills:
            print(f"  {skill.name} (default: {skill.default_version})")
    # </doc_skills_list_skills>


def example_108():
    # <doc_skills_get_a_skill>
    import os
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project,
    ):
        skill = project.beta.skills.get(name="greeting")
        print(f"{skill.name}: default version {skill.default_version}")
    # </doc_skills_get_a_skill>


def example_109():
    # <doc_skills_download_skill_content>
    import os
    import tempfile
    from datetime import datetime
    from pathlib import Path
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    download_folder = Path(tempfile.gettempdir()).resolve()
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project,
    ):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_path = download_folder / f"greeting_{timestamp}.zip"
        download_path.write_bytes(b"".join(project.beta.skills.download("greeting")))
        print(f"Downloaded skill package to: {download_path}")
    # </doc_skills_download_skill_content>


def example_110():
    # <doc_skills_delete_a_skill>
    import os
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project,
    ):
        deleted = project.beta.skills.delete(name="greeting")
        print(f"Deleted skill: {deleted}")
    # </doc_skills_delete_a_skill>


def main():
    examples = {
        "aip-python-104": example_104,
        "aip-python-105": example_105,
        "aip-python-106": example_106,
        "aip-python-107": example_107,
        "aip-python-108": example_108,
        "aip-python-109": example_109,
        "aip-python-110": example_110,
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-104")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
