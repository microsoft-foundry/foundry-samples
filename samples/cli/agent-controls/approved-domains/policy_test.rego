package approved_domains

import rego.v1

request(url) := {
    "intervention_point": "pre_tool_call",
    "snapshot": {"tool_call": {"name": "fetch_document"}},
    "policy_target": {"value": {"url": url}},
}

test_approved_destinations if {
    every url in ["https://learn.microsoft.com", "https://learn.microsoft.com/azure/", "https://docs.example.com/api?q=tools"] {
        result := verdict with input as request(url)
        result.decision == "allow"
    }
}

test_unapproved_destinations if {
    every url in [
        "http://learn.microsoft.com/",
        "https://learn.microsoft.com.evil.example/",
        "https://learn.microsoft.com@evil.example/",
        "https://learn.microsoft.com:8443/",
        "https://evil.example/learn.microsoft.com",
        "https://learn.microsoft.com/#fragment",
        "https://learn.microsoft.com/with space",
        "",
        null,
    ] {
        result := verdict with input as request(url)
        result.decision == "deny"
    }
}

test_missing_destination if {
    result := verdict with input as {"intervention_point": "pre_tool_call", "policy_target": {"value": {}}}
    result.decision == "deny"
}
