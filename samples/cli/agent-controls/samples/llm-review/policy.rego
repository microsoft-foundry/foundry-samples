package llm_review

import rego.v1

default verdict := {"decision": "deny", "reason": "commitment_requires_review"}

verdict := {"decision": "allow"} if {
    input.intervention_point == "output"
    observation := input.annotations.commitment_review
    observation.schema == "acs.judge.observation/v2"
    observation.applicable == true
    observation.completed == true
    observation.label == "informational"
    is_number(observation.score)
    observation.score >= 0
    observation.score < 4
}
