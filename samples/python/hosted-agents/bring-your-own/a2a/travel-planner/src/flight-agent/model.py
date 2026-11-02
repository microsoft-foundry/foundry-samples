# Copyright (c) Microsoft. All rights reserved.
"""Authenticated Foundry model transport, packaged independently by each agent."""

import json
import logging
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx2 as httpx
from azure.ai.agentserver.core import get_request_context
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from opentelemetry import propagate, trace

TRACER = trace.get_tracer("a2a.travel.model")
logger = logging.getLogger("a2a.travel.model")


class ModelClient:
    def __init__(self, project: str, model: str) -> None:
        self.project = project.rstrip("/")
        parsed = urlsplit(self.project)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"/api/projects/[A-Za-z0-9_-]+", parsed.path)
        ):
            raise ValueError(
                "Use an HTTPS Foundry project endpoint without credentials or query"
            )
        if not model:
            raise ValueError("Specify an existing model deployment")
        self.model = model
        self.credential = DefaultAzureCredential(process_timeout=60)
        self.token_provider = get_bearer_token_provider(
            self.credential, "https://ai.azure.com/.default"
        )
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(180, connect=15))

    async def close(self) -> None:
        await self.http.aclose()
        await self.credential.close()

    async def headers(self) -> dict[str, str]:
        headers = {"Authorization": "Bearer " + await self.token_provider()}
        propagate.inject(headers)
        headers.update(get_request_context().platform_headers())
        return headers

    async def model_response(self, request: dict[str, Any]) -> dict[str, Any]:
        with TRACER.start_as_current_span("travel.model"):
            response = await self.http.post(
                self.project + "/openai/v1/responses",
                headers=await self.headers(),
                json={
                    "model": self.model,
                    "reasoning": {"effort": "minimal"},
                    "max_output_tokens": 3200,
                    "store": False,
                    **request,
                },
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get("status") != "completed":
                raise RuntimeError("Model response did not complete")
            if not isinstance(result.get("output"), list):
                raise TypeError("Model response is missing output")
            if not isinstance(result.get("id"), str) or not result["id"]:
                raise RuntimeError("Model response is missing its response ID")
            return result

    async def verified_response(
        self, request: dict[str, Any], validate: Callable[[dict], dict]
    ) -> tuple[dict, str, int]:
        for attempt in range(1, 3):
            response = await self.model_response(request)
            texts = [
                part["text"]
                for item in response["output"]
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
                and isinstance(part.get("text"), str)
            ]
            if len(texts) != 1:
                raise RuntimeError(
                    "Specialist model did not return one structured answer"
                )
            answer = json.loads(texts[0])
            if not isinstance(answer, dict):
                raise TypeError("Specialist model answer must be an object")
            try:
                result = validate(answer)
            except ValueError as error:
                logger.warning(
                    "SPECIALIST_MODEL_REJECTED response_id=%s attempt=%s reason=%s",
                    response["id"],
                    attempt,
                    error,
                )
                if attempt == 2:
                    raise
                # Ask the model to recalculate; do not supply code-computed answers.
                request = {
                    **request,
                    "input": request["input"]
                    + "\nPrevious answer rejected: "
                    + json.dumps(answer)
                    + "\nValidation error: "
                    + str(error)
                    + "\nRe-evaluate every filter and recalculate integer cents from the raw inventory. "
                    "Return a corrected complete answer, not the rejected values.",
                }
            else:
                return result, response["id"], attempt
        raise RuntimeError("Specialist calculation attempts exhausted")
