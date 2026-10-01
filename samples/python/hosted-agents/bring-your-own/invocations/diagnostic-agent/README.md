<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Diagnostic Agent (Python, Invocations)

A **diagnostic** hosted-agent built on the Invocations protocol. It does **not** call an LLM and does **not** require a Foundry project endpoint or a model deployment. Instead, on each invocation, it runs DNS / TCP / TLS / HTTP probes against caller-supplied hostnames and returns a structured JSON report describing what the runtime sandbox can actually reach.

Use this image to answer questions like:

- From inside the delegated `agent-subnet-*`, what does `<customer>.azurecr.io` resolve to? A private IP or a public one?
- Does `https://<customer>.azurecr.io/v2/` return `401 Unauthorized` (registry reachable) or does the request hang / get connection refused / TLS-verify-fail?
- Can the runtime egress to public Azure endpoints (`login.microsoftonline.com`, `management.azure.com`) or only to private endpoints?

For a read-only explanation of the Azure network configuration before running
these probes, use the
[Foundry Reachability Analyzer](../../../../../../infrastructure/infrastructure-setup-bicep/deployment-tools/reachability-analyzer/README.md).
It complements this agent with static DNS, NSG, route, and private-endpoint
analysis; it does not deploy a second live probe.

## Design notes

- **Stdlib-only probe code.** All DNS / TCP / TLS / HTTP probes are written against `socket`, `ssl`, `urllib`, and `http.client`. The network is the very thing being diagnosed; the probes must not depend on import-time package fetches or pyca handshakes that obscure the failure mode.
- **No model, no project endpoint.** The manifest declares no `resources` and no `environment_variables`. The image is portable across any Foundry project.
- **Buffered JSON or opt-in SSE.** By default, all probe outcomes are returned as one JSON document. Set `"stream": true` or send `Accept: text/event-stream` to receive SSE heartbeats followed by the complete report. Per-probe failures remain in the report rather than becoming non-2xx HTTP responses.
- **Caller controls the probe matrix.** The request body lists hostnames; nothing is hard-coded to a specific customer ACR. An empty body runs only the safe defaults (container info, env dump, and a small set of public Azure endpoints).
- **No secrets in the response.** Env vars matching `KEY`, `SECRET`, `PASSWORD`, `TOKEN`, `CONNECTION_STRING`, or `SAS` are reported with their length only.
- **Extensible probe framework.** Each diagnostic is a small, self-registering **probe** that emits one uniform `ProbeResult` (`probe`/`status`/`findings`/`metrics`/`evidence`). A probe-agnostic runner executes them under isolation and an aggregator rolls them into a top-level `summary`. Adding a probe requires **no** change to the handler, runner, or aggregator — see [DEVELOPMENT.md](DEVELOPMENT.md#developing-probes). The response is validated by [`schema/report.schema.json`](src/diagnostic-agent-python-invocations/schema/report.schema.json).
- **Structured, uniform output.** Every probe emits the same `ProbeResult` (`probe`/`status`/`findings`/`metrics`/`evidence`) under `results[]`, with a probe-agnostic `summary` rollup. New consumers and LLM readers get one shape to parse across all diagnostics; the response is validated by [`schema/report.schema.json`](src/diagnostic-agent-python-invocations/schema/report.schema.json).

## Getting Started (Bring Your Own Infrastructure)

This sample is designed for **Bring Your Own** (BYO) infrastructure scenarios where the Azure Foundry account, project, and supporting resources are already provisioned separately.

### Prerequisites

- An existing **Azure Foundry project** (account + project already created)
- An existing **container registry** (if deploying in container mode)
- **Python 3.12+** and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed outside the project virtual environment
- **Azure CLI** with `azure.ai.agents` extension installed:
  ```bash
  azd config set ai.agents.version 0.1.22-preview
  ```

### Deployment

1. **Set environment variables** — Copy `.env.example` to `.env` and fill in your existing Foundry project details:
   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your project information:
   ```env
   AZURE_AI_PROJECT_ID=/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>
   AZURE_AI_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
   AZURE_SUBSCRIPTION_ID=<sub-id>
   AZURE_ENV_NAME=<env-name>
   AZURE_LOCATION=<region>
   AZURE_CONTAINER_REGISTRY_ENDPOINT=<registry>.azurecr.io  # For container mode only
   ```

2. **Deploy the agent** — Use `azd deploy` (not `azd up`, since no infrastructure needs provisioning):

   **Option A: Container Mode (Recommended)** — Docker image pushed to container registry:
   ```bash
   # Default configuration — uses azure.yaml as-is
   azd deploy --no-prompt
   ```
   - Builds Docker image from `Dockerfile`
   - Pushes to `AZURE_CONTAINER_REGISTRY_ENDPOINT`
   - Deploys container to Foundry
   - **Requires**: ACR configured in `.env`

   **Option B: ZIP Mode** — Bundle Python code directly (no container):
   ```bash
   # Step 1: Edit azure.yaml
   # Change this line:
   #   language: docker
   # To:
   #   language: python
   #
   # And remove the docker section entirely (lines 12-13):
   #   docker:
   #       remoteBuild: false

   # Step 2: Deploy
   azd deploy --no-prompt
   ```
   - Bundles Python source code as ZIP
   - Deploys to Foundry without container image
   - **No ACR required**
   - Useful for code-only scenarios or testing

3. **Invoke the agent** — Once deployed, invoke it via REST:
   ```bash
   TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
   curl -X POST \
     "https://<account>.services.ai.azure.com/api/projects/<project>/agents/diagnostic-agent-python-invocations/endpoint/protocols/invocations?api-version=v1" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"hosts": ["microsoft.com"]}'
   ```

## Deployment Modes Comparison

| Aspect | Container Mode | ZIP Mode |
|--------|---|---|
| **Command** | `azd deploy --no-prompt` (default) | Edit `azure.yaml`, then `azd deploy --no-prompt` |
| **Build Process** | Builds Docker image → Pushes to ACR | Bundles Python code as ZIP |
| **Requires ACR** | ✅ Yes | ❌ No |
| **Container Image Size** | ~500 MB (python:3.12-slim) | N/A (code only) |
| **Startup Speed** | ~30 seconds | ~30 seconds (similar) |
| **Use Case** | Production, versioned images | Testing, code-only scenarios |
| **Config Change** | None (default) | Edit `azure.yaml` (1 line) |

Validation: both execution paths were tested locally after removing IMDS/MSI support.

## Troubleshooting: ACR Not Reachable From Private Network

If private networking is misconfigured, container-mode deployment can fail before the diagnostic image is even available (for example, DNS failure, blocked egress, or Private Endpoint routing issues to your private ACR).

Use one of the following fallback paths to keep debugging network reachability:

### Path 1 (Preferred): ZIP deploy from a VM attached to the target network

This route avoids ACR entirely and still runs the same diagnostics code in Foundry.

1. Use a VM that is attached to the same VNet/subnet path you want to validate.
2. In `azure.yaml`, switch to ZIP mode:
  - Change `language: docker` to `language: python`.
  - Remove the `docker:` block.
3. Deploy with:
  ```bash
  azd deploy --no-prompt
  ```
4. Invoke the agent and probe your private endpoints as usual.

When ZIP mode works but container mode fails, the issue is typically on the ACR path (DNS, NSG/UDR/firewall, or PE routing), not in the probe logic.

### Path 2: Temporary public-ACR fallback for image distribution

If you must validate container mode while private ACR is unreachable, use a temporary public ACR (PNA enabled) for this diagnostic image.

1. Set `AZURE_CONTAINER_REGISTRY_ENDPOINT=<public-registry>.azurecr.io` in `.env`.
2. Run:
  ```bash
  azd deploy --no-prompt
  ```
3. Re-run the same diagnostic probes.

If deployment succeeds with public ACR but fails with private ACR, the regression is isolated to private ACR connectivity/policy.

For security, treat this as a short-lived troubleshooting step only: remove temporary public exposure and revert to private ACR once networking is fixed.

## Request body contract

All fields are optional:

```json
{
  "hosts": [
    "<customer-acr>.azurecr.io",
    "<customer-acr>.<region>.data.azurecr.io"
  ],
  "public_hosts": [
    "https://www.microsoft.com/",
    "https://management.azure.com/metadata/endpoints?api-version=2020-09-01",
    "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration"
  ],
  "resolvers":      ["168.63.129.16"],
  "record_types":   ["A", "AAAA"],
  "raw_dns":        true,
  "dns_attempts":   20,
  "gai_attempts":   20,
  "parallel_probe": true,
  "dns_propagation_probe":         true,
  "dns_propagation_duration_sec":  30,
  "dns_propagation_interval_sec":   1,
  "dns_propagation_threshold_sec": 15,
  "stream": true,
  "direct_targets": ["10.0.1.9:443"],
  "include_env_dump":       true,
  "include_container_info": true,
  "include_evidence":       true,
  "tcp_timeout_sec":  5,
  "http_timeout_sec": 10,
  "dns_timeout_sec":  5
}
```

| Field | Default | Notes |
|---|---|---|
| `hosts` | `[]` | List of FQDNs. For each, runs raw DNS (dig) + DNS → TCP/443 → TLS/443 → HTTPS GET. For `*.azurecr.io` and `*.data.azurecr.io` hosts, the GET path is `/v2/` (returns 401 with `Www-Authenticate` when reachable). For all other hosts, GET path is `/`. |
| `public_hosts` | small built-in list | Full URLs. HTTPS-GET only — no DNS/TCP/TLS breakdown. Pass `[]` to skip. |
| `resolvers` | `["168.63.129.16"]` | **Extra** DNS servers to query alongside the ones in `/etc/resolv.conf`. Defaults to Azure platform DNS (`168.63.129.16`) so a private-zone linkage gap shows up as a per-resolver disagreement out of the box. Pass `[]` to compare against the system resolvers only. |
| `record_types` | `["A","AAAA"]` | Record types queried per resolver by the raw DNS client. |
| `raw_dns` | `true` | Automate `dig <type> @<resolver>` for every (resolver × record type): reports the real rcode (SERVFAIL/REFUSED/NXDOMAIN/NODATA/timeout), the CNAME chain, latency, and cross-resolver disagreement. Runs **even when `getaddrinfo` fails** (the EAI_AGAIN case). |
| `dns_attempts` | `1` | Repeat each raw DNS query N times to expose **intermittency**. Reports per-resolver `timeout_rate`, `successes/attempts`, and min/max/avg latency; classifies `DNS_INTERMITTENT` / `DNS_OK_PRIVATE_INTERMITTENT` when some attempts answer and others time out. On any UDP timeout it also probes **TCP/53** and flags `DNS_UDP_DROP_TCP_OK` (EDNS/MTU fragmentation). |
| `gai_attempts` | `1` | Repeat the OS `getaddrinfo` call N times and report the **failure rate** (`successes/failures`, per-error counts) — measures the intermittent `EAI_AGAIN` the app actually experiences, separate from the raw wire-level result. |
| `parallel_probe` | `false` | Mimic glibc's default `getaddrinfo`: send **A and AAAA back-to-back on one UDP socket** and measure how often a reply is lost (`both_ok_rate`). A loss here while raw sequential queries are clean is the signature of a **concurrent-query** problem (`PARALLEL_DUAL_LOSS`) — the cause of `getaddrinfo` failures that `dig` cannot reproduce and that firewalls show no drops for. |
| `dns_propagation_probe` | `false` | Run the opt-in `dns.propagation` probe for each host. It samples OS `getaddrinfo` over time and records a timestamped attempt timeline. Use it to distinguish delayed network-connection/DNS propagation from persistent or intermittent DNS failure. |
| `dns_propagation_duration_sec` | `30` | Observation window in seconds. Clamped to `0`–`120`. |
| `dns_propagation_interval_sec` | `1` | Target cadence between samples in seconds. Values below `0.1` are clamped to `0.1`; query time counts toward the interval. |
| `dns_propagation_threshold_sec` | `15` | Failure at invocation start that recovers within this threshold produces `DNS_INITIAL_INSTABILITY`; recovery after it produces `DNS_PROPAGATION_DELAY`. Failure for the full window produces `DNS_FAILURE_PERSISTED`. Clamped to the observation window. |
| `stream` | `false` | Return Server-Sent Events instead of buffered JSON. The stream emits `started`, a `heartbeat` every five seconds while probes run, the complete report in `report`, then `done`. Sending `Accept: text/event-stream` also enables streaming. |
| `direct_targets` | `[]` | `ip:port` (or `host:port`) reachability tests that **skip DNS** — isolate a network-path break from a DNS break. |
| `include_env_dump` | `true` | Returns env vars matching an allowlist prefix (`FOUNDRY_`, `AZURE_`, `KUBERNETES_`, etc.); credential-shaped values are length-only. |
| `include_container_info` | `true` | Hostname, container IP, default gateway from `/proc/net/route`, resolvers + full `resolv.conf` detail (`search`, `ndots`, `timeout`, `attempts`). |
| `include_evidence` | `true` | Include each probe's verbose `evidence` block (raw dig output, per-resolver records, before/after counters). Set `false` for a lean response carrying only `status`/`findings`/`metrics`. |
| `tcp_timeout_sec` | `5` | Per-attempt TCP/TLS timeout. |
| `http_timeout_sec` | `10` | HTTP timeout. |
| `dns_timeout_sec` | `5` | Per-query raw DNS timeout. |

You may also send a **plain-text body** containing a single hostname; the agent treats it as `{"hosts": ["<text>"]}`. Useful from the Foundry portal chat UI.

If the body is empty, the agent runs only the defaults: container info + env dump + the built-in public-host list. No private hosts are probed unless explicitly requested.

For long-running diagnostics, request SSE and disable curl buffering:

```bash
curl -sS -N -X POST "<invocations-url>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"hosts":["<customer-acr>.azurecr.io"],"public_hosts":[],"dns_propagation_probe":true,"stream":true}'
```

Heartbeats reduce idle-connection timeout risk but do not override a platform or client maximum invocation duration.

## Keeping the sandbox warm

A hosted-agent sandbox suspends after ~15 minutes idle. To hold one sandbox warm for extended inspection (for example, watching host metrics over an hour) **without an external caller**, the agent can self-ping on a fixed cadence using its own managed identity. This is off by default and enabled purely with environment variables — a single deploy keeps the sandbox warm, with no extra request needed.

The loop acquires a data-plane token via `DefaultAzureCredential`, then POSTs `{"keepalive_ping": true}` to this agent's own external invocations endpoint. That body hits a cheap short-circuit returning `200 {"status": "alive"}` before any probe runs, so each keepalive is inexpensive and never recurses. A `200` also confirms the agent's identity has data-plane invoke permission; a `401`/`403` means it does not.

| Env var | Default | Notes |
|---|---|---|
| `KEEPALIVE_SELF_PING` | *(unset)* | Set to `1`/`true`/`yes` to start the loop at container startup. Off by default. |
| `KEEPALIVE_SELF_PING_INTERVAL_SEC` | `120` | Cadence between pings in seconds. Keep it under the ~15-min idle timeout. |
| `KEEPALIVE_SELF_PING_DURATION_SEC` | `900` | Total window in seconds; the loop exits after this. The default 15 min keeps the sandbox warm for the run and then lets it idle out (~30 min total lifetime). Raise it for long-running inspection (for example `28800` for 8 hours), or set `0` to run for the container's lifetime. |
| `KEEPALIVE_SELF_PING_TIMEOUT_SEC` | `30` | Per-ping HTTP timeout in seconds. |
| `KEEPALIVE_SELF_PING_API_VERSION` | `v1` | Invocations API version used in the self-ping URL. |

The endpoint and session are taken from the platform-injected env vars `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_AGENT_NAME`, and `FOUNDRY_AGENT_SESSION_ID`; if the project endpoint or agent name is unset the loop logs a warning and does nothing.

Any caller can POST `{"keepalive_ping": true}` to the invocations endpoint to read the loop's current status without scraping container logs — the short-circuit response carries a `keepalive_self_ping` block:

```json
{
  "status": "alive",
  "agent_session_id": "…",
  "invocation_id": "…",
  "keepalive_self_ping": {
    "enabled": true,
    "running": true,
    "interval_sec": 120,
    "duration_sec": 900,
    "ping_count": 7,
    "last_code": 200,
    "last_error": null,
    "last_ping_utc": "2026-08-04T14:52:31.004+00:00",
    "last_session_id": "…"
  }
}
```

When the loop is off, `enabled` and `running` are `false` and `last_code` is `null`.

## Response shape

Every probe emits one uniform `ProbeResult` under `results[]`; `summary` is a
probe-agnostic rollup of them. Top-level `status` reports whether the **agent** ran
(`ok`, or `partial` if a probe crashed); `summary.status` is the **diagnostic
verdict** (`ok`/`warn`/`fail`). With `stream` omitted or `false`, this report is the
HTTP 200 JSON response body. With `stream: true`, the HTTP 200 body is an SSE stream
and this report appears in the `report` event's `report` property. The report itself
is validated by [`schema/report.schema.json`](src/diagnostic-agent-python-invocations/schema/report.schema.json).

```json
{
  "schema_version": 1,
  "status": "ok",
  "summary": {
    "status": "fail",
    "targets_failed": ["<acct>.services.ai.azure.com"],
    "findings_by_severity": {"error": 2, "warning": 1, "info": 3},
    "top_findings": [
      {"probe": "dns.getaddrinfo", "code": "GAI_FAIL_RAW_OK", "severity": "error",
       "message": "getaddrinfo fails though the record resolves at the wire level.",
       "target": "<acct>.services.ai.azure.com"},
      {"probe": "dns.raw", "code": "DNS_OK_PRIVATE_INTERMITTENT", "severity": "warning",
       "message": "A-record UDP via configured resolver timed out ~45% of attempts; TCP works.",
       "target": "<acct>.services.ai.azure.com"}
    ],
    "probes_run": ["container.info","env.dump","dns.getaddrinfo","dns.raw","dns.parallel","conn.tcp","conn.tls","conn.http","net.udp_counters"],
    "probes_errored": []
  },
  "results": [
    {"probe": "dns.getaddrinfo", "probe_version": 1, "status": "fail",
     "target": {"host": "<acct>.services.ai.azure.com"},
     "summary": "getaddrinfo FAILED (gaierror)",
     "findings": [{"code": "GAI_FAIL_RAW_OK", "severity": "error",
       "message": "getaddrinfo failed but the record resolves at the wire level.",
       "remediation": "Root cause is the DNS path/server, not the app; see dns.raw."}],
     "metrics": {"gai_attempts": 20, "gai_failures": 3, "gai_failure_rate": 0.15},
     "evidence": {"...": "gated by include_evidence"}, "elapsed_ms": 210.4},

    {"probe": "dns.raw", "probe_version": 1, "status": "warn",
     "target": {"host": "<acct>.services.ai.azure.com"},
     "summary": "DNS_OK_PRIVATE_INTERMITTENT",
     "findings": [{"code": "DNS_OK_PRIVATE_INTERMITTENT", "severity": "warning",
       "message": "A over UDP 11/20 ok, 9 timeouts (avg 1367ms); TCP OK; AAAA OK.",
       "remediation": "Fix UDP A-record recursion on the resolver, or add a 2nd resolver / VNet-local Private Resolver."}],
     "metrics": {"a_udp_timeout_rate": 0.45, "a_udp_avg_ms": 1367.0, "a_tcp_ok": 1},
     "elapsed_ms": 41230.7},

    {"probe": "dns.parallel", "probe_version": 1, "status": "ok",
     "target": {"host": "<acct>.services.ai.azure.com"},
     "summary": "PARALLEL_DUAL_OK",
     "findings": [{"code": "PARALLEL_DUAL_OK", "severity": "info",
       "message": "20/20 both-ok — rules out same-socket concurrent-query collision.",
       "remediation": null}],
     "metrics": {"both_ok_rate": 1.0, "a_lost": 0, "aaaa_lost": 0}, "elapsed_ms": 620.9},

    {"probe": "net.udp_counters", "probe_version": 1, "status": "ok",
     "target": {"kind": "container"},
     "summary": "No local UDP/interface drops; loss is on the path or upstream.",
     "findings": [{"code": "LOCAL_UDP_CLEAN", "severity": "info",
       "message": "No local UDP/interface drops during the run.", "remediation": null}],
     "metrics": {"udp_in_errors_delta": 0, "udp_rcvbuf_errors_delta": 0, "iface_rx_dropped_delta": 0},
     "elapsed_ms": 4.2}
  ]
}
```

Each probe's `evidence` (when `include_evidence` is true) carries the full raw
detail — for `dns.raw` that includes the per-resolver records, rcodes, CNAME
chains, `dig`-style text, and the UDP-vs-TCP comparison.

## Interpretation cheat-sheet

**Read `summary.top_findings` first** for the verdict, then drill into `results[]`
for detail. Every finding carries a stable `code` (e.g. `GAI_FAIL_RAW_OK`), for
problems a `remediation`, and supporting numbers under the result's `metrics`.

| Probe / finding `code` | Likely cause |
|---|---|
| `dns.getaddrinfo` `GAI_FAIL_RAW_OK` | `getaddrinfo` fails but the record resolves at the wire level — the app-visible failure is in the DNS **path/server**, not connectivity. Drill into `dns.raw`. |
| `dns.getaddrinfo` `GAI_INTERMITTENT` (`gai_failure_rate > 0`) | The OS resolver fails intermittently — quantifies the `EAI_AGAIN` the app actually experiences. |
| `dns.raw` `DNS_OK_PRIVATE_INTERMITTENT` / `DNS_INTERMITTENT` (`a_udp_timeout_rate`) | Some attempts answered, others timed out. Record exists but the resolver/path is unreliable (packet loss, forwarder capacity, flaky hub/ExpressRoute hop). Fix DNS-path reliability; add a second resolver or a local Private Resolver. |
| `dns.raw` `DNS_UDP_DROP_TCP_OK` (`a_tcp_ok=1`, high `a_udp_timeout_rate`) | UDP/53 times out but TCP/53 answers — EDNS/MTU fragmentation or UDP-response loss on the path. Allow UDP fragments/EDNS(0) or use a local Private Resolver. |
| `dns.raw` `DNS_OK_PUBLIC_FOR_PRIVATE` | Name CNAMEs to `privatelink.*` but resolved to a **public** IP. For a **configured** resolver it doesn't serve the private zone; for an **extra** comparison resolver (e.g. `168.63.129.16` from a spoke VNet) this is **expected** in a hub-DNS design. |
| `dns.raw` `DNS_SERVFAIL` | Resolver/forwarder authoritative-but-broken for the zone (or its conditional forwarder failed). Fast failure. |
| `dns.raw` `DNS_REFUSED` | Source-based ACL/view excludes this subnet — authorize the agent-subnet source on the DNS server. |
| `dns.raw` `DNS_TIMEOUT` | Resolver/forwarder unreachable or dropping packets from this subnet (NSG/UDR/peering). Slow failure ⇒ path problem, not a missing record. |
| `dns.raw` `DNS_NXDOMAIN` / `DNS_NODATA` | Name/record missing in the zone this resolver serves. |
| `dns.raw` `RESOLVER_DISAGREE` | Resolvers return different answers — the private zone is only linked to part of the DNS path. Classic "works from the VM subnet, not the agent subnet." |
| `dns.parallel` `PARALLEL_DUAL_LOSS` (`both_ok_rate < 1`) | Parallel A+AAAA on one socket loses replies while sequential queries are clean — a concurrent-query problem (the `EAI_AGAIN` `dig` can't reproduce and firewalls show no drops for). |
| `dns.parallel` `PARALLEL_DUAL_OK` | Parallel A+AAAA always succeeded — **rules out** the same-socket concurrent-query collision; look at the raw A-record path (`dns.raw`) instead. |
| `dns.propagation` `DNS_INITIAL_INSTABILITY` | DNS failed immediately after invocation start but recovered within the threshold. Delay dependent calls until resolution is stable and investigate startup-time network propagation. |
| `dns.propagation` `DNS_PROPAGATION_DELAY` / `DNS_FAILURE_PERSISTED` | DNS remained unavailable beyond the configured threshold or throughout the observation window. Investigate managed-network connection and private-DNS propagation. |
| `net.udp_counters` `LOCAL_UDP_CLEAN` | No local NIC/UDP-socket drops during the run — the loss is on the network **path or upstream server**, not this sandbox. |
| `net.udp_counters` `LOCAL_UDP_DROPS` | Local UDP/socket drops occurred — part of the loss may be local (socket-buffer exhaustion, CPU starvation). Inspect the per-counter deltas. |
| `conn.direct` `ok` while the same host fails DNS | The private IP is reachable — the break is **DNS**, not the network path. |
| `conn.tcp` `TCP_FAIL` (timeout) | NSG egress rule, UDR routing to an NVA that black-holes the flow, or firewall drop. |
| `conn.tcp` `TCP_FAIL` (refused) | PE is in Disconnected state, or an upstream device is sending RST. |
| `conn.tls` `TLS_FAIL` (SSLCertVerificationError) | A firewall is doing TLS interception. Bypass `*.azurecr.io` / `*.azure.com`. |
| `conn.tls` `TLS_FAIL` (SSLError mid-handshake) | NVA breaking SNI. Enable SNI passthrough. |
| `conn.http` `code=401` on `/v2/` for ACR | Registry is reachable. ✅ |
| `conn.http` `code=403` on `/v2/` for ACR | PNA=Disabled + caller not on an approved PE. |

## Per-service expected results

When probing a private-link-enabled Foundry project's BYO dependency
services, each service has a distinct healthy fingerprint. Anything that
deviates from the row below points at a misconfiguration, not auth.

| Service | FQDN pattern | Expected cert SANs | Expected unauth `GET /` |
|---|---|---|---|
| ACR (registry) | `<acr>.azurecr.io` | `*.azurecr.io`, `*.<region>.geo.azurecr.io` | `401` + `WWW-Authenticate: Bearer realm=".../oauth2/token"` (path: `/v2/`) |
| ACR (data) | `<acr>.<region>.data.azurecr.io` | `*.<region>.data.azurecr.io`, `*.azurecr.io`, `*.data.azurecr.io` | `403 DENIED` (path: `/v2/`) |
| Cosmos DB | `<acct>.documents.azure.com` | `*.{sql,mongo,table,gremlin,cassandra}.cosmosdb.azure.com` | `401 Unauthorized` + JSON body about missing `authorization` header |
| Storage (blob) | `<acct>.blob.core.windows.net` | `*.blob.core.windows.net`, `*.blob.storage.azure.net` | `400 InvalidQueryParameterValue` (root GET is malformed by design) |
| AI Search | `<svc>.search.windows.net` | `*.search.windows.net`, `*.management.search.windows.net` | `401 Unauthorized` + `WWW-Authenticate: Bearer ... resource="https://search.azure.com"` |
| AI Services (cognitive) | `<acct>.cognitiveservices.azure.com` | `*.cognitiveservices.azure.com`, `*.openai.azure.com`, `*.services.ai.azure.com` | `200 Service Operational` |
| AI Services (openai) | `<acct>.openai.azure.com` | (same as above) | `200 Service Operational` |
| AI Services (services.ai) | `<acct>.services.ai.azure.com` | `<acct>.services.ai.azure.com` (account-specific cert) | `200 OK` (`server: Kestrel`) |

Any cert issuer other than a `Microsoft TLS …` / `Microsoft Azure RSA TLS Issuing CA …` / per-account cert (for example, an enterprise TLS inspection CA) suggests the TLS handshake was intercepted by a network device instead of terminating at the expected Private Endpoint.

## Realistic multi-service response

Here's what a successful probe against all of a Foundry project's BYO
private endpoints looks like (truncated for readability; placeholder
resource names). DNS resolves to the PE subnet (`192.168.1.0/24`), TCP/443
succeeds, TLS terminates with a Microsoft-issued cert whose SANs cover the
host, and the unauth `GET /` returns each service's expected challenge.

Request:

```json
{
  "hosts": [
    "myorgacr.southindia.data.azurecr.io",
    "myorgacr.azurecr.io",
    "myorgcosmos.documents.azure.com",
    "myorgstorage.blob.core.windows.net",
    "myorgsearch.search.windows.net",
    "myorgaisvc.cognitiveservices.azure.com",
    "myorgaisvc.openai.azure.com",
    "myorgaisvc.services.ai.azure.com"
  ]
}
```

Response (per-host summary, full JSON elided):

| Host | DNS IP | TCP | TLS | HTTP |
|---|---|---|---|---|
| `myorgacr.southindia.data.azurecr.io` | `192.168.1.11` | ok | ok | `403 DENIED` (`/v2/`) |
| `myorgacr.azurecr.io` | `192.168.1.12` | ok | ok | `401 Bearer realm=...` (`/v2/`) |
| `myorgcosmos.documents.azure.com` | `192.168.1.4` | ok | ok | `401` (Cosmos) |
| `myorgstorage.blob.core.windows.net` | `192.168.1.9` | ok | ok | `400 InvalidQueryParameterValue` |
| `myorgsearch.search.windows.net` | `192.168.1.10` | ok | ok | `401` + Search WWW-Authenticate |
| `myorgaisvc.cognitiveservices.azure.com` | `192.168.1.6` | ok | ok | `200 Service Operational` |
| `myorgaisvc.openai.azure.com` | `192.168.1.7` | ok | ok | `200 Service Operational` |
| `myorgaisvc.services.ai.azure.com` | `192.168.1.8` | ok | ok | `200 OK` (Kestrel) |

## Running locally

This sample follows the same `azd ai agent` workflow as the other invocations samples. See [hello-world/README.md](../hello-world/README.md) for the full `azd` / Foundry Toolkit walkthrough.

For the local-only path (no `azd`):

```bash
uv sync --frozen
uv run --no-sync python main.py
```

The agent listens on `http://localhost:8088/`. Invoke it:

```bash
# Default profile (container + env + public hosts only)
curl -sS -X POST "http://localhost:8088/invocations?agent_session_id=diag-001" \
  -H "Content-Type: application/json" -d '{}' | jq

# Probe a specific ACR (registry + data plane)
curl -sS -X POST "http://localhost:8088/invocations?agent_session_id=diag-001" \
  -H "Content-Type: application/json" \
  -d '{
        "hosts": [
          "<acr>.azurecr.io",
          "<acr>.<region>.data.azurecr.io"
        ],
        "public_hosts": []
      }' | jq

# Plain-text body — quick single-host check from the portal chat UI
curl -sS -X POST "http://localhost:8088/invocations" \
  -H "Content-Type: text/plain" \
  --data "<acr>.azurecr.io" | jq
```

The interesting runs happen when the image is deployed into a Foundry project and invoked from there.

Maintainers validating response and deployment-mode compatibility should see [DEVELOPMENT.md](DEVELOPMENT.md).

## Deploying to Microsoft Foundry

Same `azd` / Foundry Toolkit workflow as the other invocations samples — see [hello-world/README.md](../hello-world/README.md#deploying-the-agent-to-microsoft-foundry). Because the manifest declares no `resources` block, deployment does not provision a model.

## Security notes

- This image is intended for diagnostics, not for production agent traffic. Treat its responses as semi-public: nothing in the response is a credential, but env-var names can reveal infrastructure topology.
- The image never writes secrets. It does not parse, log, or return `Authorization` headers, or any env var matching credential-shaped substrings.
- The image performs HTTPS-GET only. No POST/PUT/DELETE; no authenticated calls to the probed hosts.
