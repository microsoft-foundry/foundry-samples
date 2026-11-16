# Runner checks: where the machine that ran the diagnostic sits, and whether its network matches the agent subnet's.
# Results marked * in the report come only from this machine's tests, so they matter only as far as its network matches.

$script:RunnerAzureDns = '168.63.129.16'
$script:RunnerMatchNeeds = "Run the diagnostic from a VM in the agent VNet that uses the same route table, NSG and DNS servers, to test the agent's real path."

function Get-DiagRunnerDns {
    # Effective DNS servers for a VNet: custom servers, or Azure-provided DNS.
    param($Vnet)
    $servers = @($Vnet.Data.properties.dhcpOptions.dnsServers | Where-Object { $_ })
    if ($servers.Count) { $servers } else { @($script:RunnerAzureDns) }
}

function Format-DiagRunnerName {
    param([string]$Id)
    $(if ($Id) { Get-ArmName $Id } else { 'none' })
}

# Compares the runner subnet with the agent subnet. Returns runnerMatch, differs, and why it can't tell (Seen) when Unknown.
function Get-DiagRunnerComparison {
    param($Evidence)
    $agentId = $Evidence.discovery.agentSubnet
    $runner = $Evidence.discovery.runner
    $runnerId = $runner.subnet
    $result = @{ Match = 'Unknown'; Differs = @(); Refs = @(); Seen = $null; Compared = @() }
    if (!$agentId) {
        $result.Seen = "The project's agent subnet isn't known, so this machine's network can't be compared with it."
        return $result
    }
    if (!$runnerId) {
        $result.Seen = $(if (!$Evidence.discovery.Contains('runner')) { 'This evidence file has no data about the machine that ran the diagnostic.' }
            else { "This machine's subnet isn't known (it isn't an Azure VM, or its VM couldn't be read), so its network can't be compared with the agent subnet." })
        return $result
    }
    $agent = Get-Ev $Evidence $agentId
    $mine = Get-Ev $Evidence $runnerId
    foreach ($read in @($agent, $mine)) {
        if ($read.Ok) { $result.Refs += Get-EvRef $read; continue }
        $label = Get-ArmName $read.Path
        $why = $(if (!$read.Read) { "This evidence file has no data for subnet '$label'" }
            elseif ($read.NotFound) { "Subnet '$label' wasn't found" }
            else { $result.Refs += Get-EvRef $read; "Couldn't read subnet '$label' ($($read.Status) $($read.ErrorKind))" })
        $result.Seen = "$why, so this machine's network can't be compared with the agent subnet."
        return $result
    }
    if (Test-SameArmId $agentId $runnerId) { $result.Match = 'Match'; return $result }

    $a = $agent.Data.properties; $r = $mine.Data.properties
    $differs = [Collections.Generic.List[string]]::new()
    $routeDiffers = $false
    $agentVnetId = Get-ArmParent $agentId; $runnerVnetId = Get-ArmParent $runnerId
    if (!(Test-SameArmId $agentVnetId $runnerVnetId)) {
        $differs.Add("virtual network: runner $(Get-ArmName $runnerVnetId), agents $(Get-ArmName $agentVnetId)")
    }
    if (!(Test-SameArmId $a.routeTable.id $r.routeTable.id) -and ($a.routeTable.id -or $r.routeTable.id)) {
        $differs.Add("route table: runner $(Format-DiagRunnerName $r.routeTable.id), agents $(Format-DiagRunnerName $a.routeTable.id)")
        $routeDiffers = $true
    }
    if (!(Test-SameArmId $a.networkSecurityGroup.id $r.networkSecurityGroup.id) -and ($a.networkSecurityGroup.id -or $r.networkSecurityGroup.id)) {
        $differs.Add("NSG: runner $(Format-DiagRunnerName $r.networkSecurityGroup.id), agents $(Format-DiagRunnerName $a.networkSecurityGroup.id)")
    }
    if ($runner.nic) {
        $nic = Get-Ev $Evidence $runner.nic
        if ($nic.Ok) {
            $result.Refs += Get-EvRef $nic
            $nicNsg = $nic.Data.properties.networkSecurityGroup.id
            if ($nicNsg) { $differs.Add("network interface NSG: runner $(Get-ArmName $nicNsg), agents none") }
        }
    }
    # DNS: what this machine actually uses vs what the agent VNet hands out.
    $agentVnet = Get-Ev $Evidence $agentVnetId
    if ($agentVnet.Ok) {
        $result.Refs += Get-EvRef $agentVnet
        $agentDns = @(Get-DiagRunnerDns $agentVnet)
        $runnerDns = @($Evidence.run.runner.dnsServers | Where-Object { $_ })
        if (!$runnerDns.Count) {
            $runnerVnet = Get-Ev $Evidence $runnerVnetId
            if ($runnerVnet.Ok) { $runnerDns = @(Get-DiagRunnerDns $runnerVnet) }
        }
        if ($runnerDns.Count -and (@($runnerDns | Sort-Object) -join ',') -ne (@($agentDns | Sort-Object) -join ',')) {
            $differs.Add("DNS servers: runner $($runnerDns -join ' '), agents $($agentDns -join ' ')")
        }
    }
    $result.Differs = @($differs)
    $result.Match = $(if (!$differs.Count) { 'Match' } elseif ($routeDiffers) { 'NoMatch' } else { 'Partial' })
    $result.Compared = @('virtual network', 'route table', 'NSG', 'DNS servers')
    $result
}

function Test-DiagRunner {
    param($Evidence)
    $out = [Collections.Generic.List[object]]::new()
    $info = $Evidence.run.runner
    $d = $Evidence.discovery
    $runner = $d.runner

    # runner.location — Azure VM → NIC → subnet.
    $title = 'Location of this machine'
    if (!$d.Contains('runner') -and !$info) {
        $out.Add((New-DiagResult -Id runner.location -Area Runner -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Config `
            -Seen 'This evidence file has no data about the machine that ran the diagnostic.' -Needs 'Run the current version of the diagnostic to collect it.'))
    }
    elseif (!$runner.vm -and !$info.azureVmResourceId) {
        $out.Add((New-DiagResult -Id runner.location -Area Runner -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Config `
            -Seen "This machine isn't an Azure VM, or its VM details couldn't be read, so its network can't be compared with the agent subnet." `
            -Needs 'Run the diagnostic from an Azure VM in the agent virtual network for network tests that reflect the agent path.'))
    }
    else {
        $vmId = $(if ($runner.vm) { $runner.vm } else { $info.azureVmResourceId })
        $vm = Get-Ev $Evidence $vmId
        $nic = Get-Ev $Evidence $runner.nic
        if ($runner.subnet) {
            $ip = @($nic.Data.properties.ipConfigurations | Where-Object { $_ -and (Test-SameArmId $_.properties.subnet.id $runner.subnet) } |
                ForEach-Object { $_.properties.privateIPAddress } | Where-Object { $_ })[0]
            $out.Add((New-DiagResult -Id runner.location -Area Runner -Title $title -Status OK -Layer Config -Resource $vmId `
                -Seen "This machine is VM '$(Get-ArmName $vmId)' in subnet '$(Get-ArmName $runner.subnet)' of virtual network '$(Get-ArmName (Get-ArmParent $runner.subnet))'$(if ($ip) { " ($ip)" })." `
                -Evidence @(@($vm, $nic) | Where-Object Ok | ForEach-Object { Get-EvRef $_ }) -Details @{ vm = $vmId; nic = $runner.nic; subnet = $runner.subnet; ip = $ip }))
        }
        else {
            $gap = $null
            if ($vm.ErrorKind -in @('Forbidden', 'Unauthorized')) {
                # Typical of managed machines such as Cloud PCs and Dev Boxes, whose VM lives in a Microsoft subscription.
                $gap = New-DiagResult -Id runner.location -Area Runner -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Config -Resource $vmId `
                    -Seen "This machine's VM is in a subscription this sign-in can't read, so it's likely not on the agent network." `
                    -Needs 'Run the diagnostic from an Azure VM in the agent virtual network for network tests that reflect the agent path.' -Evidence (Get-EvRef $vm)
            }
            if (!$gap) { $gap = New-ReadGap $vm -Id runner.location -Area Runner -Title $title -Layer Config -Resource $vmId -What "VM '$(Get-ArmName $vmId)'" }
            if (!$gap -and $runner.nic) { $gap = New-ReadGap $nic -Id runner.location -Area Runner -Title $title -Layer Config -Resource $vmId -What "network interface '$(Get-ArmName $runner.nic)'" }
            if (!$gap) {
                $gap = New-DiagResult -Id runner.location -Area Runner -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Config -Resource $vmId `
                    -Seen "This machine is VM '$(Get-ArmName $vmId)', but its subnet couldn't be found." -Needs 'Run the diagnostic from a VM whose network interface is readable.'
            }
            $out.Add($gap)
        }
    }

    # runner.match — exactly one result; details feed the report's runner footnote.
    $title = "Network match between this machine and the agent subnet"
    $cmp = Get-DiagRunnerComparison $Evidence
    $details = @{ runnerMatch = $cmp.Match; differs = @($cmp.Differs); runnerSubnet = $runner.subnet; agentSubnet = $d.agentSubnet; compared = $cmp.Compared }
    switch ($cmp.Match) {
        'Match' {
            $out.Add((New-DiagResult -Id runner.match -Area Runner -Title $title -Status OK -Layer Config -Resource $runner.subnet `
                -Seen $(if (Test-SameArmId $runner.subnet $d.agentSubnet) { 'This machine is in the agent subnet.' } else { "This machine's subnet '$(Get-ArmName $runner.subnet)' uses the same virtual network, route table, NSG and DNS servers as the agent subnet." }) `
                -Evidence $cmp.Refs -Details $details))
        }
        default {
            # A runner off the agent's path is a limit of this run, never a setup fault.
            $seen = $(if ($cmp.Match -eq 'Unknown') { $cmp.Seen } else { "This machine's network differs from the agent subnet: $($cmp.Differs -join '; ')." })
            $out.Add((New-DiagResult -Id runner.match -Area Runner -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Config -Scope ThisMachine `
                -Resource $runner.subnet -Seen $seen -Needs $script:RunnerMatchNeeds -Evidence $cmp.Refs -Details $details))
        }
    }

    # runner.proxy — a proxy on this machine can make its tests take a different path from the agent's.
    $title = 'Proxy on this machine'
    if (!$info -or !$info.Contains('proxy') -or $null -eq $info.proxy) {
        $out.Add((New-DiagResult -Id runner.proxy -Area Runner -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Config -Scope ThisMachine `
            -Seen 'This evidence file has no proxy settings for this machine.' -Needs 'Run the current version of the diagnostic to collect them.'))
    }
    else {
        $system = $info.proxy.system
        $envVars = @($info.proxy.env | Where-Object { $_ })
        $set = @()
        if ($system -and $system -ne 'none') { $set += "system proxy $system" }
        if ($envVars.Count) { $set += "environment variables $($envVars -join ', ')" }
        if ($set.Count) {
            $out.Add((New-DiagResult -Id runner.proxy -Area Runner -Title $title -Status Problem -Severity Medium -Layer Config -Scope ThisMachine `
                -Seen "This machine has a proxy configured ($($set -join '; '))." `
                -Likely "Consistent with this machine's tests and sign-in taking a different path from the agent's traffic." -Owner Customer `
                -Action 'Run the diagnostic from a machine without a proxy in the agent virtual network, or treat results marked * as this machine''s view only.' `
                -Details @{ system = $system; env = $envVars }))
        }
        else {
            $out.Add((New-DiagResult -Id runner.proxy -Area Runner -Title $title -Status OK -Layer Config -Scope ThisMachine -Seen 'No proxy is configured on this machine.'))
        }
    }

    # runner.token — informational.
    $title = 'Sign-in used by this run'
    $source = $info.tokenSource
    if (!$source) {
        $out.Add((New-DiagResult -Id runner.token -Area Runner -Title $title -Status CouldNotCheck -Gap KnownLimit -Layer Config -Scope ThisMachine `
            -Seen 'This evidence file has no sign-in details.' -Needs 'Run the current version of the diagnostic to collect them.'))
    }
    else {
        $label = switch ($source) { 'ManagedIdentity' { "this VM's managed identity" } 'AzAccounts' { 'the Az PowerShell sign-in (Connect-AzAccount)' } default { $source } }
        $out.Add((New-DiagResult -Id runner.token -Area Runner -Title $title -Status OK -Layer Config -Scope ThisMachine `
            -Seen "Azure was read using $label; results that couldn't be read depend on its permissions." -Details @{ tokenSource = $source }))
    }

    , $out.ToArray()
}
