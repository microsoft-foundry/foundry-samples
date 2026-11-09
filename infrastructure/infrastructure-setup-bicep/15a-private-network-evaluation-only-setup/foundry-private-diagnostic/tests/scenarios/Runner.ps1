# Scenarios for Runner checks (where the diagnostic ran, and whether its network matches the agent subnet).
@(
    @{ Name = 'runner-not-azure-vm'
       Mutate = { param($E) $E.run.runner.azureVmResourceId = $null; $E.discovery.runner = [ordered]@{ vm = $null; nic = $null; subnet = $null } }
       Expect = @{ 'runner.location' = 'CouldNotCheck:KnownLimit'; 'runner.match' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'runner-other-vnet-and-route'
       Mutate = { param($E)
           $ids = Get-TestIds
           $hubVnet = "$($ids.Sub)/resourceGroups/rg-hub/providers/Microsoft.Network/virtualNetworks/vnet-hub"
           $subnet = "$hubVnet/subnets/mgmt"
           Set-EvRequest $E $subnet (New-ArmObject $subnet @{ addressPrefix = '10.0.9.0/24'; delegations = @()
               routeTable = @{ id = "$($ids.Sub)/resourceGroups/rg-hub/providers/Microsoft.Network/routeTables/rt-mgmt" } })
           Set-EvRequest $E $hubVnet (New-ArmObject $hubVnet @{ addressSpace = @{ addressPrefixes = @('10.0.0.0/16') }; dhcpOptions = @{ dnsServers = @() } })
           (Get-EvData $E $ids.Nic).properties.ipConfigurations[0].properties.subnet.id = $subnet
           $E.discovery.runner.subnet = $subnet }
       Expect = @{ 'runner.match' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'runner-different-route-table'
       Mutate = { param($E) (Get-EvData $E (Get-TestIds).JumpSubnet).properties.routeTable = @{ id = "$((Get-TestIds).Sub)/resourceGroups/rg-network/providers/Microsoft.Network/routeTables/rt-jump" } }
       Expect = @{ 'runner.match' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'runner-different-nsg'
       Mutate = { param($E) (Get-EvData $E (Get-TestIds).JumpSubnet).properties.networkSecurityGroup = @{ id = "$((Get-TestIds).Sub)/resourceGroups/rg-network/providers/Microsoft.Network/networkSecurityGroups/nsg-jump" } }
       Expect = @{ 'runner.match' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'runner-nic-nsg'
       Mutate = { param($E) (Get-EvData $E (Get-TestIds).Nic).properties.networkSecurityGroup = @{ id = "$((Get-TestIds).Sub)/resourceGroups/rg-network/providers/Microsoft.Network/networkSecurityGroups/nsg-nic" } }
       Expect = @{ 'runner.match' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'runner-different-dns'
       Mutate = { param($E) $E.run.runner.dnsServers = @('10.9.9.9') }
       Expect = @{ 'runner.match' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'runner-subnet-unreadable'
       Mutate = { param($E) Set-EvStatus $E (Get-TestIds).JumpSubnet 403 }
       Expect = @{ 'runner.match' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'runner-vm-unreadable'
       Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Vm 403; $E.discovery.runner.nic = $null; $E.discovery.runner.subnet = $null }
       Expect = @{ 'runner.location' = 'CouldNotCheck:KnownLimit'; 'runner.match' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'runner-no-agent-subnet'
       Mutate = { param($E) $E.discovery.agentSubnet = $null }
       Expect = @{ 'runner.match' = 'CouldNotCheck:KnownLimit' } }
    @{ Name = 'runner-proxy'
       Mutate = { param($E) $E.run.runner.proxy = @{ system = 'proxy.contoso.com:8080'; env = @('HTTPS_PROXY') } }
       Expect = @{ 'runner.proxy' = 'Problem:Medium' } }
    @{ Name = 'runner-old-evidence'
       Mutate = { param($E) $E.run.Remove('runner'); $E.discovery.Remove('runner') }
       Expect = @{ 'runner.location' = 'CouldNotCheck:KnownLimit'; 'runner.match' = 'CouldNotCheck:KnownLimit'
                   'runner.proxy' = 'CouldNotCheck:KnownLimit'; 'runner.token' = 'CouldNotCheck:KnownLimit' } }
)
