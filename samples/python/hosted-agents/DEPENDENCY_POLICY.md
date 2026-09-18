# Python Hosted Agent dependency policy

This policy applies only to executable Python projects under `samples/python/hosted-agents/`.

## Why dependencies must be reproducible

Hosted Agent samples are built locally, in pull-request validation, and by remote Foundry build systems. A sample with floating direct or transitive dependencies can resolve to different package versions in each environment and can start failing even though its code did not change.

To give consumers and build systems a reproducible installation path, each new or dependency-updated Python Hosted Agent runtime must commit one supported dependency artifact:

- **Default:** `pyproject.toml` together with `uv.lock`.
- **Backward-compatible fallback:** a fully resolved `requirements.txt`.

New samples should use uv unless they have a concrete compatibility reason not to. Existing requirements-based samples can continue using `requirements.txt`; this policy does not force an immediate repository-wide migration.

## Supported consumer artifacts

### Default: pyproject.toml and uv.lock

A new runtime should use uv throughout its documented development, validation, and deployment paths:

```text
sample/
├── azure.yaml
└── src/
    └── my-agent/
        ├── main.py
        ├── pyproject.toml
        └── uv.lock
```

CI validates that the lock matches the project and exports a complete runtime graph. The sample's `sample.yaml` build command must install a pinned uv version and use `uv sync --frozen`. Deployment must use Hosted Agent remote dependency resolution or a Dockerfile that installs a pinned uv version and uses `uv sync --frozen`. Consumers use uv directly; a duplicate `requirements.txt` export is not required.

### Backward-compatible fallback: requirements.txt

Existing requirements-based runtimes—and new runtimes with a concrete compatibility constraint—may use a fully resolved `requirements.txt`:

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

A separately executable nested client with its own dependencies should have its own supported artifact. A standard-library-only runtime may use an empty `requirements.txt` with a comment explaining that it has no third-party runtime dependencies.

When both artifact forms are present, the uv pair is authoritative and must satisfy the uv policy. `requirements.txt` is treated as a compatibility artifact and is not independently validated.

## Dependency tooling

Use uv for new samples. Existing requirements-based samples may keep their current resolver and committed `requirements.txt` fallback. Authors maintaining the fallback may use pip-tools, Poetry, PDM, Pipenv, uv export, or another resolver, but must commit a pip-compatible `requirements.txt` containing the complete resolved runtime graph.

Examples:

```bash
# Default uv-native workflow
uv lock
uv sync --frozen

# Backward-compatible requirements.txt with pip-tools
pip-compile requirements.in --output-file requirements.txt

# Backward-compatible requirements.txt exported from uv
uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file requirements.txt

```

Generated artifacts should include a comment describing the source and regeneration command when the generator supports it. Do not maintain two independent dependency lists by hand.

## What compliant artifacts contain

### requirements.txt

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

### uv.lock

A uv-native runtime must commit both `pyproject.toml` and `uv.lock`. The lock must:

- be current for the committed project, as verified by `uv lock --check`;
- contain immutable versions for the complete runtime graph;
- use the public PyPI registry for third-party packages;
- contain no VCS, direct-URL, local-path, or external editable sources.

The runtime project itself may appear as `source = { editable = "." }` or `source = { virtual = "." }`. CI also verifies that uv can export the locked production graph without updating the lock.

## When the policy is enforced

The pull-request check is a ratchet. It does not immediately reject every existing Hosted Agent sample.

The check runs when:

1. a PR adds a Python service to a Hosted Agent `azure.yaml`; or
2. a PR changes an existing runtime's dependency inputs, such as `requirements.txt`, `requirements.in`, `pyproject.toml`, `uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile`, `setup.py`, or environment files.

An existing sample with legacy floating dependencies remains grandfathered during source-only or documentation-only updates. Once its dependency inputs change, the affected runtime must satisfy this policy.

For uv-native projects, changing `pyproject.toml`, `uv.toml`, or another dependency input requires an updated `uv.lock`. For requirements-based projects, regenerate and commit `requirements.txt` when a separate authoring manifest or native lock changes, even when the resolved versions happen to remain unchanged.

## Validation

The [Hosted-agent policies workflow](../../../.github/workflows/hosted-agent-policies.yml)
runs this check on pull requests, including forks subject to GitHub's workflow
approval controls. It uses read-only permissions and no Azure credentials.

Use Python 3.13 and run the same static policy check from the repository root:

```bash
python -m pip install "pip==25.1.1" "uv==0.11.7" -r .github/scripts/requirements.txt
BASE=$(git merge-base origin/main HEAD)
python .github/scripts/check-hosted-agent-python-requirements.py \
  --base "$BASE" \
  --head HEAD
```

To also ask pip or uv to verify the committed artifact:

```bash
python .github/scripts/check-hosted-agent-python-requirements.py \
  --base "$BASE" \
  --head HEAD \
  --resolve
```

For `requirements.txt`, the closure check uses pip in dry-run mode with an empty installed-package view. It fails if pip introduces a transitive package that is not explicitly pinned. For PR security, it resolves binary distributions only; a package available only as a source distribution requires a narrow exception until a wheel is published.

For a uv-native project, the check runs `uv lock --check` and a frozen production export. The uv version used by CI is pinned in [the Hosted Agent policies workflow](../../../.github/workflows/hosted-agent-policies.yml).

The PR check validates the Hosted Agent runtime's primary Linux/Python CI environment. Required merge checks are configured separately in repository rules. Environment markers are accepted, but authors remain responsible for verifying additional platforms and supported Python versions documented by the sample.

## Exceptions

Exceptions must be narrow, temporary, and reviewable. Contributors propose them
in [`.azure-pipelines/hosted-agent-tests/python-requirements-exceptions.toml`](../../../.azure-pipelines/hosted-agent-tests/python-requirements-exceptions.toml)
as part of a public pull request. An exception identifies an exact runtime root
and diagnostic code and requires a reason, owner, public tracking issue, and
expiration date.

The path, code, reason, owner, and issue must be non-empty strings. The tracking
issue must use `https://github.com/microsoft-foundry/foundry-samples/issues/<number>`
with a positive issue number and no query string or fragment. Requiring this
public repository's issue URL avoids accepting private tracking links without
adding a credentialed lookup to the policy check.

Do not request an exception merely to keep using a preferred dependency manager. Adopt the uv-native default or use the backward-compatible `requirements.txt` path.

## Troubleshooting CI failures

Each failure includes a stable `PYREQ` code, affected runtime root, triggering file, offending line when available, remediation text, and a link back to this document.

Common failures:

| Code | Meaning |
| --- | --- |
| `PYREQ001` | An affected runtime contains neither `requirements.txt` nor the complete `pyproject.toml` + `uv.lock` pair. |
| `PYREQ002` | A package is not pinned to one concrete version in the selected artifact. |
| `PYREQ003` | A VCS dependency is used without an approved exception. |
| `PYREQ004` | An editable or local-path dependency is present. |
| `PYREQ005` | The artifact includes another requirements or constraints file. |
| `PYREQ006` | An authoring input changed without updating the selected lock artifact. |
| `PYREQ007` | Pip resolved an unpinned transitive dependency. |
| `PYREQ008` | Pip resolved a version different from the committed pin. |
| `PYREQ009` | A nonportable package index, host, or other option is embedded in the artifact. |
| `PYREQ010` | A requirement or uv TOML document is syntactically invalid. |
| `PYREQ011` | A direct URL dependency is present without an approved exception. |
| `PYREQ012` | Pip or uv could not validate the committed artifact. |
| `PYREQ013` | A uv-native runtime does not declare pinned, frozen uv validation and a lock-aware deployment path. |
