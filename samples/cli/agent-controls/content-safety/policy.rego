package content_safety

import rego.v1

default verdict := {"decision": "deny", "reason": "content_not_cleared"}

acceptable_signals if {
    every category in ["Hate", "SelfHarm", "Sexual", "Violence"] {
        signal := input.annotations.safety[category]
        is_boolean(signal.detected)
        severity := signal.numericSeverity
        is_number(severity)
        severity == floor(severity)
        severity >= 0
        severity <= 7
        severity < 4
    }
    input.annotations.safety.PromptInjection.detected == false
}

verdict := {"decision": "allow"} if {
    input.intervention_point in {"input", "output"}
    acceptable_signals
}
