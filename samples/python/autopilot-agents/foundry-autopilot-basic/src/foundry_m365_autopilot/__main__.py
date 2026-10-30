# Copyright (c) Microsoft. All rights reserved.

"""Allow running the package as ``python -m foundry_m365_autopilot``."""

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
