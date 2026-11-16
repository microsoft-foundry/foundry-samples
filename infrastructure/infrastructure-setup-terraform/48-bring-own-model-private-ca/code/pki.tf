# ============================================================================
# Private PKI for the gateway hostname.
#
#   private root CA (CA:TRUE) --signs--> gateway leaf (SAN = gateway FQDN)
#
# * The root CA PUBLIC certificate is the trust anchor registered on the
#   Foundry account (trustedCertificateSources), so the data proxy can chain
#   the gateway's leaf up to it.
# * Application Gateway serves the leaf + root chain (PFX in Key Vault).
#
# The sample generates this PKI with Terraform for convenience; the private
# keys therefore live in Terraform state. In production, issue the gateway
# certificate from your enterprise PKI and supply only the root CA public
# certificate and the gateway PFX.
# ============================================================================

resource "tls_private_key" "root_ca" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "tls_self_signed_cert" "root_ca" {
  private_key_pem       = tls_private_key.root_ca.private_key_pem
  is_ca_certificate     = true
  set_subject_key_id    = true
  validity_period_hours = var.root_ca_validity_hours
  allowed_uses          = ["cert_signing", "crl_signing"]

  subject {
    common_name = var.root_ca_common_name
  }
}

resource "tls_private_key" "gateway" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "tls_cert_request" "gateway" {
  private_key_pem = tls_private_key.gateway.private_key_pem
  dns_names       = [local.custom_domain_fqdn]

  subject {
    common_name = local.custom_domain_fqdn
  }
}

resource "tls_locally_signed_cert" "gateway" {
  cert_request_pem      = tls_cert_request.gateway.cert_request_pem
  ca_private_key_pem    = tls_private_key.root_ca.private_key_pem
  ca_cert_pem           = tls_self_signed_cert.root_ca.cert_pem
  set_subject_key_id    = true
  validity_period_hours = var.gateway_cert_validity_hours
  early_renewal_hours   = 720
  allowed_uses          = ["digital_signature", "key_encipherment", "server_auth"]
}

resource "random_password" "gateway_pfx" {
  length  = 32
  special = false
}

# PFX = gateway leaf + private key + root CA chain, imported into Key Vault.
resource "pkcs12_from_pem" "gateway" {
  password        = random_password.gateway_pfx.result
  cert_pem        = tls_locally_signed_cert.gateway.cert_pem
  private_key_pem = tls_private_key.gateway.private_key_pem
  ca_pem          = tls_self_signed_cert.root_ca.cert_pem
  # 3DES transport encoding for broad Key Vault import compatibility; Key Vault
  # re-protects the stored certificate.
  encoding = "legacyDES"
}
