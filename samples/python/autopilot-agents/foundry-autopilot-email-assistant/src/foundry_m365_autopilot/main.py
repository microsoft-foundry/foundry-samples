# Copyright (c) Microsoft. All rights reserved.

"""Entry point — starts the generic host with :class:`FoundryDigitalWorkerAgent`.

Equivalent of ``Program.cs`` in the original C# sample.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from .agent import FoundryDigitalWorkerAgent
    from .host_agent_server import create_and_run_host
else:
    # azd's Python project detection starts this file directly from the package
    # directory. Add the package parent so package-relative imports still work.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from foundry_m365_autopilot.agent import FoundryDigitalWorkerAgent
    from foundry_m365_autopilot.host_agent_server import create_and_run_host


def main() -> int:
    try:
        print("Starting Foundry A365 Agent Host with FoundryDigitalWorkerAgent...")
        create_and_run_host(FoundryDigitalWorkerAgent)
    except Exception as ex:
        print(f"❌ Failed to start server: {ex}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
