# Virtual Network
resource "azurerm_virtual_network" "main" {
  count               = var.enable_networking ? 1 : 0
  name                = var.vnet_name
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = [var.vnet_address_prefix]
}

# Subnets
resource "azurerm_subnet" "private_endpoints" {
  count                             = var.enable_networking ? 1 : 0
  name                              = var.private_endpoints_subnet_name
  resource_group_name               = azurerm_resource_group.main.name
  virtual_network_name              = azurerm_virtual_network.main[0].name
  address_prefixes                  = [var.private_endpoints_subnet_prefix]
  default_outbound_access_enabled   = true
}

resource "azurerm_subnet" "vms" {
  count                             = var.enable_vm ? 1 : 0
  name                              = var.vm_subnet_name
  resource_group_name               = azurerm_resource_group.main.name
  virtual_network_name              = azurerm_virtual_network.main[0].name
  address_prefixes                  = [var.vm_subnet_prefix]
  default_outbound_access_enabled   = true
}

resource "azurerm_subnet" "bastion" {
  count                             = var.enable_vm ? 1 : 0
  name                              = "AzureBastionSubnet"
  resource_group_name               = azurerm_resource_group.main.name
  virtual_network_name              = azurerm_virtual_network.main[0].name
  address_prefixes                  = [var.bastion_subnet_prefix]
  default_outbound_access_enabled   = true
}

# Bastion Public IP
resource "azurerm_public_ip" "bastion" {
  count               = var.enable_vm ? 1 : 0
  name                = "${var.bastion_name}-pip"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

# Azure Bastion
resource "azurerm_bastion_host" "main" {
  count               = var.enable_vm ? 1 : 0
  name                = var.bastion_name
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard"

  ip_configuration {
    name                 = "bastionIpConfig"
    subnet_id            = azurerm_subnet.bastion[0].id
    public_ip_address_id = azurerm_public_ip.bastion[0].id
  }

  # Enable features for enhanced connectivity
  tunneling_enabled      = true
  shareable_link_enabled = false
  ip_connect_enabled     = true
  copy_paste_enabled     = true
  file_copy_enabled      = true

  tags = merge(
    var.tags,
    {
      environment = "lab"
    }
  )
}

# Network Interface for VM
resource "azurerm_network_interface" "vm" {
  count               = var.enable_vm ? 1 : 0
  name                = "${var.vm_name}-nic"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.vms[0].id
    private_ip_address_allocation = "Dynamic"
  }
}

# Windows Server 2025 VM with Entra ID Authentication
resource "azurerm_windows_virtual_machine" "main" {
  count               = var.enable_vm ? 1 : 0
  name                = var.vm_name
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  size                = "Standard_B2s"
  admin_username      = var.vm_admin_username
  admin_password      = random_password.vm_admin[0].result

  network_interface_ids = [
    azurerm_network_interface.vm[0].id
  ]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "MicrosoftWindowsServer"
    offer     = "WindowsServer"
    sku       = "2025-datacenter-azure-edition"
    version   = "latest"
  }

  # Enable system-assigned managed identity for Entra ID login
  identity {
    type = "SystemAssigned"
  }

  # Enable Azure Hybrid Benefit for Windows Server
  license_type = "Windows_Server"

  automatic_updates_enabled = true
  provision_vm_agent        = true
  patch_mode                = "AutomaticByPlatform"
  patch_assessment_mode     = "AutomaticByPlatform"

  tags = merge(
    var.tags,
    {
      environment = "lab"
    }
  )
}

# AAD Login Extension for Windows
resource "azurerm_virtual_machine_extension" "aad_login" {
  count                      = var.enable_vm ? 1 : 0
  name                       = "AADLoginForWindows"
  virtual_machine_id         = azurerm_windows_virtual_machine.main[0].id
  publisher                  = "Microsoft.Azure.ActiveDirectory"
  type                       = "AADLoginForWindows"
  type_handler_version       = "2.0"
  auto_upgrade_minor_version = true
}

# Role Assignment: Virtual Machine Administrator Login for current user
resource "azurerm_role_assignment" "vm_admin_login" {
  count                = var.enable_vm ? 1 : 0
  scope                = azurerm_windows_virtual_machine.main[0].id
  role_definition_name = "Virtual Machine Administrator Login"
  principal_id         = data.azurerm_client_config.current.object_id
}
