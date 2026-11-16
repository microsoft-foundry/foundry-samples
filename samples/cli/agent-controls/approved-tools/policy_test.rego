package approved_tools

import rego.v1

test_approved_tools if {
    every name in ["search_catalog", "get_order"] {
        result := verdict with input as {"intervention_point": "pre_tool_call", "snapshot": {"tool_call": {"name": name}}}
        result.decision == "allow"
    }
}

test_unapproved_tools if {
    every name in ["delete_order", "refund_order", "", "GET_ORDER"] {
        result := verdict with input as {"intervention_point": "pre_tool_call", "snapshot": {"tool_call": {"name": name}}}
        result.decision == "deny"
    }
}

test_missing_tool if {
    result := verdict with input as {"intervention_point": "pre_tool_call"}
    result.decision == "deny"
}
