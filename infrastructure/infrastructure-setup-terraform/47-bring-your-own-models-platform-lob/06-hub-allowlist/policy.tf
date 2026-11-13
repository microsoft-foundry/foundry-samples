# Renders the same apim-policy.xml.tftpl used by hub-workload's initial
# state, but with a populated project OID allowlist. Because hub-workload
# never creates the policy resource, hub-allowlist owns it end-to-end.
#
# Between step 2 and the first successful step 6, no APIM policy is
# attached to the inference API. During that window the gateway responds
# to any request with a raw passthrough (no auth), which is safe because
# no spoke exists yet and the gateway is only reachable via a private
# endpoint that hasn't been linked to any spoke VNet.

resource "azurerm_api_management_api_policy" "inference" {
  api_name            = local.apim_api_name
  api_management_name = local.apim_name
  resource_group_name = local.apim_rg

  xml_content = templatefile("${path.module}/apim-policy.xml.tftpl", {
    tenant_id               = local.tenant_id
    audience                = local.token_audience
    project_oid_allowlist   = var.project_oid_allowlist
    quota_tokens_per_minute = local.quota_tokens_per_min

    foundry_endpoint = local.render.foundry_endpoint
    foundry_alias    = local.render.foundry_alias

    gemini_alias    = local.render.gemini_alias
    gemini_upstream = local.render.gemini_upstream
    gemini_model    = local.render.gemini_model

    groq_alias    = local.render.groq_alias
    groq_upstream = local.render.groq_upstream
    groq_model    = local.render.groq_model

    # Diagnostic mock alias. Kept as a literal (not local.render.mock_alias) so
    # this policy render never depends on a fresh hub-workload output — a
    # targeted `04` apply (used to avoid the KV 403) need not refresh outputs.
    # Must match the "mock" catalog entry in 04-hub-workload/locals.tf.
    mock_alias = "mock"
  })
}
