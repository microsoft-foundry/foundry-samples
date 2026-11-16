# Project checks: the Foundry account and project themselves.

function Test-DiagProject {
    param($Evidence)
    $d = $Evidence.discovery
    $out = [Collections.Generic.List[object]]::new()

    # project.resource — account and project exist and provisioned.
    foreach ($item in @(@{ Id = $d.account; Label = 'Foundry account' }, @{ Id = $d.project; Label = 'Foundry project' })) {
        if (!$item.Id) { continue }
        $ev = Get-Ev $Evidence $item.Id
        $title = "$($item.Label) provisioning"
        $gap = New-ReadGap $ev -Id project.resource -Area Project -Title $title -Layer Config -Resource $item.Id -What "the $($item.Label.ToLowerInvariant())"
        if ($gap) { $out.Add($gap); continue }
        $name = Get-ArmName $item.Id
        if ($ev.NotFound) {
            $out.Add((New-DiagResult -Id project.resource -Area Project -Title $title -Status Problem -Severity High -Layer Config -Resource $item.Id `
                -Seen "$($item.Label) '$name' was not found." -Owner Customer -Action 'Check the project resource ID passed to the diagnostic.' -Evidence (Get-EvRef $ev)))
            continue
        }
        $state = $ev.Data.properties.provisioningState
        if ($state -and $state -ne 'Succeeded') {
            $out.Add((New-DiagResult -Id project.resource -Area Project -Title $title -Status Problem -Severity High -Layer Config -Resource $item.Id `
                -Seen "$($item.Label) '$name' is in state '$state'." -Owner AzureAdmin `
                -Action 'Wait for the deployment to finish, or redeploy it and check the deployment error.' -Evidence (Get-EvRef $ev) -Details @{ provisioningState = $state }))
        }
        else {
            $out.Add((New-DiagResult -Id project.resource -Area Project -Title $title -Status OK -Layer Config -Resource $item.Id `
                -Seen "$($item.Label) '$name' is provisioned." -Evidence (Get-EvRef $ev)))
        }
    }

    $account = Get-Ev $Evidence $d.account
    if ($account.Ok) {
        # project.injection — agent traffic is injected into a customer subnet.
        $title = 'Agent network injection'
        $injections = @($account.Data.properties.networkInjections | Where-Object { $_ -and $_.scenario -eq 'agent' })
        $injection = $injections | Select-Object -First 1
        if (!$injection -or !$injection.subnetArmId) {
            $out.Add((New-DiagResult -Id project.injection -Area Project -Title $title -Status Problem -Severity High -Layer Config -Resource $d.account `
                -Seen 'The account has no agent network injection, so evaluations do not run in your virtual network.' -Owner AzureAdmin `
                -Action 'Deploy the account with network injection for the agent scenario pointing at a subnet delegated to Microsoft.App/environments.' `
                -Evidence (Get-EvRef $account) -Details @{ networkInjections = @($account.Data.properties.networkInjections) }))
        }
        elseif ($injection.useMicrosoftManagedNetwork) {
            $out.Add((New-DiagResult -Id project.injection -Area Project -Title $title -Status Problem -Severity High -Layer Config -Resource $d.account `
                -Seen 'The agent network injection uses a Microsoft-managed network, not your subnet.' -Owner AzureAdmin `
                -Action 'Redeploy the account with network injection set to your agent subnet.' -Evidence (Get-EvRef $account)))
        }
        else {
            $out.Add((New-DiagResult -Id project.injection -Area Project -Title $title -Status OK -Layer Config -Resource $d.account `
                -Seen "Agent traffic is injected into subnet '$(Get-ArmName $injection.subnetArmId)'." -Evidence (Get-EvRef $account) `
                -Details @{ subnet = $injection.subnetArmId }))
        }

        # project.publicAccess — recommended: public network access disabled.
        $title = 'Account public network access'
        $public = $account.Data.properties.publicNetworkAccess
        $aclDeny = $account.Data.properties.networkAcls.defaultAction -eq 'Deny'
        if ($public -eq 'Enabled' -and !$aclDeny) {
            $out.Add((New-DiagResult -Id project.publicAccess -Area Project -Title $title -Status Problem -Severity Low -Path Foundry -Layer Config -Resource $d.account `
                -Seen 'The account accepts traffic from any public network.' -Owner AzureAdmin `
                -Action 'Disable public network access on the account (or restrict it to selected networks) so only the private endpoint is used.' `
                -Evidence (Get-EvRef $account) -Details @{ publicNetworkAccess = $public; defaultAction = $account.Data.properties.networkAcls.defaultAction }))
        }
        else {
            $out.Add((New-DiagResult -Id project.publicAccess -Area Project -Title $title -Status OK -Path Foundry -Layer Config -Resource $d.account `
                -Seen $(if ($public -eq 'Enabled') { 'Public network access is limited to selected networks.' } else { 'Public network access is disabled.' }) `
                -Evidence (Get-EvRef $account)))
        }
    }

    # project.identity — the project's managed identity exists (it reads storage and monitoring data).
    $project = Get-Ev $Evidence $d.project
    if ($project.Ok) {
        $title = 'Project managed identity'
        $principal = $project.Data.identity.principalId
        if (!$principal) {
            $out.Add((New-DiagResult -Id project.identity -Area Project -Title $title -Status Problem -Severity High -Layer Access -Resource $d.project `
                -Seen 'The project has no managed identity, so it cannot read storage or monitoring data.' -Owner AzureAdmin `
                -Action 'Enable the system-assigned managed identity on the project.' -Evidence (Get-EvRef $project)))
        }
        else {
            $out.Add((New-DiagResult -Id project.identity -Area Project -Title $title -Status OK -Layer Access -Resource $d.project `
                -Seen "Project identity $principal." -Evidence (Get-EvRef $project) -Details @{ principalId = $principal; type = $project.Data.identity.type }))
        }
    }

    # project.connections — which connections the evaluation uses.
    if ($d.project) {
        $path = "$($d.project)/connections"
        $ev = Get-Ev $Evidence $path
        $title = 'Project connections'
        $gap = New-ReadGap $ev -Id project.connections -Area Project -Title $title -Layer Config -Resource $d.project -What 'the project connections'
        if ($gap) { $out.Add($gap) }
        elseif ($ev.Ok) {
            $all = @($ev.Data)
            $chosen = @($d.connections | Where-Object { $_.path })
            $notes = foreach ($c in $chosen) {
                $same = @($all | Where-Object { $_.properties.category -eq $c.category }).Count
                if ($same -gt 1) { "$($c.name) ($same $($c.category) connections; use -ConnectionName to check another)" } else { $c.name }
            }
            $seen = if ($chosen.Count) { "Checking: $($notes -join ', ')." } else { 'No storage, Application Insights or model connections; only the account path is checked.' }
            $out.Add((New-DiagResult -Id project.connections -Area Project -Title $title -Status OK -Layer Config -Resource $d.project -Seen $seen `
                -Evidence (Get-EvRef $ev) -Details @{ connections = @($all | ForEach-Object { @{ name = $_.name; category = $_.properties.category } }) }))
        }
    }

    , $out.ToArray()
}
