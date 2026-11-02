# Copyright (c) Microsoft. All rights reserved.

"""Single CE Hosted Agent containing the original Router and Worker."""

import logging
import os

from voice_runtime import create_app


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    create_app().run()


if __name__ == "__main__":
    main()
