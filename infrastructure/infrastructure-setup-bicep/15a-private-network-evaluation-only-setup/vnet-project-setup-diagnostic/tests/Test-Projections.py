"""Validate Azure CLI JMESPath projections offline using its bundled Python."""
import json
from pathlib import Path
import subprocess
import sys

import jmespath


def main():
    with open(sys.argv[1], encoding="utf-8-sig") as source:
        cases = json.load(source)
    item = {
        "id": "/fixture",
        "credentials": "fixture-sensitive-sentinel",
        "properties": {
            "credentials": {"key": "fixture-sensitive-sentinel"},
            "connectionString": "fixture-sensitive-sentinel",
            "instrumentationKey": "fixture-sensitive-sentinel",
            "authType": "AAD",
            "condition": "fixture-sensitive-sentinel",
            "category": "AppInsights",
            "metadata": {
                "ResourceId": "/fixture-insights",
                "secret": "fixture-sensitive-sentinel",
                "ApplicationInsightsConnectionString": "fixture-sensitive-sentinel",
            },
            "provisioningState": "Succeeded",
        },
    }
    for case in cases:
        data = {"value": [item], "nextLink": None} if case["collection"] else item
        result = jmespath.search(case["query"], data)
        assert "fixture-sensitive-sentinel" not in json.dumps(result), case["kind"]
        projected = result["value"][0] if case["collection"] else result
        assert projected["id"] == "/fixture"
        if case["kind"] == "Authorization":
            assert projected["properties"]["conditionPresent"] is True
        if case["kind"] == "Connection":
            assert projected["properties"]["metadata"]["ResourceId"] == "/fixture-insights"
        if case["kind"] == "Monitoring":
            assert projected["properties"]["privateLinkScopedResources"] == []
            for collection_key, id_key, scope_key in [
                ("PrivateLinkScopedResources", "ResourceId", "ScopeId"),
                ("privateLinkScopedResources", "resourceId", "scopeId"),
            ]:
                monitoring_item = {
                    "id": "/fixture-insights",
                    "properties": {
                        collection_key: [{id_key: "/fixture-ampls/scopedresources/insights", scope_key: "fixture-scope", "secret": "fixture-sensitive-sentinel"}],
                        "features": {"enableLogAccessUsingOnlyResourcePermissions": True},
                        "ConnectionString": "fixture-sensitive-sentinel",
                    },
                }
                data = {"value": [monitoring_item]} if case["collection"] else monitoring_item
                result = jmespath.search(case["query"], data)
                assert "fixture-sensitive-sentinel" not in json.dumps(result)
                normalized = result["value"][0] if case["collection"] else result
                assert normalized["properties"]["privateLinkScopedResources"] == [
                    {"resourceId": "/fixture-ampls/scopedresources/insights", "scopeId": "fixture-scope"}
                ]
                assert normalized["properties"]["features"]["enableLogAccessUsingOnlyResourcePermissions"] is True
    print(f"PASS: {len(cases)} real JMESPath projections; secret-bearing fields excluded.")
    native_path = Path(sys.argv[1]).with_name("native-projections.json")
    if native_path.exists():
        native_cases = json.loads(native_path.read_text(encoding="utf-8-sig"))
        cli_cases = [
            {"kind": case["kind"], "collection": case["collection"],
             "data": jmespath.search(case["query"], case["data"])}
            for case in native_cases
        ]
        cli_path = native_path.with_name("cli-projections.json")
        normalized_path = native_path.with_name("cli-projections-normalized.json")
        cli_path.write_text(json.dumps(cli_cases), encoding="utf-8")
        subprocess.run([
            "pwsh", "-NoProfile", "-File", str(Path(__file__).with_name("Normalize-ProjectionBatch.ps1")),
            "-InputPath", str(cli_path), "-OutputPath", str(normalized_path)
        ], check=True)
        normalized = json.loads(normalized_path.read_text(encoding="utf-8-sig"))
        for case, cli in zip(native_cases, normalized):
            assert case["native"] == cli, f"Native/CLI metadata mismatch: {case['kind']}"
            assert "projection-secret-canary" not in json.dumps(cli), case["kind"]
        assert len(native_cases) == len(normalized)
        print(f"PASS: {len(native_cases)} raw ARM/native/CLI post-projection parity cases; all supported kinds and collections.")


if __name__ == "__main__":
    main()
