# Storage checks: the storage account the project connection points at (evaluation data and results).

$script:StorageEntraAuthTypes = @('AAD', 'ManagedIdentity', 'UserEntraToken', 'ServicePrincipal')

function Get-DiagConnection {
    param($Evidence, [string]$Path)
    @($Evidence.discovery.connections | Where-Object { $_ -and $_.path -eq $Path })[0]
}

# The raw connection metadata (target, authType) from {project}/connections, or $null.
function Get-DiagConnectionData {
    param($Evidence, [string]$Name)
    $read = Get-Ev $Evidence "$($Evidence.discovery.project)/connections"
    if (!$read.Ok -or !$Name) { return $null }
    @($read.Data | Where-Object { $_ -and $_.name -eq $Name })[0]
}

function Get-DiagHostName {
    param([string]$Url)
    if (!$Url) { return $null }
    $uri = $null
    if ([uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri)) { return $uri.Host.ToLowerInvariant() }
    $null
}

function Test-DiagStorage {
    param($Evidence)
    if (!(Test-DiagPathUsed $Evidence 'Storage')) { return , @() }
    $out = [Collections.Generic.List[object]]::new()
    $conn = Get-DiagConnection $Evidence 'Storage'
    $id = $conn.resource
    $connName = $conn.name

    # storage.connection — the connection resolves to a storage account.
    $title = 'Storage connection target'
    if (!$conn -or !$id) {
        $out.Add((New-DiagResult -Id storage.connection -Area Storage -Title $title -Status Problem -Severity High -Path Storage -Layer Config -Resource $Evidence.discovery.project `
            -Seen $(if ($conn) { "Storage connection '$connName' has no storage account resource ID." } else { 'The project has no storage connection.' }) -Owner Customer `
            -Action 'Add (or fix) a project storage connection that references the storage account by its resource ID.' -Details @{ connection = $connName }))
        return , $out.ToArray()
    }
    if ($id -notmatch '(?i)/providers/Microsoft\.Storage/storageAccounts/[^/]+$') {
        $out.Add((New-DiagResult -Id storage.connection -Area Storage -Title $title -Status Problem -Severity High -Path Storage -Layer Config -Resource $id `
            -Seen "Storage connection '$connName' points at '$(Get-ArmName $id)', which is not a storage account." -Owner Customer `
            -Action "Point connection '$connName' at the resource ID of a storage account." -Details @{ connection = $connName; resource = $id }))
        return , $out.ToArray()
    }

    $name = Get-ArmName $id
    $storage = Get-Ev $Evidence $id
    $connData = Get-DiagConnectionData $Evidence $connName
    $connHost = Get-DiagHostName $connData.properties.target
    $blobHost = $(if ($storage.Ok) { Get-DiagHostName $storage.Data.properties.primaryEndpoints.blob })
    if ($connHost -and $blobHost -and $connHost -ne $blobHost) {
        $out.Add((New-DiagResult -Id storage.connection -Area Storage -Title $title -Status Problem -Severity High -Path Storage -Layer Config -Resource $id `
            -Seen "Storage connection '$connName' targets $connHost, but storage account '$name' serves blobs at $blobHost." -Owner Customer `
            -Action "Update connection '$connName' so its target is $blobHost and its resource ID is storage account '$name'." `
            -Evidence @(Get-EvRef $storage) -Details @{ connectionHost = $connHost; blobHost = $blobHost }))
    }
    else {
        $out.Add((New-DiagResult -Id storage.connection -Area Storage -Title $title -Status OK -Path Storage -Layer Config -Resource $id `
            -Seen "Storage connection '$connName' points at storage account '$name'." -Details @{ connection = $connName }))
    }

    # storage.resource — the account exists and is provisioned.
    $title = 'Storage account'
    $gap = New-ReadGap $storage -Id storage.resource -Area Storage -Title $title -Layer Config -Path Storage -Resource $id -What "storage account '$name'"
    if ($gap) { $out.Add($gap) }
    elseif ($storage.NotFound) {
        $out.Add((New-DiagResult -Id storage.resource -Area Storage -Title $title -Status Problem -Severity High -Path Storage -Layer Config -Resource $id `
            -Seen "Storage account '$name' was not found." -Owner Customer `
            -Action "Recreate storage account '$name' or point connection '$connName' at an existing storage account." -Evidence @(Get-EvRef $storage)))
    }
    elseif ($storage.Data.properties.provisioningState -and $storage.Data.properties.provisioningState -ne 'Succeeded') {
        $state = $storage.Data.properties.provisioningState
        $out.Add((New-DiagResult -Id storage.resource -Area Storage -Title $title -Status Problem -Severity High -Path Storage -Layer Config -Resource $id `
            -Seen "Storage account '$name' is in state '$state'." -Owner ResourceOwner `
            -Action "Wait for storage account '$name' to finish provisioning, or check its deployment error." -Evidence @(Get-EvRef $storage) -Details @{ provisioningState = $state }))
    }
    else {
        $out.Add((New-DiagResult -Id storage.resource -Area Storage -Title $title -Status OK -Path Storage -Layer Config -Resource $id `
            -Seen "Storage account '$name' exists." -Evidence @(Get-EvRef $storage)))
    }

    # storage.authentication — the connection uses Microsoft Entra ID, not keys.
    $title = 'Storage connection authentication'
    $connRead = Get-Ev $Evidence "$($Evidence.discovery.project)/connections"
    $gap = New-ReadGap $connRead -Id storage.authentication -Area Storage -Title $title -Layer Access -Path Storage -Resource $id -What 'the project connections'
    if ($gap) { $out.Add($gap) }
    elseif ($connRead.Ok) {
        $auth = $connData.properties.authType
        $sharedKeyOff = $storage.Ok -and $storage.Data.properties.allowSharedKeyAccess -eq $false
        if (!$auth) {
            $out.Add((New-DiagResult -Id storage.authentication -Area Storage -Title $title -Status CouldNotCheck -Gap KnownLimit -Path Storage -Layer Access -Resource $id `
                -Seen "Connection '$connName' has no authentication type in its metadata." -Needs "Check the authentication type of connection '$connName' in the Foundry portal." `
                -Evidence @(Get-EvRef $connRead)))
        }
        elseif ($auth -in $script:StorageEntraAuthTypes) {
            $out.Add((New-DiagResult -Id storage.authentication -Area Storage -Title $title -Status OK -Path Storage -Layer Access -Resource $id `
                -Seen "Connection '$connName' uses Microsoft Entra ID ($auth)." -Evidence @(Get-EvRef $connRead) -Details @{ authType = $auth }))
        }
        elseif ($sharedKeyOff) {
            $out.Add((New-DiagResult -Id storage.authentication -Area Storage -Title $title -Status Problem -Severity High -Path Storage -Layer Access -Resource $id `
                -Seen "Connection '$connName' uses $auth, but storage account '$name' doesn't allow shared key access." -Owner Customer `
                -Action "Change connection '$connName' to Microsoft Entra ID authentication and give the project managed identity Storage Blob Data Contributor on '$name'." `
                -Evidence @((Get-EvRef $connRead), (Get-EvRef $storage)) -Details @{ authType = $auth; allowSharedKeyAccess = $false }))
        }
        else {
            $out.Add((New-DiagResult -Id storage.authentication -Area Storage -Title $title -Status Problem -Severity Low -Path Storage -Layer Access -Resource $id `
                -Seen "Connection '$connName' uses $auth instead of Microsoft Entra ID." -Owner Customer `
                -Action "Change connection '$connName' to Microsoft Entra ID authentication." -Evidence @(Get-EvRef $connRead) -Details @{ authType = $auth }))
        }
    }

    if (!$storage.Ok) { return , $out.ToArray() }
    $p = $storage.Data.properties
    $public = $p.publicNetworkAccess
    $aclDeny = $p.networkAcls.defaultAction -eq 'Deny'
    $peRead = Get-Ev $Evidence "$id/privateEndpointConnections"
    $pes = @($(if ($peRead.Ok) { @($peRead.Data | Where-Object { $_ }) }))

    # storage.privatePolicy — public access off means the agent needs a private endpoint.
    $title = 'Storage private access'
    $gap = New-ReadGap $peRead -Id storage.privatePolicy -Area Storage -Title $title -Layer Config -Path Storage -Resource $id -What "the private endpoints of storage account '$name'"
    if ($gap) { $out.Add($gap) }
    elseif ($pes.Count) {
        $out.Add((New-DiagResult -Id storage.privatePolicy -Area Storage -Title $title -Status OK -Path Storage -Layer Config -Resource $id `
            -Seen "Storage account '$name' has $($pes.Count) private endpoint connection(s)." -Evidence @((Get-EvRef $storage), (Get-EvRef $peRead)) `
            -Details @{ publicNetworkAccess = $public; defaultAction = $p.networkAcls.defaultAction }))
    }
    elseif ($public -eq 'Disabled') {
        $out.Add((New-DiagResult -Id storage.privatePolicy -Area Storage -Title $title -Status Problem -Severity High -Path Storage -Layer Config -Resource $id `
            -Seen "Storage account '$name' has public network access disabled and no private endpoint." -Owner NetworkTeam `
            -Likely 'Consistent with evaluations failing to read or write evaluation data in storage.' `
            -Action "Create a blob private endpoint for storage account '$name' in a subnet the agent subnet can reach, with the privatelink.blob.core.windows.net zone." `
            -Evidence @((Get-EvRef $storage), (Get-EvRef $peRead)) -Details @{ publicNetworkAccess = $public }))
    }
    elseif ($aclDeny) {
        $out.Add((New-DiagResult -Id storage.privatePolicy -Area Storage -Title $title -Status Problem -Severity Medium -Path Storage -Layer Config -Resource $id `
            -Seen "Storage account '$name' only accepts selected networks and has no private endpoint." -Owner NetworkTeam `
            -Action "Create a blob private endpoint for storage account '$name', or make sure its network rules allow the agent subnet." `
            -Evidence @((Get-EvRef $storage), (Get-EvRef $peRead)) -Details @{ publicNetworkAccess = $public; defaultAction = 'Deny'; bypass = $p.networkAcls.bypass }))
    }
    else {
        $out.Add((New-DiagResult -Id storage.privatePolicy -Area Storage -Title $title -Status OK -Path Storage -Layer Config -Resource $id `
            -Seen "Storage account '$name' accepts public traffic; the agent reaches it over the public endpoint." -Evidence @((Get-EvRef $storage), (Get-EvRef $peRead)) `
            -Details @{ publicNetworkAccess = $public; defaultAction = $p.networkAcls.defaultAction }))
    }

    # storage.subresources — a private endpoint for each storage service the agent uses (blob, plus file/queue/table if used).
    if ($peRead.Ok -and $pes.Count) {
        $title = 'Storage private endpoint services'
        # The storage account's connection list often omits groupIds; the private endpoint itself always has them.
        $groups = @($pes | ForEach-Object {
                $g = @($_.properties.groupIds | Where-Object { $_ })
                if (!$g.Count -and $_.properties.privateEndpoint.id) {
                    $peData = (Get-Ev $Evidence $_.properties.privateEndpoint.id).Data
                    $g = @(@($peData.properties.privateLinkServiceConnections) + @($peData.properties.manualPrivateLinkServiceConnections) |
                            Where-Object { $_ } | ForEach-Object { @($_.properties.groupIds) } | Where-Object { $_ })
                }
                $g
            } | ForEach-Object { $_.ToLowerInvariant() } | Sort-Object -Unique)
        $dependency = @($Evidence.discovery.dependencies | Where-Object { $_ -and $_.kind -eq 'Storage' -and (Test-SameArmId $_.resource $id) })[0]
        $needed = [Collections.Generic.List[string]]::new()
        $needed.Add('blob')
        foreach ($h in @($dependency.hosts)) {
            if ($h -match '(?i)^[^.]+\.(file|queue|table|dfs)\.core\.') { $needed.Add($Matches[1].ToLowerInvariant()) }
        }
        $missing = @($needed | Sort-Object -Unique | Where-Object { $_ -notin $groups })
        if ($missing.Count) {
            $severity = $(if ($public -eq 'Disabled' -or $aclDeny) { 'High' } else { 'Medium' })
            $out.Add((New-DiagResult -Id storage.subresources -Area Storage -Title $title -Status Problem -Severity $severity -Path Storage -Layer Config -Resource $id `
                -Seen $(if ($groups.Count) { "Storage account '$name' has private endpoints for $($groups -join ', ') but not for $($missing -join ', ')." } else { "Storage account '$name' has no private endpoint for $($missing -join ', ')." }) -Owner NetworkTeam `
                -Action "Create a private endpoint for $($missing -join ', ') on storage account '$name', with the matching privatelink.<service>.core.windows.net zone." `
                -Evidence @(Get-EvRef $peRead) -Details @{ groupIds = $groups; missing = $missing }))
        }
        else {
            $out.Add((New-DiagResult -Id storage.subresources -Area Storage -Title $title -Status OK -Path Storage -Layer Config -Resource $id `
                -Seen "Private endpoints cover $($groups -join ', ')." -Evidence @(Get-EvRef $peRead) -Details @{ groupIds = $groups }))
        }
    }

    , $out.ToArray()
}
