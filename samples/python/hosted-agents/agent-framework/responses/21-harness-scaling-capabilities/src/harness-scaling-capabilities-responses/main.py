# Copyright (c) Microsoft. All rights reserved.

"""Scaling its capabilities (Post 3) — hosted through the Foundry Responses protocol.

Ported from ``claw_step03_scaling_capabilities.py`` in the Microsoft Agent Framework. The original
runs the personal-finance harness agent in an interactive console; this project keeps the same
instructions, tools, skills, background agent, confined shell, and CodeAct provider while replacing
the console host with the native Foundry ``ResponsesHostServer``.

It preserves Post 3's four "scaling" capabilities:

1. Skills        — file-based finance skills (valuation, risk-scoring) under ``skills/``, loaded on
                   demand. Optionally folds in centrally-managed Foundry skills from a Foundry Toolbox
                   MCP endpoint (opt-in via FOUNDRY_TOOLBOX_MCP_SERVER_URL).
2. Shell         — a sandboxed shell confined to the trade-confirmation vault, used to reorganize the
                   accumulated confirmation files. Guarded by a deny-list policy and a confined
                   working directory.
3. CodeAct       — the agent writes and runs Python to crunch portfolio numbers, using the pure,
                   cross-platform Monty interpreter.
4. Background agents — fan out a per-ticker research sub-agent so several tickers are researched
                   concurrently, then aggregated.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT        — Microsoft Foundry project endpoint URL (auto-injected when hosted)
    AZURE_AI_MODEL_DEPLOYMENT_NAME  — Model deployment name
    FOUNDRY_TOOLBOX_MCP_SERVER_URL  — (optional) Foundry Toolbox MCP endpoint URL; enables Foundry skills

Authentication:
    Run ``az login`` before running locally. Hosted containers use managed identity.
"""

import asyncio
import logging
import os
import shutil
import uuid
from collections.abc import Callable, Generator
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from agent_framework import (
    Agent,
    AgentModeProvider,
    AggregatingSkillsSource,
    DeduplicatingSkillsSource,
    FileSkillsSource,
    FileSystemAgentFileStore,
    InMemoryHistoryProvider,
    MCPSkillsSource,
    SkillsProvider,
    SkillsSource,
    create_harness_agent,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from agent_framework_monty import MontyCodeActProvider
from agent_framework_tools.shell import LocalShellTool, ShellPolicy
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import Field

from subprocess_script_runner import subprocess_script_runner

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_SAMPLE_DIR = Path(__file__).resolve().parent
_PACKAGED_WORKING_DIR = _SAMPLE_DIR / "working"
# Foundry maps HOME to durable storage for the hosted session.
_SESSION_HOME = Path(os.environ.get("HOME") or os.getcwd())
_WORKING_DIR = _SESSION_HOME / "working"
_FILE_MEMORY_DIR = _SESSION_HOME / "agent-file-memory"
_VAULT_DIR = _WORKING_DIR / "confirmations"
_SKILLS_DIR = _SAMPLE_DIR / "skills"

# The Responses host owns conversation history across turns, but harness loops (planning, tool
# iterations, compaction) still need current-run persistence. These limits match the harness
# defaults the console host would have applied.
MAX_CONTEXT_WINDOW_TOKENS = 128_000
MAX_OUTPUT_TOKENS = 16_384


def _initialize_working_dir() -> None:
    """Seed the writable session workspace without overwriting persisted changes."""
    if _WORKING_DIR.is_dir():
        return
    if _WORKING_DIR.exists():
        raise NotADirectoryError(f"Working path is not a directory: {_WORKING_DIR}")

    shutil.copytree(_PACKAGED_WORKING_DIR, _WORKING_DIR)


FINANCE_INSTRUCTIONS = """\
## Personal Finance Assistant Instructions

You are a personal finance and investing assistant. You help the user understand their portfolio
and watchlist, value individual stocks, gauge portfolio risk, research the market, and keep their
records tidy.

### Working style

- The user's holdings live in a file called portfolio.csv. Read it with the file_access tools
  before answering questions about their portfolio, and never modify it unless asked.
- You have skills for valuation and risk-scoring. When a question matches a skill, load it and
  follow its instructions (read its references, run its scripts) rather than guessing.
- When asked to research several tickers, delegate each one to the background research agent so
  they run concurrently, then summarize the findings together.
- The user's trade confirmations accumulate in the confirmations folder. When asked to tidy or
  reorganize them, use the run_shell tool: inspect the folder first, then copy (do not move) the
  files into an organized/ subfolder using a year/month layout, renaming each copy to
  YYYY-MM-DD_TICKER_BUY|SELL.txt. Leave the original flat files untouched so the source data stays
  intact. If organized/ already exists from a previous run, clear it first so the result is clean.
  Explain your plan before running commands that change anything.
- To buy or sell, use the place_trade tool. This simulates a real action, so explain what you are
  about to do before running it.

### Important

You provide information and analysis only — you are not a licensed financial advisor and you must
not present your output as personalized investment advice. Remind the user to do their own
research before making decisions.
"""

# A tiny in-memory book of (price, trailing EPS) so the sample runs without any external dependency.
# These are illustrative mock values, not real market data.
_PRICE_BOOK: dict[str, tuple[float, float]] = {
    "MSFT": (462.97, 11.80),
    "AAPL": (229.35, 6.13),
    "GOOGL": (178.12, 7.54),
    "AMZN": (201.45, 4.18),
    "NVDA": (134.81, 2.95),
    "SPY": (612.40, 23.10),
}


def get_stock_price(
    symbol: Annotated[str, "The stock ticker symbol, e.g. MSFT or AAPL."],
) -> dict[str, object]:
    """Get the latest (delayed, illustrative) stock price and trailing EPS for a ticker symbol."""
    ticker = symbol.upper()
    data = _PRICE_BOOK.get(ticker)
    if data is None:
        # Deterministic pseudo-values for unknown symbols so the sample stays self-contained.
        # The built-in hash() is randomized per process (PYTHONHASHSEED), so derive a stable seed.
        seed = 0
        for ch in ticker:
            seed = (seed * 31 + ord(ch)) % 1_000_000
        price = 50.0 + (seed % 45000) / 100.0
        data = (price, round(price / 20.0, 2))

    return {
        "symbol": ticker,
        "price": round(data[0], 2),
        "trailing_eps": round(data[1], 2),
        "currency": "USD",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


@tool(approval_mode="always_require")
def place_trade(
    symbol: Annotated[str, "The stock ticker symbol to trade, e.g. MSFT."],
    action: Annotated[Literal["buy", "sell"], "Either 'buy' or 'sell'."],
    quantity: Annotated[int, Field(gt=0, description="The number of shares to trade.")],
) -> str:
    """Place a simulated buy or sell order. No real order is placed.

    ``action`` and ``quantity`` are validated by the framework (pydantic) from their type hints:
    the model can only pass 'buy'/'sell' and a quantity greater than zero.
    """
    verb = "Sold" if action == "sell" else "Bought"
    confirmation = f"TRADE-{uuid.uuid4().hex[:8].upper()}"
    return f"{verb} {quantity} share(s) of {symbol.upper()}. Confirmation: {confirmation}."


async def _build_skills_provider(stack: AsyncExitStack) -> SkillsProvider:
    """Build a skills provider over the local skills/ folder, plus optional Foundry-managed skills.

    File-based skills (valuation, risk-scoring) always load. When FOUNDRY_TOOLBOX_MCP_SERVER_URL is
    set we also connect to a Foundry Toolbox MCP endpoint and surface its skills, so they can be
    managed and updated centrally without changing this agent.
    """
    # subprocess_script_runner lets the file-based skills run their Python scripts.
    sources: list[SkillsSource] = [FileSkillsSource(str(_SKILLS_DIR), script_runner=subprocess_script_runner)]

    toolbox_url = os.environ.get("FOUNDRY_TOOLBOX_MCP_SERVER_URL")
    if toolbox_url:
        session = await _connect_foundry_toolbox(stack, toolbox_url)
        sources.append(MCPSkillsSource(client=session))
        logger.info("Foundry skills enabled (Toolbox MCP).")
    else:
        logger.info(
            "Foundry skills disabled. Set FOUNDRY_TOOLBOX_MCP_SERVER_URL to enable them."
        )

    source: SkillsSource = sources[0] if len(sources) == 1 else AggregatingSkillsSource(sources)
    # The source auto-approves skill operations through the console's session-bound approval
    # middleware. Under the Responses host that middleware isn't wired (disable_tool_auto_approval),
    # so opt the skill tools out of approval directly to keep skills frictionless — matching the
    # source, where loading/reading/running skills never prompts and only trades and shell commands do.
    return SkillsProvider(
        DeduplicatingSkillsSource(source),
        disable_load_skill_approval=True,
        disable_read_skill_resource_approval=True,
        disable_run_skill_script_approval=True,
    )


class _ToolboxAuth(httpx.Auth):
    """Attach a fresh Foundry bearer token to every request."""

    def __init__(self, token_provider: Callable[[], str]):
        self._get_token = token_provider

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


async def _connect_foundry_toolbox(stack: AsyncExitStack, url: str) -> ClientSession:
    """Open an MCP session against a Foundry Toolbox endpoint, tied to ``stack``'s lifetime."""
    token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
    http_client = await stack.enter_async_context(
        httpx.AsyncClient(
            auth=_ToolboxAuth(token_provider),
            headers={"Foundry-Features": "Toolboxes=V1Preview"},
            timeout=httpx.Timeout(30.0, read=300.0),
            follow_redirects=True,
        )
    )
    read, write, _ = await stack.enter_async_context(streamable_http_client(url=url, http_client=http_client))
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return session


def _build_research_agent(client: FoundryChatClient) -> Any:
    """Build the lean, web-search-only chat agent used for per-ticker research."""
    # This sub-agent doesn't need any harness machinery - it's a plain chat agent with a single
    # tool: the same hosted web search the harness would have added. The parent still exposes the
    # background_agents_* tools because it receives this agent via background_agents.
    return Agent(
        client=client,
        name="TickerResearchAgent",
        description="Searches the web for recent news and commentary about a single stock ticker.",
        tools=[client.get_web_search_tool()],
        instructions=(
            "You research a single stock ticker. Use the web search tool to find the most recent, "
            "relevant news and commentary, then return a short, factual summary (3-4 bullet points) "
            "with no preamble."
        ),
    )


def _build_shell() -> LocalShellTool:
    """A sandboxed shell, confined to the trade-confirmation vault.

    ``confine_workdir`` re-anchors every command to the vault, and the deny-list pre-filters
    obviously destructive command shapes. (Patterns are a UX guardrail, not a security boundary —
    for hard isolation use DockerShellTool.)
    """
    return LocalShellTool(
        mode="persistent",
        workdir=str(_VAULT_DIR),
        confine_workdir=True,
        policy=ShellPolicy(
            denylist=[
                r"\brm\s+-rf\b",
                r"\bsudo\b",
                r":\(\)\s*\{",  # fork-bomb shape
                r"\bmkfs\b",
                r">\s*/dev/sd",
            ],
        ),
        timeout=15,
    )


# The skills provider (and optional Foundry Toolbox MCP session) live for the lifetime of the host
# process, so anchor the AsyncExitStack alongside the server run rather than a short-lived context.
def _build_client() -> FoundryChatClient:
    # FoundryChatClient reads FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME from the
    # environment. DefaultAzureCredential resolves the Azure CLI login locally and managed identity
    # when hosted.
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )


def _build_agent(client: FoundryChatClient, skills_provider: SkillsProvider) -> Agent:
    research_agent = _build_research_agent(client)
    shell = _build_shell()

    # CodeAct: a sandboxed Python interpreter the model can write and run code in to crunch numbers.
    # Monty is a pure, cross-platform interpreter, so it needs no extra setup.
    context_providers: list[Any] = [MontyCodeActProvider(approval_mode="never_require")]
    logger.info("CodeAct enabled (Monty).")

    # Turn the chat client into a harness agent with Post 3's four "scaling" capabilities: skills
    # (our own provider), background agents, a confined shell, and CodeAct. Read-only file tools are
    # auto-approved so reading the portfolio is frictionless. File writes, trades, and shell
    # commands still require approval.
    return create_harness_agent(
        client=client,
        agent_instructions=FINANCE_INSTRUCTIONS,
        tools=[get_stock_price, place_trade],
        # ResponsesHostServer supplies prior turns; retain current-run persistence without reloading history.
        history_provider=InMemoryHistoryProvider(load_messages=False),
        max_context_window_tokens=MAX_CONTEXT_WINDOW_TOKENS,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        # The harness default is {cwd}/agent-file-memory, but the hosted source tree is read-only.
        # Keep session-scoped file memory in the writable, persistent hosted home instead.
        file_memory_store=FileSystemAgentFileStore(str(_FILE_MEMORY_DIR)),
        file_access_store=FileSystemAgentFileStore(str(_WORKING_DIR)),
        skills_provider=skills_provider,
        background_agents=[research_agent],
        shell_executor=shell,
        # Keep reads frictionless. The source auto-approves read-only file tools via the console's
        # session-bound rule; under the host that middleware isn't wired, so opt the read-only tools
        # out of approval directly.
        file_access_disable_readonly_tool_approval=True,
        context_providers=context_providers,
        mode_provider=AgentModeProvider(default_mode="execute"),
        # The Responses host translates and persists approval requests; the harness session-bound
        # auto-approval middleware requires an AgentSession the host does not pass, so leave it unwired
        # and express each auto-approval as the tool's own never-require flag (above) instead.
        disable_tool_auto_approval=True,
    )


async def main() -> None:
    _initialize_working_dir()

    # The skills provider (and its optional Foundry Toolbox MCP session) must stay open for the
    # lifetime of the server, so hold the AsyncExitStack across the whole run.
    async with AsyncExitStack() as stack:
        client = _build_client()
        skills_provider = await _build_skills_provider(stack)
        agent = _build_agent(client, skills_provider)

        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
