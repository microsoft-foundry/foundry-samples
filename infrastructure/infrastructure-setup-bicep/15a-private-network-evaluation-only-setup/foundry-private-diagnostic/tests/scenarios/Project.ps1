# Scenarios for Project and Subnet checks.
@(
    @{ Name = 'project-not-found'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Project 404 }
       Expect = @{ 'project.resource' = 'Problem:High' }; Allow = @('project.resource') }
    @{ Name = 'account-failed'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).Account).properties.provisioningState = 'Failed' }
       Expect = @{ 'project.resource' = 'Problem:High' }; Allow = @('project.resource') }
    @{ Name = 'account-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Account 403 }
       Expect = @{ 'project.resource' = 'CouldNotCheck:Blocking' }; Allow = @('project.resource') }
    @{ Name = 'no-injection'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).Account).properties.networkInjections = @() }
       Expect = @{ 'project.injection' = 'Problem:High' } }
    @{ Name = 'managed-network-injection'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).Account).properties.networkInjections[0].useMicrosoftManagedNetwork = $true }
       Expect = @{ 'project.injection' = 'Problem:High' } }
    @{ Name = 'account-public'; Mutate = { param($E) $a = Get-EvData $E (Get-TestIds).Account; $a.properties.publicNetworkAccess = 'Enabled'; $a.properties.networkAcls.defaultAction = 'Allow' }
       Expect = @{ 'project.publicAccess' = 'Problem:Low' } }
    @{ Name = 'project-no-identity'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).Project).identity = $null }
       Expect = @{ 'project.identity' = 'Problem:High' } }
    @{ Name = 'connections-unreadable'; Mutate = { param($E) Set-EvStatus $E "$((Get-TestIds).Project)/connections" 403 }
       Expect = @{ 'project.connections' = 'CouldNotCheck:Blocking' } }
    @{ Name = 'connections-old-evidence'; Mutate = { param($E) Remove-EvRequest $E "$((Get-TestIds).Project)/connections" }
       Expect = @{ 'project.connections' = 'CouldNotCheck:KnownLimit' } }

    @{ Name = 'subnet-missing'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).AgentSubnet 404 }
       Expect = @{ 'subnet.resource' = 'Problem:High' } }
    @{ Name = 'subnet-not-delegated'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).AgentSubnet).properties.delegations = @() }
       Expect = @{ 'subnet.delegation' = 'Problem:High' } }
    @{ Name = 'subnet-too-small'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).AgentSubnet).properties.addressPrefix = '10.1.2.0/28' }
       Expect = @{ 'subnet.size' = 'Problem:High' } }
    @{ Name = 'subnet-small'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).AgentSubnet).properties.addressPrefix = '10.1.2.0/26' }
       Expect = @{ 'subnet.size' = 'Problem:Low' } }
    @{ Name = 'subnet-shared'; Mutate = { param($E) (Get-EvData $E (Get-TestIds).AgentSubnet).properties.serviceAssociationLinks += @{ properties = @{ linkedResourceType = 'Microsoft.Web/serverFarms' } } }
       Expect = @{ 'subnet.attachments' = 'Problem:Medium' } }
    @{ Name = 'vnet-unreadable'; Mutate = { param($E) Set-EvStatus $E (Get-TestIds).Vnet 403 }
       Expect = @{ 'subnet.dnsServers' = 'CouldNotCheck:Blocking' } }
)
