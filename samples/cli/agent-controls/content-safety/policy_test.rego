package content_safety

import rego.v1

signals := {
    "Hate": {"detected": false, "numericSeverity": 0},
    "SelfHarm": {"detected": false, "numericSeverity": 0},
    "Sexual": {"detected": false, "numericSeverity": 0},
    "Violence": {"detected": false, "numericSeverity": 0},
    "PromptInjection": {"detected": false},
}

request(facts) := {"intervention_point": "input", "annotations": {"safety": facts}}

test_clear_content if {
    result := verdict with input as request(signals)
    result.decision == "allow"
}

test_severity_boundary if {
    every severity in [4, 5, 6, 7] {
        facts := object.union(signals, {"Violence": {"detected": true, "numericSeverity": severity}})
        result := verdict with input as request(facts)
        result.decision == "deny"
    }
    facts := object.union(signals, {"Violence": {"detected": true, "numericSeverity": 3}})
    result := verdict with input as request(facts)
    result.decision == "allow"
}

test_prompt_injection if {
    facts := object.union(signals, {"PromptInjection": {"detected": true}})
    result := verdict with input as request(facts)
    result.decision == "deny"
}

test_missing_evidence if {
    result := verdict with input as request(object.remove(signals, ["Hate"]))
    result.decision == "deny"
}

test_invalid_severity if {
    every severity in [-1, 8, 0.5, "0", null] {
        facts := object.union(signals, {"Hate": {"detected": false, "numericSeverity": severity}})
        result := verdict with input as request(facts)
        result.decision == "deny"
    }
}

test_output_is_checked if {
    result := verdict with input as {"intervention_point": "output", "annotations": {"safety": signals}}
    result.decision == "allow"
}
