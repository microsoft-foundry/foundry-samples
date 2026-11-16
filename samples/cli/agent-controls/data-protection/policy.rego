package data_protection

import rego.v1

default verdict := {"decision": "deny", "reason": "output_requires_privacy_review"}

verdict := {"decision": "allow"} if {
    input.intervention_point == "output"
    input.annotations.privacy.PersonallyIdentifiableInformation.detected == false
}
