package refund_guard

import rego.v1

request(name, args) := {
    "intervention_point": "pre_tool_call",
    "policy_target": {"value": args},
    "snapshot": {"tool_call": {"name": name, "args": args}},
}

test_allowed_refund_amounts if {
    every amount in [0.01, 99.99, 100] {
        result := verdict with input as request("refund_order", {"amount": amount})
        result.decision == "allow"
    }
}

test_invalid_refund_amounts if {
    every amount in [0, -1, 100.01, "100", null, true] {
        result := verdict with input as request("refund_order", {"amount": amount})
        result.decision == "deny"
    }
}

test_missing_refund_amount if {
    result := verdict with input as request("refund_order", {})
    result.decision == "deny"
}

test_unknown_tool if {
    result := verdict with input as request("delete_order", {})
    result.decision == "deny"
}

test_lookup_order if {
    result := verdict with input as request("lookup_order", {"order_id": "demo-001"})
    result.decision == "allow"
}

test_other_points if {
    every point in ["agent_startup", "input", "pre_model_call", "post_model_call", "post_tool_call", "output", "agent_shutdown"] {
        result := verdict with input as {"intervention_point": point}
        result.decision == "allow"
    }
}
