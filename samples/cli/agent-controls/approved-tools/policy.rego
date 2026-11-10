package approved_tools

import rego.v1

default verdict := {"decision": "deny", "reason": "tool_not_approved"}

verdict := {"decision": "allow"} if {
    input.intervention_point == "pre_tool_call"
    input.snapshot.tool_call.name in {"search_catalog", "get_order"}
}
