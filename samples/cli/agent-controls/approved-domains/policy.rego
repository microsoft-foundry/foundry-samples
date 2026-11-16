package approved_domains

import rego.v1

default verdict := {"decision": "deny", "reason": "destination_not_approved"}

verdict := {"decision": "allow"} if {
    input.intervention_point == "pre_tool_call"
    input.snapshot.tool_call.name == "fetch_document"
    url := input.policy_target.value.url
    is_string(url)
    regex.match(`^https://(learn[.]microsoft[.]com|docs[.]example[.]com)(/[^[:space:]#]*)?$`, url)
}
