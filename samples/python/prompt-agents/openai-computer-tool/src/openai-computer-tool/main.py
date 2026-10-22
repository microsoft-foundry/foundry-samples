"""CLI entrypoint for the Azure AI Foundry OpenAI Computer Tool Prompt Agent sample.

Usage (from `src/openai-computer-tool/`):
    python main.py provision                  # Provision the Prompt Agent version in Azure AI Foundry
    python main.py run --scenario calculator  # Run the Calculator + Notepad desktop scenario (default)
    python main.py run --scenario paint       # Run the MS Paint colored smiley face scenario
    python main.py delete                     # Delete all versions of the Prompt Agent
"""

import argparse

from scenarios import run_calculator_scenario, run_paint_scenario
from utils import delete_agent, provision_agent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision and invoke the Azure AI Foundry OpenAI Computer Tool Prompt Agent."
    )
    parser.add_argument(
        "--scenario",
        choices=["calculator", "paint"],
        default="calculator",
        help="Desktop scenario to execute when running `python main.py` directly (default: calculator).",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Optional custom task prompt sent to the Prompt Agent.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("provision", help="Provision the Prompt Agent in Azure AI Foundry")

    run_parser = subparsers.add_parser("run", help="Run a desktop automation scenario")
    run_parser.add_argument(
        "--scenario",
        choices=["calculator", "paint"],
        default="calculator",
        help="Desktop scenario to execute (calculator or paint).",
    )
    run_parser.add_argument(
        "--prompt",
        default=None,
        help="Optional custom task prompt sent to the Prompt Agent.",
    )

    subparsers.add_parser("delete", help="Delete all versions of the Prompt Agent")

    args = parser.parse_args()

    if args.command == "provision":
        provision_agent()
    elif args.command == "delete":
        delete_agent()
    else:
        if args.scenario == "paint":
            run_paint_scenario(prompt=args.prompt)
        else:
            run_calculator_scenario(prompt=args.prompt)


if __name__ == "__main__":
    main()
