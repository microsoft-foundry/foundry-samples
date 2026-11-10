package refund_guard

import rego.v1

default verdict := {"decision": "allow"}

permitted_tool_call if {
    input.snapshot.tool_call.name == "lookup_order"
}

permitted_tool_call if {
    input.snapshot.tool_call.name == "refund_order"
    amount := input.policy_target.value.amount
    is_number(amount)
    amount > 0
    amount <= 100
}

verdict := {
    "decision": "deny",
    "reason": "tool_request_not_permitted",
    "message": "Use an approved tool. Refund amounts must be numeric, greater than zero, and at most 100.",
} if {
    input.intervention_point == "pre_tool_call"
    not permitted_tool_call
}
