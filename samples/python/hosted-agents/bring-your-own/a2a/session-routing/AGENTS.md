# Coding Agent Instructions - A2A session routing

This project was built with the microsoft-foundry skill. Before working on or answering questions about foundry agents, read the microsoft-foundry skill first.

This sample hosts three deterministic native A2A 1.0 agents in Foundry. It tests
session routing independently of LLM conversations or model quality.

## Deployment mode

Direct code deployment, Python 3.13, with bundled Linux dependencies. No Dockerfile
or model is required. All three services intentionally share the same source
directory; `REPRO_ROLE` selects A, B or C.

## Key files

- `azure.yaml`: three agents and a configurable existing project endpoint.
- `src/agent/main.py`: forwarders and C's session-scoped synthetic ledger.
- `src/agent/client.py`: native A2A client and request-scoped identity forwarding.
- `src/agent/requirements.txt`: fully pinned runtime graph.
- `prepare_bundle.ps1`: Linux dependency bundle preparation from Windows.
- `run_experiment.py`: single-user sequential/concurrent matrix.
- `run_real_user.py`: independent sign-ins and receipt comparison.
- `evidence/`: historical synthetic receipts; never replace with live-test output.

## Dependency workflow

Follow `samples/python/hosted-agents/DEPENDENCY_POLICY.md`. This sample uses the
fully pinned requirements fallback because the tested preview SDK remote build
failed to recognize the uv-only project, and subsequent remote restores hit TLS
errors. Preserve the tested versions. Regenerate the full graph and run the
repository dependency checker, including `--resolve`, for dependency changes.
The preview SDK packages require the public Azure SDK development feed; index
configuration belongs in install commands, not the requirements artifact.

## Development and evidence

Use the standard `logging` module for runtime diagnostics. CLI tools may print.
Run `python -m unittest discover -s tests -v` and `python test_local.py` from a
restored environment. The local test owns and stops its three child processes.
Cloud A2A needs the dedicated runners, not the shared Responses/Invocations
harness. Do not silently substitute another protocol to satisfy CI.

Never forward caller-supplied identity headers as proof of identity. A/B forward
the SDK's platform call context and use their own managed identities. Test only
synthetic markers. Session IDs, context IDs and boot IDs are distinct concepts.
Do not assert cross-user or concurrent isolation without the relevant receipts.
