# Copyright (c) Microsoft. All rights reserved.

"""Guard the locked and installed deployment dependencies against known advisories."""

import ssl
import tomllib
from importlib.metadata import version
from pathlib import Path

import certifi
import pytest
from opentelemetry.trace import TraceState, get_current_span
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from packaging.version import Version

# GHSA-6q48-6c7w-9gw2 and GHSA-xcq7-p3pf-p88h.
SECURITY_FLOORS = [("certifi", "2026.10.19"), ("opentelemetry-api", "1.45.1")]


@pytest.mark.parametrize(("name", "minimum"), SECURITY_FLOORS)
def test_locked_security_dependencies(name, minimum):
    lock = tomllib.loads((Path(__file__).parents[1] / "uv.lock").read_text(encoding="utf-8"))
    versions = [package["version"] for package in lock["package"] if package["name"] == name]
    assert versions
    assert all(Version(value) >= Version(minimum) for value in versions)


@pytest.mark.parametrize(("name", "minimum"), SECURITY_FLOORS)
def test_installed_security_dependencies(name, minimum):
    assert Version(version(name)) >= Version(minimum)


def test_installed_telemetry_api_and_sdk_are_compatible():
    assert version("opentelemetry-sdk") == version("opentelemetry-api")


def test_ca_bundle_removes_compromised_root_but_remains_usable():
    certificates = ssl.create_default_context(cafile=certifi.where()).get_ca_certs()
    assert certificates
    common_names = {
        value
        for certificate in certificates
        for attributes in certificate["subject"]
        for key, value in attributes
        if key == "commonName"
    }
    assert "emSign ECC Root CA - G3" not in common_names


def test_tracestate_boundary_rejection_does_not_break_later_valid_input():
    valid = ",".join(f"vendor{index}=value" for index in range(32))
    assert len(TraceState.from_header([valid])) == 32
    assert not TraceState.from_header([valid + ",extra=value"])
    assert len(TraceState.from_header([valid])) == 32


@pytest.mark.parametrize("whitespace", [" ", "\t"])
def test_malformed_whitespace_propagation_preserves_later_valid_input(whitespace):
    propagator = TraceContextTextMapPropagator()
    traceparent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    malformed = propagator.extract({
        "traceparent": traceparent,
        "tracestate": "a=b" + whitespace * 16_000 + "x",
    })
    rejected = get_current_span(malformed).get_span_context()
    assert rejected.is_valid
    assert not rejected.trace_state
    valid = propagator.extract({"traceparent": traceparent, "tracestate": "vendor=value"})
    recovered = get_current_span(valid).get_span_context()
    assert recovered.trace_id == rejected.trace_id
    assert recovered.trace_state["vendor"] == "value"
