"""Standalone script to create / initialize (or delete) the OpenAI Computer Tool Prompt Agent in Microsoft Foundry.

Usage (from `src/openai-computer-tool/`):
    python create_agent.py           # Create / initialize the Prompt Agent version in Microsoft Foundry
    python create_agent.py --delete  # Delete all versions of the Prompt Agent
"""

import argparse

from utils import delete_agent, provision_agent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or delete the OpenAI Computer Tool Prompt Agent in Microsoft Foundry."
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete all versions of the Prompt Agent instead of creating a new version.",
    )
    args = parser.parse_args()

    if args.delete:
        delete_agent()
    else:
        provision_agent()


if __name__ == "__main__":
    main()
