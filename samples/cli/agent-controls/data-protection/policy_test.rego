package data_protection

import rego.v1

test_clear_output if {
    result := verdict with input as {
        "intervention_point": "output",
        "annotations": {"privacy": {"PersonallyIdentifiableInformation": {"detected": false}}},
    }
    result.decision == "allow"
}

test_detected_pii if {
    result := verdict with input as {
        "intervention_point": "output",
        "annotations": {"privacy": {"PersonallyIdentifiableInformation": {"detected": true}}},
    }
    result.decision == "deny"
}

test_missing_or_invalid_pii_evidence if {
    every facts in [{}, {"detected": null}, {"detected": "false"}] {
        result := verdict with input as {
            "intervention_point": "output",
            "annotations": {"privacy": {"PersonallyIdentifiableInformation": facts}},
        }
        result.decision == "deny"
    }
}
