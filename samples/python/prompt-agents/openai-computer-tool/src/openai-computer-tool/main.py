"""CLI entrypoint to invoke the provisioned OpenAI Computer Tool Prompt Agent on the local desktop.

First create/initialize the Prompt Agent once using `create_agent.py`:
    python create_agent.py

Then run the desktop scenario with `main.py`:
    python main.py
    python main.py --prompt "Open Windows Search, launch MS Paint, and draw a blue star."
"""

import argparse

from scenarios import run_paint_scenario


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Invoke the provisioned Azure AI Foundry OpenAI Computer Tool Prompt Agent."
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Optional custom task prompt sent to the Prompt Agent.",
    )
    args = parser.parse_args()
    run_paint_scenario(prompt=args.prompt)


if __name__ == "__main__":
    main()
