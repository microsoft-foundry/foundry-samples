# Scenarios for Nsg checks.

function global:New-NsgScenarioRule {
    param([string]$Name, [int]$Priority, [string]$Direction, [string]$Access, [string]$Destination = '*', [string]$Source = '*', [string]$Port = '*', [hashtable]$Extra = @{})
    $p = @{ priority = $Priority; direction = $Direction; access = $Access; protocol = '*'; sourceAddressPrefix = $Source; destinationAddressPrefix = $Destination
        sourcePortRange = '*'; destinationPortRange = $Port }
    foreach ($k in $Extra.Keys) { $p[$k] = $Extra[$k] }
    @{ name = $Name; properties = $p }
}

function global:Add-NsgScenarioRules {
    param($E, [string]$NsgId, [object[]]$Rules)
    $nsg = Get-EvData $E $NsgId
    $nsg.properties.securityRules = @(@($nsg.properties.securityRules) + $Rules | Where-Object { $_ })
}

# Gives the private endpoint subnet its own NSG (nsg-pe) with the given rules and network policies.
function global:Set-NsgScenarioPeSubnetNsg {
    param($E, [string]$Policies, [object[]]$Rules = @())
    $ids = Get-TestIds
    $nsgId = $ids.Nsg -replace 'nsg-agents$', 'nsg-pe'
    Set-EvRequest $E $nsgId (New-ArmObject $nsgId @{ securityRules = @($Rules); defaultSecurityRules = @(Get-DefaultNsgRules) })
    $subnet = Get-EvData $E $ids.PeSubnet
    $subnet.properties.networkSecurityGroup = @{ id = $nsgId }
    $subnet.properties.privateEndpointNetworkPolicies = $Policies
}

# Azure Monitor query goes public: no AMPLS private endpoint, public query enabled on Application Insights and the workspace.
function global:Set-NsgScenarioPublicMonitor {
    param($E)
    $ids = Get-TestIds
    @($E.discovery.dependencies | Where-Object { $_.kind -eq 'Ampls' })[0].privateEndpoints = @()
    (Get-EvData $E $ids.Ampls).properties.privateEndpointConnections = @()
    (Get-EvData $E $ids.AppInsights).properties.publicNetworkAccessForQuery = 'Enabled'
    (Get-EvData $E $ids.Workspace).properties.publicNetworkAccessForQuery = 'Enabled'
}

function global:Set-NsgScenarioRunnerNsg {
    param($E, [object[]]$Rules)
    $ids = Get-TestIds
    $nsgId = $ids.Nsg -replace 'nsg-agents$', 'nsg-jump'
    Set-EvRequest $E $nsgId (New-ArmObject $nsgId @{ securityRules = @($Rules); defaultSecurityRules = @(Get-DefaultNsgRules) })
    (Get-EvData $E $ids.JumpSubnet).properties.networkSecurityGroup = @{ id = $nsgId }
}

@(
    @{ Name = 'nsg-deny-pe-subnet'; Mutate = { param($E) Add-NsgScenarioRules $E (Get-TestIds).Nsg @(New-NsgScenarioRule 'deny-pe' 100 Outbound Deny '10.1.5.0/24') }
       Expect = @{ 'nsg.agentOutbound@Foundry' = 'Problem:High'; 'nsg.agentOutbound@Storage' = 'Problem:High'; 'nsg.agentOutbound@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'nsg-deny-one-ip'; Mutate = { param($E) Add-NsgScenarioRules $E (Get-TestIds).Nsg @(New-NsgScenarioRule 'deny-blob' 100 Outbound Deny '10.1.5.7/32' -Port '443') }
       Expect = @{ 'nsg.agentOutbound@Storage' = 'Problem:High' } }
    @{ Name = 'nsg-allow-before-deny-all'; Mutate = { param($E) Add-NsgScenarioRules $E (Get-TestIds).Nsg @(
                (New-NsgScenarioRule 'allow-vnet-443' 100 Outbound Allow 'VirtualNetwork' -Port '443'), (New-NsgScenarioRule 'deny-all' 4000 Outbound Deny)) }
       Expect = @{ 'nsg.agentOutbound' = 'OK' } }
    @{ Name = 'nsg-deny-other-port'; Mutate = { param($E) Add-NsgScenarioRules $E (Get-TestIds).Nsg @(New-NsgScenarioRule 'deny-ssh' 100 Outbound Deny '*' -Port '22') }
       Expect = @{ 'nsg.agentOutbound' = 'OK' } }
    @{ Name = 'nsg-public-monitor-internet-denied'; Mutate = { param($E) Set-NsgScenarioPublicMonitor $E
            Add-NsgScenarioRules $E (Get-TestIds).Nsg @(New-NsgScenarioRule 'deny-internet' 200 Outbound Deny 'Internet') }
       Expect = @{ 'nsg.agentOutbound@MonitorQuery' = 'Problem:High' } }
    # A service tag rule doesn't cover private endpoint addresses; the OK result says so.
    @{ Name = 'nsg-service-tag-deny-private-targets'; Mutate = { param($E) Add-NsgScenarioRules $E (Get-TestIds).Nsg @(New-NsgScenarioRule 'deny-storage' 100 Outbound Deny 'Storage') }
       Expect = @{ 'nsg.agentOutbound@Foundry' = 'OK'; 'nsg.agentOutbound@Storage' = 'OK'; 'nsg.agentOutbound@MonitorQuery' = 'OK' } }
    @{ Name = 'nsg-public-monitor-tag-allowed'; Mutate = { param($E) Set-NsgScenarioPublicMonitor $E
            Add-NsgScenarioRules $E (Get-TestIds).Nsg @((New-NsgScenarioRule 'allow-monitor' 100 Outbound Allow 'AzureMonitor' -Port '443'), (New-NsgScenarioRule 'deny-internet' 200 Outbound Deny 'Internet')) }
       Expect = @{ 'nsg.agentOutbound@MonitorQuery' = 'OK' } }
    @{ Name = 'nsg-asg-rule'; Mutate = { param($E) Add-NsgScenarioRules $E (Get-TestIds).Nsg @(New-NsgScenarioRule 'deny-asg' 100 Outbound Deny $null -Extra @{
                destinationApplicationSecurityGroups = @(@{ id = "$((Get-TestIds).Sub)/resourceGroups/rg-network/providers/Microsoft.Network/applicationSecurityGroups/asg-pe" }) }) }
       Expect = @{ 'nsg.agentOutbound' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'nsg-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Nsg 403 }
       Expect = @{ 'nsg.agentOutbound' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'nsg-not-found'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Nsg 404 }
       Expect = @{ 'nsg.agentOutbound' = 'CouldNotCheck:KnownLimit' } }

    @{ Name = 'nsg-pe-subnet-denies-agent'; Mutate = { param($E) Set-NsgScenarioPeSubnetNsg $E 'Enabled' @(New-NsgScenarioRule 'deny-agents' 100 Inbound Deny '*' '10.1.2.0/24') }
       Expect = @{ 'nsg.peInbound@Foundry' = 'Problem:High'; 'nsg.peInbound@Storage' = 'Problem:High'; 'nsg.peInbound@MonitorQuery' = 'Problem:High' } }
    @{ Name = 'nsg-pe-subnet-policies-off'; Mutate = { param($E) Set-NsgScenarioPeSubnetNsg $E 'Disabled' @(New-NsgScenarioRule 'deny-agents' 100 Inbound Deny '*' '10.1.2.0/24') }
       Expect = @{ 'nsg.peInbound' = 'OK' } }
    @{ Name = 'nsg-pe-subnet-default-rules'; Mutate = { param($E) Set-NsgScenarioPeSubnetNsg $E 'NetworkSecurityGroupEnabled' }
       Expect = @{ 'nsg.peInbound' = 'OK' } }
    @{ Name = 'nsg-pe-subnet-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).PeSubnet 403 }
       Expect = @{ 'nsg.peInbound' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'nsg-pe-subnet-nsg-unreadable'; Mutate = { param($E) Set-NsgScenarioPeSubnetNsg $E 'Enabled'; Set-EvStatus $E ((Get-TestIds).Nsg -replace 'nsg-agents$', 'nsg-pe') 403 }
       Expect = @{ 'nsg.peInbound' = 'CouldNotCheck:Blocking' } }

    @{ Name = 'nsg-runner-differs'; Mutate = { param($E) Set-NsgScenarioRunnerNsg $E @(New-NsgScenarioRule 'allow-all-443' 100 Outbound Allow '*' -Port '443') }
       Expect = @{ 'nsg.runner' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'nsg-runner-same-rules'; Mutate = { param($E) Set-NsgScenarioRunnerNsg $E @() }
       Expect = @{ 'nsg.runner' = 'OK' } }
    @{ Name = 'nsg-runner-subnet-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).JumpSubnet 403 }
       Expect = @{ 'nsg.runner' = 'CouldNotCheck:KnownLimit' } }
)
