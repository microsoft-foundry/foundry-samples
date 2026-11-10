package llm_review

import rego.v1

observation := {
    "schema": "acs.judge.observation/v2",
    "applicable": true,
    "completed": true,
    "label": "informational",
    "score": 0,
}

request(facts) := {"intervention_point": "output", "annotations": {"commitment_review": facts}}

test_informational_response if {
    every score in [0, 3.99] {
        result := verdict with input as request(object.union(observation, {"score": score}))
        result.decision == "allow"
    }
}

test_commitment_requires_review if {
    every score in [4, 7, 10] {
        result := verdict with input as request(object.union(observation, {"label": "commitment", "score": score}))
        result.decision == "deny"
    }
}

test_boundary_and_invalid_scores if {
    every score in [4, -1, 11, "0", null] {
        result := verdict with input as request(object.union(observation, {"score": score}))
        result.decision == "deny"
    }
}

test_uncertain_or_incomplete if {
    every change in [
        {"label": "uncertain"},
        {"label": "commitment", "score": 0},
        {"completed": false},
        {"applicable": false},
        {"schema": "acs.judge.observation/v1"},
    ] {
        result := verdict with input as request(object.union(observation, change))
        result.decision == "deny"
    }
}

test_missing_observation if {
    result := verdict with input as {"intervention_point": "output", "annotations": {}}
    result.decision == "deny"
}
