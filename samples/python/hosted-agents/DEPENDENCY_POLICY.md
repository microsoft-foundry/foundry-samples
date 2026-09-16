# Python Hosted Agent dependency policy

This policy applies only to executable Python projects under `samples/python/hosted-agents/`.

## Why dependencies must be reproducible

Hosted Agent samples are built locally, in pull-request validation, and by remote Foundry build systems. A sample with floating direct or transitive dependencies can resolve to different package versions in each environment and can start failing even though its code did not change.

To give consumers and build systems one portable, reproducible installation path, each new or dependency-updated Python Hosted Agent runtime must commit a fully resolved `requirements.txt`.

## Portable consumer artifact

`requirements.txt` is the canonical portable dependency artifact for sample consumers, CI, and deployment systems that use pip:

```bash
python -m pip install -r requirements.txt
```

The file belongs in the executable runtime project. Most Hosted Agent manifests point to that directory through `services.<name>.project`:

```text
sample/
├── azure.yaml
└── src/
    └── my-agent/
        ├── main.py
        └── requirements.txt
```

A separately executable nested client with its own dependencies should have its own `requirements.txt`. A standard-library-only runtime should commit an empty `requirements.txt` with a comment explaining that it has no third-party runtime dependencies.

## Authors may choose their locking tools

This policy does not require consumers or authors to adopt a particular dependency manager. Authors may use pip-tools, uv, Poetry, PDM, Pipenv, or another resolver. Tool-specific manifests and native locks may be committed in addition to `requirements.txt`.

Regardless of the authoring tool, export and commit a pip-compatible `requirements.txt` containing the complete resolved runtime graph. Consumers must not need the authoring tool unless that tool is an explicit subject of the sample.

Examples:

```bash
# pip-tools
pip-compile requirements.in --output-file requirements.txt

# uv
uv export --frozen --no-dev --format requirements-txt --output-file requirements.txt

# Poetry (requires poetry-plugin-export)
poetry export --format requirements.txt --output requirements.txt

# PDM
pdm export --format requirements --output requirements.txt

# Pipenv
pipenv requirements > requirements.txt
```

Generated artifacts should include a comment describing the source and regeneration command when the generator supports it. Do not maintain two independent dependency lists by hand.

## What a compliant requirements file contains

Pin every direct and transitive runtime package to one immutable version:

```text
agent-framework-core==1.12.1
agent-framework-foundry==1.10.3
azure-core==1.36.0
azure-identity==1.25.1
```

Extras, prerelease versions, and valid environment markers are supported:

```text
azure-ai-voicelive[aiohttp]==1.3.0b1
colorama==0.4.6 ; sys_platform == "win32"
```

Do not use bare names, ranges, compatible-release specifiers, wildcard pins, or exclusions:

```text
# Not reproducible
agent-framework-foundry
azure-identity>=1.25
openai~=2.8
httpx==0.28.*
pydantic!=2.11.0
```

The portable artifact must also not contain:

- editable or local-path dependencies;
- `file:` URLs;
- VCS dependencies without a narrow, reviewed exception;
- requirements or constraints includes such as `-r` or `-c`;
- index, trusted-host, or credential configuration;
- direct URLs without a narrow, reviewed exception.

VCS and direct-URL dependencies are nonportable even when their version is immutable because consumers need additional tools or external source availability. Prefer publishing and pinning a package. If that is temporarily impossible, request a narrow exception tied to a tracking issue and expiration date.

Hashes are supported and recommended where practical, but are not mandatory in the initial policy.

## When the policy is enforced

The pull-request check is a ratchet. It does not immediately reject every existing Hosted Agent sample.

The check runs when:

1. a PR adds a Python service to a Hosted Agent `azure.yaml`; or
2. a PR changes an existing runtime's dependency inputs, such as `requirements.txt`, `requirements.in`, `pyproject.toml`, `uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile`, `setup.py`, or environment files.

An existing sample with legacy floating dependencies remains grandfathered during source-only or documentation-only updates. Once its dependency inputs change, the affected runtime must satisfy this policy.

If a separate authoring manifest or native lock changes, regenerate and commit `requirements.txt` in the same PR even when the resolved versions happen to remain unchanged.

## Validation

The [Hosted-agent policies workflow](../../../.github/workflows/hosted-agent-policies.yml)
runs this check on pull requests, including forks subject to GitHub's workflow
approval controls. It uses read-only permissions and no Azure credentials.

Use Python 3.13 and run the same static policy check from the repository root:

```bash
python -m pip install "pip==25.1.1" -r .github/scripts/requirements.txt
BASE=$(git merge-base origin/main HEAD)
python .github/scripts/check-hosted-agent-python-requirements.py \
  --base "$BASE" \
  --head HEAD
```

To also ask pip to verify that the artifact includes the complete transitive graph:

```bash
python .github/scripts/check-hosted-agent-python-requirements.py \
  --base "$BASE" \
  --head HEAD \
  --resolve
```

The closure check uses pip in dry-run mode with an empty installed-package view. It fails if pip introduces a transitive package that is not explicitly pinned in `requirements.txt`. For PR security, it resolves binary distributions only; a package available only as a source distribution requires a narrow exception until a wheel is published.

The PR check validates the Hosted Agent runtime's primary Linux/Python CI environment. Required merge checks are configured separately in repository rules. Environment markers are accepted, but authors remain responsible for verifying additional platforms and supported Python versions documented by the sample.

## Exceptions

Exceptions must be narrow, temporary, and reviewable. Contributors propose them
in [`.azure-pipelines/hosted-agent-tests/python-requirements-exceptions.toml`](../../../.azure-pipelines/hosted-agent-tests/python-requirements-exceptions.toml)
as part of a public pull request. An exception identifies an exact runtime root
and diagnostic code and requires a reason, owner, public tracking issue, and
expiration date.

Do not request an exception merely to keep using a preferred dependency manager. Native manifests and locks are allowed; the requirement is to export their resolution to the portable consumer artifact.

## Troubleshooting CI failures

Each failure includes a stable `PYREQ` code, affected runtime root, triggering file, offending line when available, remediation text, and a link back to this document.

Common failures:

| Code | Meaning |
| --- | --- |
| `PYREQ001` | An affected runtime does not contain `requirements.txt`. |
| `PYREQ002` | A package is not pinned to one concrete version. |
| `PYREQ003` | A VCS dependency is used without an approved exception. |
| `PYREQ004` | An editable or local-path dependency is present. |
| `PYREQ005` | The artifact includes another requirements or constraints file. |
| `PYREQ006` | An authoring input changed without updating the portable export. |
| `PYREQ007` | Pip resolved an unpinned transitive dependency. |
| `PYREQ008` | Pip resolved a version different from the committed pin. |
| `PYREQ009` | A pip index, host, or other option is embedded in the artifact. |
| `PYREQ010` | A requirement is syntactically invalid. |
| `PYREQ011` | A direct URL dependency is present without an approved exception. |
| `PYREQ012` | Pip could not resolve the committed artifact. |
