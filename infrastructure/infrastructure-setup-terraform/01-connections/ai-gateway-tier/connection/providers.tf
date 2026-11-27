# Resource IDs below are absolute, so the spoke project and the hub gateway can
# be in different subscriptions; the signed-in identity needs access to both.
provider "azapi" {
  subscription_id = var.subscription_id
}
