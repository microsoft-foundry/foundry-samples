# Copyright (c) Microsoft. All rights reserved.

"""Local echo backend for testing the legacy Voice Live Bridge path."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from state import ModelMessage


class EchoClient:
    """Use the existing streaming contract without a model or network client."""

    model_name = "echo"
    server_address = "localhost"

    async def complete(self, messages: Sequence[ModelMessage]) -> AsyncIterator[str]:
        text = messages[-1].content
        for index in range(0, len(text), 40):
            await asyncio.sleep(0)
            yield text[index : index + 40]

    async def close(self) -> None:
        """No external resources are owned by this backend."""
